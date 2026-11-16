import asyncio
import logging

from pw_channel import config
from pw_channel.db.core import DatabaseUnavailable, init_database, is_configured, redacted_url

logger = logging.getLogger(__name__)

CONNECT_ATTEMPTS = 6
CONNECT_BACKOFF_SECS = 2.5

_state: dict = {"ready": False, "error": None, "url": "", "seeded": 0}


def status() -> dict:
    return {
        "useDb": config.USE_DB,
        "configured": is_configured(),
        "ready": _state["ready"],
        "error": _state["error"],
        "url": _state["url"],
        "configSource": config.source(),
    }


async def bring_up() -> dict:
    _state["url"] = redacted_url()

    if not config.USE_DB:
        logger.info(
            "[db] USE_DB is false — running on .env values. The dashboard's "
            "Configuration screen will be read-only until you set USE_DB=true."
        )
        _state["ready"] = False
        _state["error"] = None
        return status()

    if not is_configured():
        message = "USE_DB is true but DATABASE_URL is empty, so there is nowhere to read settings from"
        logger.error(f"[db] {message}")
        _state["ready"] = False
        _state["error"] = message
        return status()

    for attempt in range(1, CONNECT_ATTEMPTS + 1):
        try:
            init_database()

            from pw_channel.auth.roles import ensure_default_roles
            from pw_channel.auth.users import ensure_seed_admin
            from pw_channel.settings.custom_store import apply_to_environment
            from pw_channel.settings.store import prune_unknown, seed_from_environment

            _state["seeded"] = seed_from_environment()
            dropped = prune_unknown()
            if dropped:
                logger.info(
                    f"[settings] dropped {len(dropped)} row(s) for settings that no "
                    f"longer exist: {', '.join(dropped)}"
                )
            ensure_default_roles()
            ensure_seed_admin()
            from pw_channel.intake.intakes import ensure_builtin

            ensure_builtin()

            custom = apply_to_environment()
            if custom:
                logger.info(f"[settings] {custom} custom variable(s) exported to the environment")

            changes = config.reload()
            logger.info(
                f"[db] control plane ready ({len(changes)} settings differed from .env)"
            )
            _state["ready"] = True
            _state["error"] = None
            return status()
        except DatabaseUnavailable as e:
            _state["ready"] = False
            _state["error"] = str(e)
            if attempt < CONNECT_ATTEMPTS:
                logger.warning(
                    f"[db] {redacted_url()} not reachable yet "
                    f"(attempt {attempt}/{CONNECT_ATTEMPTS}), retrying in "
                    f"{CONNECT_BACKOFF_SECS:g}s"
                )
                await asyncio.sleep(CONNECT_BACKOFF_SECS)
                continue
            logger.error(
                f"[db] giving up on {redacted_url()} after {CONNECT_ATTEMPTS} "
                f"attempts — running on .env values. Fix the connection and "
                f"restart. Last error: {e}"
            )
        except Exception as e:
            logger.exception("[db] control plane failed to start")
            _state["ready"] = False
            _state["error"] = str(e)
            break

    return status()
