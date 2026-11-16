import re
import time
import uuid
import asyncio
import logging
from typing import Optional, List, Dict, Any

import asyncpg

from pw_channel.channels.whatsapp.settings import settings

logger = logging.getLogger(__name__)


_DB_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_IMAGE_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")
_CAPTION_LIMIT = 1024

MAX_IMAGE_BYTES = 5 * 1024 * 1024

IMAGE_ROUTE_PREFIX = "/campaign-media/"

_IMAGE_MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a", "image/png"),
)


def _sniff_image_type(content: bytes) -> str:
    for magic, mime in _IMAGE_MAGIC:
        if content.startswith(magic):
            return mime
    return ""


class CampaignConflictError(Exception):
    pass


class CampaignValidationError(Exception):
    pass


class CampaignStoreUnavailable(Exception):
    pass


class CampaignStore:

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None
        self._cache: Optional[List[Dict[str, Any]]] = None
        self._cache_ts: float = 0.0
        self._ttl = settings.campaign_cache_ttl
        self._connect_lock = asyncio.Lock()


    async def connect(self):
        if self._pool is not None:
            return
        async with self._connect_lock:
            if self._pool is not None:
                return
            try:
                pool = await self._create_pool()
            except Exception as e:
                logger.error(f"CampaignStore could not connect to Postgres: {e}")
                raise CampaignStoreUnavailable(str(e))

            self._pool = pool
            try:
                await self._ensure_schema()
            except Exception as e:
                await pool.close()
                self._pool = None
                logger.error(f"CampaignStore schema/seed failed: {e}")
                raise CampaignStoreUnavailable(str(e))

            logger.info(f"CampaignStore connected to Postgres database '{settings.campaign_db_name}'")

    async def _create_pool(self) -> asyncpg.Pool:
        try:
            return await asyncpg.create_pool(
                dsn=settings.pg_app_dsn, min_size=1, max_size=5, command_timeout=10
            )
        except asyncpg.InvalidCatalogNameError:
            await self._create_database()
            return await asyncpg.create_pool(
                dsn=settings.pg_app_dsn, min_size=1, max_size=5, command_timeout=10
            )

    async def _create_database(self):
        db = settings.campaign_db_name
        if not _DB_NAME_RE.match(db):
            raise CampaignStoreUnavailable(f"Invalid campaign_db_name '{db}' (must be a plain identifier).")
        conn = await asyncpg.connect(dsn=settings.pg_maintenance_dsn)
        try:
            exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db)
            if not exists:
                await conn.execute(f'CREATE DATABASE "{db}"')
                logger.info(f"CampaignStore created database '{db}'")
        except asyncpg.DuplicateDatabaseError:
            pass
        finally:
            await conn.close()

    async def disconnect(self):
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("CampaignStore Postgres pool closed")

    async def _ensure_schema(self):
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trigger_campaigns (
                    id            SERIAL PRIMARY KEY,
                    name          TEXT NOT NULL DEFAULT '',
                    karix_numbers TEXT[] NOT NULL DEFAULT '{}',
                    all_numbers   BOOLEAN NOT NULL DEFAULT FALSE,
                    trigger_words TEXT[] NOT NULL DEFAULT '{}',
                    message       TEXT NOT NULL,
                    image_url     TEXT NOT NULL DEFAULT '',
                    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE INDEX IF NOT EXISTS idx_trigger_campaigns_numbers
                    ON trigger_campaigns USING GIN (karix_numbers);

                -- Images uploaded from an admin's device. Stored as bytes in
                -- Postgres (rather than on disk) so they survive container
                -- restarts without needing a mounted volume. Served publicly
                -- by GET /campaign-media/{id}, which is the URL WhatsApp
                -- fetches when the campaign is sent.
                CREATE TABLE IF NOT EXISTS campaign_images (
                    id           TEXT PRIMARY KEY,
                    content      BYTEA NOT NULL,
                    content_type TEXT NOT NULL,
                    filename     TEXT NOT NULL DEFAULT '',
                    byte_size    INTEGER NOT NULL DEFAULT 0,
                    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                """
            )
            await conn.execute(
                "ALTER TABLE trigger_campaigns "
                "ADD COLUMN IF NOT EXISTS image_url TEXT NOT NULL DEFAULT ''"
            )


    @staticmethod
    def _normalize_triggers(trigger_words: List[str]) -> List[str]:
        seen, out = set(), []
        for w in trigger_words or []:
            norm = (w or "").strip().upper()
            if norm and norm not in seen:
                seen.add(norm)
                out.append(norm)
        return out

    @staticmethod
    def _normalize_image_url(image_url: Optional[str]) -> str:
        url = (image_url or "").strip()
        if not url:
            return ""
        if not _IMAGE_URL_RE.match(url):
            raise CampaignValidationError(
                "Image URL must be a public http:// or https:// link "
                "(WhatsApp downloads the image from that URL)."
            )
        path = url.split("?", 1)[0].split("#", 1)[0].lower()

        if IMAGE_ROUTE_PREFIX in path:
            return url

        if not path.endswith(_IMAGE_EXTENSIONS):
            raise CampaignValidationError(
                f"Image URL must point to a JPG or PNG file "
                f"(WhatsApp supports {', '.join(_IMAGE_EXTENSIONS)} for image messages)."
            )
        return url

    @staticmethod
    def _normalize_numbers(numbers: List[str]) -> List[str]:
        seen, out = set(), []
        for n in numbers or []:
            norm = (n or "").strip().lstrip("+")
            if norm and norm not in seen:
                seen.add(norm)
                out.append(norm)
        return out

    @staticmethod
    def _row_to_dict(row: asyncpg.Record) -> Dict[str, Any]:
        d = dict(row)
        for ts in ("created_at", "updated_at"):
            if d.get(ts) is not None:
                d[ts] = d[ts].isoformat()
        return d

    def _invalidate_cache(self):
        self._cache = None
        self._cache_ts = 0.0

    def _applies_to(self, all_numbers: bool, numbers: List[str]) -> set:
        return set(settings.campaign_numbers_list) if all_numbers else set(numbers)

    def _validate_input(
        self, karix_numbers: List[str], all_numbers: bool, trigger_words: List[str], message: str,
        image_url: Optional[str] = "",
    ):
        norm_numbers = self._normalize_numbers(karix_numbers)
        if all_numbers:
            norm_numbers = []
        else:
            if not norm_numbers:
                raise CampaignValidationError("Select at least one bot number, or enable 'All numbers'.")
            allowed = set(settings.campaign_numbers_list)
            invalid = [n for n in norm_numbers if n not in allowed]
            if invalid:
                raise CampaignValidationError(
                    f"Not a registered bot number: {invalid}. "
                    f"Campaigns may target registered Karix senders "
                    f"({', '.join(settings.karix_numbers_list) or 'none'}), Nowonextel numbers "
                    f"({', '.join(settings.nowonextel_numbers_list) or 'none'}) or the "
                    f"Meta number ({settings.meta_number or 'not configured'})."
                )
        norm_triggers = self._normalize_triggers(trigger_words)
        if not norm_triggers:
            raise CampaignValidationError("At least one non-empty trigger word is required.")
        if not (message or "").strip():
            raise CampaignValidationError("Message cannot be empty.")
        norm_image = self._normalize_image_url(image_url)
        return norm_numbers, norm_triggers, norm_image

    async def _assert_no_trigger_conflict(
        self, conn, all_numbers: bool, numbers: List[str], triggers: List[str], exclude_id: Optional[int] = None
    ):
        my_numbers = self._applies_to(all_numbers, numbers)
        incoming = set(triggers)
        rows = await conn.fetch(
            """
            SELECT id, name, all_numbers, karix_numbers, trigger_words
            FROM trigger_campaigns
            WHERE is_active = TRUE AND ($1::int IS NULL OR id <> $1)
            """,
            exclude_id,
        )
        for r in rows:
            other_numbers = self._applies_to(r["all_numbers"], r["karix_numbers"])
            shared = my_numbers & other_numbers
            overlap = incoming & set(r["trigger_words"])
            if shared and overlap:
                where = "all numbers" if (all_numbers and r["all_numbers"]) else ", ".join(sorted(shared))
                raise CampaignConflictError(
                    f"Trigger word(s) {sorted(overlap)} already used by active campaign "
                    f"#{r['id']} ('{r['name']}') on {where}."
                )


    async def list_campaigns(self, karix_number: Optional[str] = None) -> List[Dict[str, Any]]:
        await self.connect()
        async with self._pool.acquire() as conn:
            if karix_number:
                num = karix_number.strip().lstrip("+")
                rows = await conn.fetch(
                    "SELECT * FROM trigger_campaigns "
                    "WHERE all_numbers = TRUE OR $1 = ANY(karix_numbers) ORDER BY id DESC",
                    num,
                )
            else:
                rows = await conn.fetch("SELECT * FROM trigger_campaigns ORDER BY id DESC")
        return [self._row_to_dict(r) for r in rows]

    async def get_campaign(self, campaign_id: int) -> Optional[Dict[str, Any]]:
        await self.connect()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM trigger_campaigns WHERE id = $1", campaign_id)
        return self._row_to_dict(row) if row else None

    async def create_campaign(
        self,
        karix_numbers: List[str],
        trigger_words: List[str],
        message: str,
        name: str = "",
        is_active: bool = True,
        all_numbers: bool = False,
        image_url: str = "",
    ) -> Dict[str, Any]:
        numbers, triggers, image = self._validate_input(
            karix_numbers, all_numbers, trigger_words, message, image_url
        )
        await self.connect()
        async with self._pool.acquire() as conn:
            if is_active:
                await self._assert_no_trigger_conflict(conn, all_numbers, numbers, triggers)
            row = await conn.fetchrow(
                """
                INSERT INTO trigger_campaigns
                    (name, karix_numbers, all_numbers, trigger_words, message, image_url, is_active)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING *
                """,
                (name or "").strip(), numbers, all_numbers, triggers, message, image, is_active,
            )
        self._invalidate_cache()
        logger.info(
            f"Campaign #{row['id']} created (all={all_numbers}, numbers={numbers}, "
            f"triggers={triggers}, image={'yes' if image else 'no'})"
        )
        return self._row_to_dict(row)

    async def update_campaign(
        self,
        campaign_id: int,
        karix_numbers: List[str],
        trigger_words: List[str],
        message: str,
        name: str = "",
        is_active: bool = True,
        all_numbers: bool = False,
        image_url: str = "",
    ) -> Optional[Dict[str, Any]]:
        numbers, triggers, image = self._validate_input(
            karix_numbers, all_numbers, trigger_words, message, image_url
        )
        await self.connect()
        async with self._pool.acquire() as conn:
            existing = await conn.fetchrow("SELECT id FROM trigger_campaigns WHERE id = $1", campaign_id)
            if not existing:
                return None
            if is_active:
                await self._assert_no_trigger_conflict(conn, all_numbers, numbers, triggers, exclude_id=campaign_id)
            row = await conn.fetchrow(
                """
                UPDATE trigger_campaigns
                SET name = $2, karix_numbers = $3, all_numbers = $4, trigger_words = $5,
                    message = $6, is_active = $7, image_url = $8, updated_at = now()
                WHERE id = $1
                RETURNING *
                """,
                campaign_id, (name or "").strip(), numbers, all_numbers, triggers, message,
                is_active, image,
            )
        self._invalidate_cache()
        logger.info(
            f"Campaign #{campaign_id} updated (all={all_numbers}, numbers={numbers}, "
            f"triggers={triggers}, image={'yes' if image else 'no'})"
        )
        return self._row_to_dict(row)

    async def delete_campaign(self, campaign_id: int) -> bool:
        await self.connect()
        async with self._pool.acquire() as conn:
            result = await conn.execute("DELETE FROM trigger_campaigns WHERE id = $1", campaign_id)
        self._invalidate_cache()
        deleted = result.endswith("1")
        if deleted:
            logger.info(f"Campaign #{campaign_id} deleted")
        return deleted


    async def save_image(self, content: bytes, filename: str = "") -> Dict[str, Any]:
        if not content:
            raise CampaignValidationError("The uploaded file is empty.")
        if len(content) > MAX_IMAGE_BYTES:
            raise CampaignValidationError(
                f"Image is {len(content) / 1024 / 1024:.1f} MB — the maximum is "
                f"{MAX_IMAGE_BYTES // 1024 // 1024} MB (WhatsApp's own limit)."
            )
        content_type = _sniff_image_type(content)
        if not content_type:
            raise CampaignValidationError(
                "Unsupported file type — only JPG and PNG images can be sent on WhatsApp."
            )

        image_id = uuid.uuid4().hex
        await self.connect()
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO campaign_images (id, content, content_type, filename, byte_size)
                VALUES ($1, $2, $3, $4, $5)
                """,
                image_id, content, content_type, (filename or "")[:200], len(content),
            )
        logger.info(
            f"[CAMPAIGN] Stored uploaded image {image_id} "
            f"({content_type}, {len(content)} bytes, name={filename!r})"
        )
        return {
            "id": image_id,
            "content_type": content_type,
            "byte_size": len(content),
            "filename": filename or "",
        }

    async def get_image(self, image_id: str) -> Optional[Dict[str, Any]]:
        await self.connect()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT content, content_type FROM campaign_images WHERE id = $1", image_id
            )
        if not row:
            return None
        return {"content": bytes(row["content"]), "content_type": row["content_type"]}


    async def _load_active_cache(self) -> List[Dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT karix_numbers, all_numbers, trigger_words, message, image_url "
                "FROM trigger_campaigns WHERE is_active = TRUE"
            )
        self._cache = [
            {
                "numbers": set(r["karix_numbers"]),
                "all": r["all_numbers"],
                "triggers": set(r["trigger_words"]),
                "message": r["message"],
                "image_url": r["image_url"] or "",
            }
            for r in rows
        ]
        self._cache_ts = time.time()
        return self._cache

    async def match_trigger(self, bot_number: str, message: str) -> Optional[Dict[str, str]]:
        if not bot_number or not message:
            return None
        try:
            if self._pool is None:
                await self.connect()
            if self._cache is None or (time.time() - self._cache_ts) > self._ttl:
                await self._load_active_cache()

            number = bot_number.strip().lstrip("+")
            applicable = [c for c in (self._cache or []) if c["all"] or number in c["numbers"]]
            if not applicable:
                return None

            candidate = message.strip()

            for camp in applicable:
                if candidate in camp["triggers"]:
                    return {
                        "message": camp["message"],
                        "image_url": camp.get("image_url", ""),
                    }
            return None
        except Exception as e:
            logger.error(f"[CAMPAIGN] match_trigger failed for {bot_number}: {e}")
            return None


campaign_store = CampaignStore()
