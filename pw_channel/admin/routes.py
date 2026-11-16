import json
import re
import logging
import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from pw_channel import config
from pw_channel.auth import (
    LoginFailed,
    SessionUser,
    authenticate,
    change_password,
    issue_token,
)
from pw_channel.auth.guards import current_user, describe, require
from pw_channel.auth import otp
from pw_channel.auth.users import RESET_LINK_MINUTES, account as users_account, request_reset, reset_with_token, session_user
from pw_channel.intake import intakes as qms_intakes
from pw_channel.db import (
    DatabaseUnavailable,
    call_events,
    call_records,
    call_sessions,
    call_transcripts,
)
from pw_channel.intake import events as ingestion_events
from pw_channel.db.core import is_configured as is_db_configured
from pw_channel.db.bootstrap import status as db_status
from pw_channel.settings.watcher import status as watcher_status
from pw_channel.admin.schema import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    OtpResendRequest,
    OtpVerifyRequest,
    ResetPasswordRequest,
    LoginResponse,
    SettingsResetRequest,
    SettingsUpdateRequest,
    SettingsUpdateResponse,
    TestCallRequest,
)
from pw_channel.settings import registry
from pw_channel.settings.registry import ValidationError
from pw_channel.observability import log_file, log_event
from pw_channel.settings.store import read_meta, recent_changes, write_many
from pw_channel.settings.store import reset_keys as store_reset_keys
from pw_channel.channels.voice.calls import masking as call_masking
from pw_channel.channels.email import mailer
from pw_channel.intake import labels as qms
from pw_channel.channels.voice import usecases
from pw_channel.channels.voice.tts.factory import provider as tts_provider

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["dashboard"])

STARTED_AT = time.time()

CLEAR_SENTINEL = "__clear__"

_NO_DB = "Live call tracking needs USE_DB=true"


FORGOT_COOLDOWN_SECS = 60.0
_forgot_at: dict[str, float] = {}


def _masked(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:2]}{'•' * max(1, len(local) - 2)}@{domain}"


def _email_code(user_id: int, code: str) -> str:
    row = users_account(user_id)
    if not row:
        raise HTTPException(status_code=401, detail="this account can no longer sign in")
    sent, error = mailer.send_login_code(row["email"], row["name"], code, otp.CODE_TTL_SECS // 60)
    if not sent:
        raise HTTPException(status_code=503, detail=f"the sign-in code could not be emailed: {error}")
    return row["email"]


@router.post("/login")
def login(req: LoginRequest):
    try:
        user = authenticate(req.email, req.password)
    except LoginFailed as e:
        raise HTTPException(status_code=401, detail=str(e))
    except DatabaseUnavailable as e:
        raise HTTPException(
            status_code=503,
            detail=f"the settings database is unreachable, so logins cannot be checked: {e}",
        )

    challenge, code = otp.start(user.id)
    try:
        email = _email_code(user.id, code)
    except HTTPException:
        otp.cancel(challenge)
        raise
    logger.info(f"[dashboard] {user.email} passed the password step; code emailed")
    return {
        "otpRequired": True,
        "challenge": challenge,
        "sentTo": _masked(email),
        "expiresIn": otp.CODE_TTL_SECS,
        "resendIn": otp.RESEND_AFTER_SECS,
    }


@router.post("/login/verify", response_model=LoginResponse)
def login_verify(req: OtpVerifyRequest):
    try:
        user_id = otp.verify(req.challenge, req.code)
        user = session_user(user_id)
    except otp.OtpError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except LoginFailed as e:
        raise HTTPException(status_code=401, detail=str(e))
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))

    token, expires_at = issue_token(user)
    logger.info(f"[dashboard] {user.email} signed in")
    return LoginResponse(token=token, expiresAt=expires_at, user=describe(user))


@router.post("/login/resend")
def login_resend(req: OtpResendRequest):
    try:
        user_id, code = otp.resend(req.challenge)
    except otp.OtpError as e:
        raise HTTPException(status_code=429, detail=str(e))
    email = _email_code(user_id, code)
    return {"sentTo": _masked(email), "expiresIn": otp.CODE_TTL_SECS, "resendIn": otp.RESEND_AFTER_SECS}


@router.get("/me")
def me(user: SessionUser = Depends(current_user)):
    return describe(user)


@router.post("/password")
def update_password(req: ChangePasswordRequest, user: SessionUser = Depends(current_user)):
    try:
        change_password(
            user_id=user.id,
            current_password=req.currentPassword,
            new_password=req.newPassword,
        )
    except LoginFailed as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"message": "Password changed"}


def _send_forgotten(email: str) -> None:
    try:
        result = request_reset(email)
    except DatabaseUnavailable as e:
        logger.warning(f"[dashboard] password reset for {email} failed: {e}")
        return
    if result is None:
        logger.info(f"[dashboard] password reset asked for {email}, which has no active account")
        return
    user, token = result
    link = f"{mailer.dashboard_url().rstrip('/')}/reset?token={token}"
    sent, error = mailer.send_reset_link(user["email"], user["name"], link, RESET_LINK_MINUTES)
    if not sent:
        logger.warning(f"[dashboard] reset link for {user['email']} not sent: {error}")


@router.post("/password/reset")
def reset_password(req: ResetPasswordRequest):
    try:
        user = reset_with_token(req.token, req.newPassword)
    except LoginFailed as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    logger.info(f"[dashboard] {user['email']} reset their password from an emailed link")
    return {"message": "Password changed. Sign in with the new one."}


@router.post("/password/forgot")
def forgot_password(req: ForgotPasswordRequest, background: BackgroundTasks):
    email = (req.email or "").strip().lower()
    now = time.monotonic()
    if len(_forgot_at) > 1000:
        for key in [k for k, at in _forgot_at.items() if now - at >= FORGOT_COOLDOWN_SECS]:
            del _forgot_at[key]
    if email and now - _forgot_at.get(email, -FORGOT_COOLDOWN_SECS) >= FORGOT_COOLDOWN_SECS:
        _forgot_at[email] = now
        background.add_task(_send_forgotten, email)
    return {"ok": True}


def _live_value(key: str) -> str:
    return config.raw_values().get(key, "")


@router.get("/settings")
def get_settings(_: SessionUser = Depends(require("settings.view"))):
    catalog = registry.describe()

    stored: dict[str, dict] = {}
    if config.USE_DB:
        try:
            stored = read_meta()
        except DatabaseUnavailable as e:
            logger.warning(f"[dashboard] settings store unreachable: {e}")

    values: dict[str, dict] = {}
    for key, setting in registry.SETTINGS.items():
        live = _live_value(key)
        meta = stored.get(key, {})
        drifted = key in stored and (meta.get("value") or "").strip() != (setting.default or "").strip()
        values[key] = {
            "value": "" if setting.secret else live,
            "hasValue": bool(live),
            "defaultValue": None if setting.secret else setting.default,
            "changedFromDefault": drifted,
            "source": "database" if key in stored else ("environment" if setting.restart and os.getenv(key) else "default"),
            "inheritedValue": _live_value(setting.inherits) if setting.inherits else None,
            "updatedAt": meta.get("updatedAt"),
            "updatedBy": meta.get("updatedBy"),
        }

    return {
        **catalog,
        "values": values,
        "editable": config.USE_DB,
        "source": config.source(),
        "restartKeys": sorted(config.RESTART_REQUIRED_KEYS),
        "db": db_status(),
    }


@router.put("/settings", response_model=SettingsUpdateResponse)
def put_settings(req: SettingsUpdateRequest, user: SessionUser = Depends(require("settings.edit"))):
    if not config.USE_DB:
        raise HTTPException(
            status_code=409,
            detail="This container reads .env, not the database. Set USE_DB=true and "
            "restart to edit settings from here.",
        )

    updates: dict[str, str] = {}
    for key, raw in req.values.items():
        setting = registry.get_setting(key)
        if setting is None:
            raise HTTPException(status_code=400, detail=f"{key} is not a known setting")

        if setting.secret:
            text = "" if raw is None else str(raw)
            if text == CLEAR_SENTINEL:
                updates[key] = ""
                continue
            if text == "":
                continue

        try:
            updates[key] = registry.coerce(key, raw)
        except ValidationError as e:
            raise HTTPException(status_code=400, detail=str(e))

    if not updates:
        return SettingsUpdateResponse(
            saved=[], applied=False, restartRequired=[], message="Nothing to save"
        )

    try:
        config.validate(updates)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        saved = write_many(updates, changed_by=user.email)
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=f"could not save: {e}")

    if not saved:
        return SettingsUpdateResponse(
            saved=[], applied=False, restartRequired=[], message="No values changed"
        )

    applied = False
    if req.apply:
        config.reload()
        applied = True

    needs_restart = sorted(set(saved) & config.RESTART_REQUIRED_KEYS)
    logger.info(f"[dashboard] {user.email} changed {len(saved)} settings: {', '.join(saved)}")

    if needs_restart:
        if len(saved) == len(needs_restart):
            message = (
                f"Saved. {len(needs_restart)} "
                + ("change takes" if len(needs_restart) == 1 else "changes take")
                + " effect on the next restart."
            )
        else:
            message = (
                f"Applied {len(saved) - len(needs_restart)} of {len(saved)} changes. "
                + f"The other {len(needs_restart)} "
                + ("needs" if len(needs_restart) == 1 else "need")
                + " a restart."
            )
    elif applied:
        message = (
            f"Applied {len(saved)} " + ("change" if len(saved) == 1 else "changes") +
            ". The next call uses them."
        )
    elif config.SETTINGS_REFRESH_SECS > 0:
        message = (
            f"Saved {len(saved)} changes. Every worker picks them up within "
            f"{config.SETTINGS_REFRESH_SECS:g}s."
        )
    else:
        message = f"Saved {len(saved)} changes. They apply on the next restart."

    return SettingsUpdateResponse(
        saved=saved, applied=applied, restartRequired=needs_restart, message=message
    )


@router.post("/settings/reset")
def reset_settings(req: SettingsResetRequest, user: SessionUser = Depends(require("settings.edit"))):
    if not config.USE_DB:
        raise HTTPException(
            status_code=409,
            detail="This container reads .env already, so there is nothing stored to reset.",
        )

    unknown = [k for k in req.keys if k not in registry.SETTINGS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"not a known setting: {sorted(unknown)}")

    candidate = {k: registry.SETTINGS[k].default for k in req.keys}
    try:
        config.validate(candidate)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"the defaults these would fall back to are not valid together: {e}",
        )

    try:
        removed = store_reset_keys(list(req.keys), changed_by=user.email)
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=f"could not reset: {e}")

    if removed:
        config.reload()

    return {
        "reset": removed,
        "message": (
            f"{len(removed)} " + ("setting is" if len(removed) == 1 else "settings are")
            + " back on the default."
            if removed
            else "Nothing was stored for those — they were already on their defaults."
        ),
    }


@router.post("/settings/apply")
def apply_settings(_: SessionUser = Depends(require("settings.edit"))):
    try:
        changes = config.reload()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "applied": sorted(changes),
        "count": len(changes),
        "source": config.source(),
        "message": f"Reloaded {len(changes)} settings from the {config.source()}",
    }


@router.get("/settings/history")
def settings_history(limit: int = 40, _: SessionUser = Depends(require("settings.view"))):
    if not config.USE_DB:
        return {"changes": []}
    try:
        return {"changes": recent_changes(min(limit, 200))}
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


def _channel_rows() -> list[dict]:
    def credentials(*pairs: tuple[str, str]) -> list[str]:
        return [label for label, value in pairs if not value]

    return [
        {
            "id": "acefone",
            "name": "Acefone",
            "enabled": config.ENABLE_ACEFONE,
            "path": config.ACEFONE_WS_PATH,
            "dialer": True,
            "missing": credentials(("API key", config.ACEFONE_API_KEY), ("Access token", config.ACEFONE_AUTH_TOKEN)),
        },
        {
            "id": "website",
            "name": "Website widget",
            "enabled": config.ENABLE_WEBSITE,
            "path": config.WEBSITE_WS_PATH,
            "dialer": False,
            "missing": [],
        },
    ]


@router.get("/status")
def status(_: SessionUser = Depends(current_user)):
    calls: dict | None = None
    if config.USE_DB:
        try:
            calls = call_records.counts()
        except Exception:
            calls = None

    return {
        "app": {
            "startedAt": datetime.fromtimestamp(STARTED_AT, timezone.utc).isoformat(),
            "uptimeSecs": round(time.time() - STARTED_AT, 1),
            "phoneBrain": config.PW_CHAT_USER_TYPE_PHONE,
            "websiteBrain": config.PW_CHAT_USER_TYPE_WEBSITE,
            "language": config.LANGUAGE_NAME,
            "publicBase": config.PUBLIC_WSS_BASE,
            "logLevel": config.LOG_LEVEL,
        },
        "stack": {
            "stt": {
                "provider": config.STT_PROVIDER,
                "model": config.STT_MODEL,
                "fluxModel": config.STT_FLUX_MODEL,
                "byChannel": config.STT_PROVIDER_BY_CHANNEL,
                "language": config.STT_LANGUAGE,
                "ready": bool(config.DEEPGRAM_API_KEY),
            },
            "llm": {
                "provider": "pw-llm",
                "model": f"{config.PW_CHAT_USER_TYPE_PHONE} / {config.PW_CHAT_USER_TYPE_WEBSITE}",
                "url": config.PW_CHAT_API_URL,
                "ready": config.PW_CHAT_ENABLED
                and bool(config.PW_CHAT_API_URL)
                and bool(config.PW_CHAT_API_TOKEN),
            },
            "tts": {
                "provider": config.TTS_PROVIDER,
                "model": _tts_model(),
                "voice": _tts_voice(),
                "ready": _tts_ready(),
            },
        },
        "channels": _channel_rows(),
        "integrations": {
            "ingestion": _ingestion_config(),
            "dispositionWebhook": bool(config.DISPOSITION_LOG_WEBHOOK),
        },
        "conversation": {
            "maxCallSecs": config.MAX_CALL_DURATION_SECS,
            "wrapUpSecs": config.CALL_WRAP_UP_WARNING_SECS,
            "idleNudgeSecs": config.USER_IDLE_TIMEOUT_SECS,
            "maxReprompts": config.MAX_CONSECUTIVE_REPROMPTS,
            "minWordsToInterrupt": config.MIN_WORDS_TO_INTERRUPT,
            "outputGainDb": config.BOT_OUTPUT_GAIN_DB,
            "languageSwitch": config.ENABLE_LANGUAGE_SWITCH,
        },
        "calls": calls,
        "db": db_status(),
        "settingsWatch": watcher_status(),
        "logs": {
            "file": str(log_file()),
            "exists": log_file().exists(),
            "sizeBytes": log_file().stat().st_size if log_file().exists() else 0,
            "tokenSet": bool(config.INTERNAL_LOG_TOKEN),
        },
    }


def _tts_model() -> str:
    return tts_provider().default_model()


def _tts_voice() -> str:
    return tts_provider().default_voice()


def _tts_ready() -> bool:
    return tts_provider().ready()


@router.post("/calls")
async def place_call(req: TestCallRequest, user: SessionUser = Depends(require("calls.place"))):
    from pw_channel.intake import service as intake_service
    from pw_channel.intake.replay import phone_test_intake

    base = qms_intakes.get(req.intake) if req.intake else None
    if req.intake and base is None:
        raise HTTPException(status_code=404, detail="no such intake")
    if req.record is not None:
        record = {k: v for k, v in req.record.items() if v not in (None, "")}
    else:
        record = req.model_dump(exclude={"channel", "delay_secs", "intake", "record", "use_case"})
        record = {k: v for k, v in record.items() if v not in (None, "")}
    intake = phone_test_intake(req.use_case or "", base)
    if intake["adapter"] == "builtin.canonical" and "ref" not in record:
        intake["adapter"] = "builtin.fields"
        intake["fields"] = []
    channel = "voice"
    delivery = await intake_service.ingest_records(intake, record, source_ip=f"dashboard:{user.email}", dedupe=False)
    result = delivery.results[0] if delivery.results else {"status": "rejected", "reason": "nothing was sent"}
    result["status"] = "scheduled" if result["status"] == "merged" else result["status"]

    if result["status"] != "scheduled":
        errors = result.get("errors") or []
        detail = (
            "Not dialled. Fill in: "
            + "; ".join(f"{e['field'] or 'record'} {e['error']}" for e in errors)
            if errors
            else f"Not dialled: {result.get('reason', result['status'])}"
        )
        log_event(
            "call.rejected",
            level=logging.WARNING,
            channel=channel,
            reference_id=record.get("reference_id", ""),
            requested_by=user.email,
            error=detail,
        )
        raise HTTPException(status_code=422, detail={"message": detail, "errors": errors})

    log_event(
        "call.requested",
        channel=channel,
        reference_id=result["reference_id"],
        requested_by=user.email,
        delay_secs=result["delay_secs"],
        ingestion_id=result["ingestion_id"],
    )
    logger.info(
        f"[dashboard] {user.email} placed a {channel} call for {result['reference_id']} "
        f"(ingestion #{result['ingestion_id']})"
    )
    delay = result["delay_secs"]
    return {
        "success": True,
        "channel": channel,
        "referenceId": result["reference_id"],
        "ingestionId": result["ingestion_id"],
        "scheduledFor": result["scheduled_for"],
        "message": (
            f"Calling now over {channel}. Reference {result['reference_id']}, follow it in History (#{result['ingestion_id']})"
            if not delay
            else f"Call queued for {delay:g}s from now. Reference {result['reference_id']}, follow it in History (#{result['ingestion_id']})"
        ),
    }


def _client_agents(user: SessionUser) -> set[str] | None:
    if not user.org_id:
        return None
    from pw_channel.auth import orgs

    return orgs.allowed_agents(user.org_id)


@router.get("/calls")
def call_history(limit: int = 50, _: SessionUser = Depends(require("calls.live.view"))):
    if not config.USE_DB:
        return {"calls": [], "note": "Call history needs USE_DB=true"}
    try:
        allowed = _client_agents(_)
        if allowed is not None:
            return {"calls": call_records.recent(min(limit, 200), agents=sorted(allowed))}
        return {"calls": call_records.recent(min(limit, 200))}
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/calls/active")
def active_calls(
    did: str = "",
    ended: int = 10,
    _: SessionUser = Depends(require("calls.live.view")),
):
    if not config.USE_DB:
        return {"active": [], "recentlyEnded": [], "counts": {}, "note": _NO_DB}
    did = did.strip()
    if not did:
        return {
            "active": [],
            "recentlyEnded": [],
            "counts": {},
            "needsDid": True,
        }
    try:
        return {
            "did": did,
            "active": call_masking.agent_views(call_sessions.active(did=did)),
            "recentlyEnded": call_masking.agent_views(
                call_sessions.recently_ended(did=did, limit=min(ended, 50))
            ),
            "counts": call_sessions.counts(did=did),
        }
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/calls/dids")
def call_dids(_: SessionUser = Depends(require("calls.live.view"))):
    if not config.USE_DB:
        return {"dids": [], "note": _NO_DB}
    try:
        return {"dids": call_sessions.dids(), "configured": config.CALL_TRANSFER_NUMBER}
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/calls/{session_id}/transcript")
def call_transcript(session_id: int, _: SessionUser = Depends(require("calls.live.view"))):
    if not config.USE_DB:
        return {"call": None, "turns": [], "note": _NO_DB}
    try:
        call = call_sessions.by_id(session_id)
        if call is None:
            raise HTTPException(status_code=404, detail="no such call")
        return {
            "call": call_masking.agent_view(call),
            "turns": call_transcripts.for_session(session_id),
            "timeline": call_masking.timeline(call, call_events.for_session(session_id)),
        }
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


def _is_customer(role) -> bool:
    return role in ("customer", "user")


_briefs: dict[int, tuple[int, dict]] = {}


@router.post("/calls/{session_id}/summary")
async def call_brief(session_id: int, user: SessionUser = Depends(require("calls.live.view"))):
    import asyncio

    from pw_channel.admin.usecases import _brain

    if not config.USE_DB:
        raise HTTPException(status_code=409, detail=_NO_DB)
    try:
        call = await asyncio.to_thread(call_sessions.by_id, session_id)
        turns = await asyncio.to_thread(call_transcripts.for_session, session_id, 500)
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    if call is None:
        raise HTTPException(status_code=404, detail="no such call")
    spoken = [t for t in turns if (t.get("text") or "").strip()]
    if not any(_is_customer(t.get("role")) for t in spoken):
        raise HTTPException(status_code=409, detail="the customer has not said anything yet")
    cached = _briefs.get(session_id)
    if cached and cached[0] == len(spoken):
        return {**cached[1], "turns": len(spoken)}
    brief = await _brain("POST", "/calls/summarize", json={
        "audience": "agent",
        "messages": [{"role": "user" if _is_customer(t["role"]) else "assistant", "text": t["text"]} for t in spoken],
        "customer_name": call.get("customerName"),
        "reference_id": call.get("bookingReferenceId"),
        "ended_reason": call.get("endedReason"),
    }, timeout=45.0)
    _briefs[session_id] = (len(spoken), brief)
    if len(_briefs) > 500:
        _briefs.pop(next(iter(_briefs)))
    return {**brief, "turns": len(spoken)}


WEBRTC_SAMPLE_RATES = (8000, 16000, 22050, 24000, 44100, 48000)

def tts_keys() -> dict[str, dict[str, str]]:
    from pw_channel.channels.voice.tts.factory import TTS

    return {name: tts_provider(name).setting_keys() for name in TTS.names()}


CALL_KEYS = (
    "PUBLIC_WSS_BASE",
    "MAX_CALL_DURATION_SECS",
    "ENABLE_CALL_TRANSFER",
    "CALL_TRANSFER_NUMBER",
)


def _channel_keys(channel: str) -> tuple:
    group = next((g for g in registry.GROUPS if g.id == channel), None)
    if group is None:
        return ()
    return tuple(s.key for s in group.settings if not s.advanced)

def _setting_view(key: str) -> dict | None:
    setting = registry.get_setting(key)
    if setting is None:
        return None
    live = _live_value(key)
    return {
        "key": key,
        "label": setting.label,
        "help": setting.help,
        "type": setting.type,
        "options": list(setting.options or ()),
        "unit": setting.unit,
        "secret": setting.secret,
        "value": "" if setting.secret else live,
        "hasValue": bool(live),
    }


def _views(keys) -> list[dict]:
    return [view for view in (_setting_view(key) for key in keys) if view]


@router.get("/playground")
def playground(_: SessionUser = Depends(require("calls.place"))):
    provider = config.TTS_PROVIDER.lower()
    voices = {
        name: {
            "voice": _live_value(keys["voice"]),
            "voices": list(getattr(registry.get_setting(keys["voice"]), "options", ()) or ()),
            "model": _live_value(keys["model"]) if keys.get("model") else "",
            "keySet": bool(_live_value(keys["key"])),
        }
        for name, keys in tts_keys().items()
    }

    return {
        "editable": config.USE_DB,
        "webrtc": {
            "path": config.WEBSITE_WS_PATH,
            "enabled": config.ENABLE_WEBSITE,
            "sampleRates": list(WEBRTC_SAMPLE_RATES),
            "sampleRate": config.WEBSITE_SAMPLE_RATE,
            "pipelineRate": config.WEBSITE_PIPELINE_SAMPLE_RATE,
            "ttsProvider": provider,
            "language": config.BOT_LANGUAGE,
            "tts": voices,
        },
        "call": {
            "channels": [
                {**row, "settings": _views(_channel_keys(row["id"]))}
                for row in _channel_rows()
                if row["dialer"]
            ],
            "settings": _views(CALL_KEYS),
            "publicBase": config.PUBLIC_WSS_BASE,
        },
    }


def _ingestion_config() -> dict:
    return {
        "enabled": config.INGESTION_ENABLED,
        "path": "/api/ingestion/calls",
        "dialer": config.INGESTION_CALL_CHANNEL,
        "agent": config.INGESTION_AGENT,
        "delaySecs": config.INGESTION_CALL_DELAY_SECS,
        "dedupeWindowSecs": config.INGESTION_DEDUPE_WINDOW_SECS,
        "maxBatch": config.INGESTION_MAX_BATCH,
        "tokenSet": bool(config.INGESTION_API_TOKEN),
    }


_KEY = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
_INTAKE_ID = re.compile(r"^[a-z][a-z0-9_]{2,40}$")


def _example(field: dict):
    if "example" in field and field["example"] not in (None, ""):
        return field["example"]
    kind = field.get("type", "text")
    return {
        "number": 1000, "integer": 1, "date": "2026-11-14", "datetime": "2026-10-14T18:30:00+05:30",
        "enum": (field.get("options") or ["value"])[0], "phone": "9876543210", "email": "name@example.com",
        "url": "https://example.com", "boolean": True,
    }.get(kind, field.get("label") or field["key"])


def _public_base() -> tuple[str, str]:
    from urllib.parse import urlparse

    if config.QMS_PUBLIC_BASE_URL:
        return config.QMS_PUBLIC_BASE_URL.rstrip("/"), "setting"
    wss = urlparse(config.PUBLIC_WSS_BASE or "")
    if wss.netloc:
        return f"{'http' if wss.scheme == 'ws' else 'https'}://{wss.netloc}", "derived"
    return "", ""


def _intake_view(intake: dict) -> dict:
    fields = qms_intakes.all_fields(intake)
    path = "/api/ingestion/calls" if intake["id"] == qms_intakes.ABANDONED_CART else f"/api/qms/{intake['id']}/calls"
    sample = {f["key"]: _example(f) for f in fields if f.get("required") or f.get("required_if")}
    base, _ = _public_base()
    return {
        **intake,
        "allFields": fields,
        "path": path,
        "url": f"{base}{path}" if base else "",
        "method": "POST",
        "connected": bool(intake.get("agent")),
        "samplePayload": sample,
        "sampleResponse": {
            "accepted": 1, "duplicates": 0, "rejected": 0, "failed": 0,
            "results": [{"index": 0, "ingestion_id": 123, "reference_id": qms_intakes.new_reference(intake["id"]),
                         "status": "scheduled", "call_triggered": False,
                         "scheduled_for": "2026-10-14T12:30:10+00:00", "delay_secs": 10.0}],
        },
        "sampleRejection": {
            "accepted": 0, "duplicates": 0, "rejected": 1, "failed": 0,
            "results": [{"index": 0, "ingestion_id": 124, "status": "rejected", "call_triggered": False,
                         "errors": [{"field": "phone_number", "error": "missing"}]}],
        },
        "delayDefault": config.INGESTION_CALL_DELAY_SECS,
        "dedupeDefault": config.INGESTION_DEDUPE_WINDOW_SECS,
        "maxBatch": config.INGESTION_MAX_BATCH,
        "enabledGlobally": config.INGESTION_ENABLED,
    }


@router.get("/qms")
async def qms_sources(_: SessionUser = Depends(require("ingestion.view"))):
    import asyncio

    note = ""
    out = []
    allowed = _client_agents(_)
    for intake in await asyncio.to_thread(qms_intakes.list_intakes):
        if allowed is not None and intake["agent"] not in allowed:
            continue
        agent = await usecases.fetch(intake["agent"]) if intake["agent"] else None
        try:
            counts = await asyncio.to_thread(ingestion_events.counts, source=intake["id"])
            counts["awaiting"] = await asyncio.to_thread(ingestion_events.awaiting_count, intake["id"])
        except DatabaseUnavailable as e:
            counts, note = None, f"the database is unreachable, so the figures cannot be shown: {e}"
        out.append({
            **_intake_view(intake),
            "agentName": (agent or {}).get("name", ""),
            "agentReady": usecases.usable_on(agent, intake.get("channel") or "acefone"),
            "counts": counts,
        })
    base, base_from = _public_base()
    return {
        "sources": out, "persisted": is_db_configured(), "note": note, "fieldTypes": list(qms_intakes.FIELD_TYPES),
        "baseUrl": base, "baseUrlFrom": base_from, "enabled": config.INGESTION_ENABLED,
    }


@router.get("/qms/for-agent/{agent}")
def qms_for_agent(agent: str, _: SessionUser = Depends(require("calls.place"))):
    return {"intakes": [_intake_view(i) for i in qms_intakes.for_agent(agent)]}


@router.get("/qms/catalog")
def qms_catalog(_: SessionUser = Depends(require("usecases.view"))):
    base, base_from = _public_base()
    intakes = [{**_intake_view(i), "awaiting": ingestion_events.awaiting_count(i["id"])} for i in qms_intakes.list_intakes()]
    return {"intakes": intakes, "baseUrl": base, "baseUrlFrom": base_from,
            "delayDefault": config.INGESTION_CALL_DELAY_SECS, "dedupeDefault": config.INGESTION_DEDUPE_WINDOW_SECS}


_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


@router.put("/qms/intakes/{intake_id}/connection")
async def connect_intake(intake_id: str, payload: dict, user: SessionUser = Depends(require("usecases.edit"))):
    import asyncio

    from pw_channel.intake import replay as qms_release

    current = qms_intakes.get(intake_id)
    if current is None:
        raise HTTPException(status_code=404, detail="no such intake")
    agent = str(payload.get("agent") or "").strip()
    start, end = (str(payload.get(k) or "").strip() for k in ("callHoursStart", "callHoursEnd"))
    if bool(start) != bool(end):
        raise HTTPException(status_code=422, detail="set both ends of the calling hours, or neither")
    for value in (start, end):
        if value and not _HHMM.match(value):
            raise HTTPException(status_code=422, detail=f"calling hours: {value!r} is not HH:MM")
    if start and start == end:
        raise HTTPException(status_code=422, detail="calling hours open and close at the same time")
    trigger = {"callHoursStart": start, "callHoursEnd": end}
    for key, top in (("delaySecs", 7 * 86400), ("dedupeWindowSecs", 7 * 86400)):
        value = payload.get(key)
        if value in (None, ""):
            trigger[key] = None
            continue
        try:
            trigger[key] = float(value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail=f"{key} must be a number of seconds")
        if not 0 <= trigger[key] <= top:
            raise HTTPException(status_code=422, detail=f"{key} must be between 0 and {top} seconds")
    pending = str(payload.get("pending") or "").strip()
    if pending not in ("", "call", "hold"):
        raise HTTPException(status_code=422, detail="pending must be call or hold")
    if pending == "call":
        release_after = qms_intakes.EPOCH
    elif pending == "hold" or (agent and agent != current["agent"]):
        release_after = datetime.now(timezone.utc)
    else:
        release_after = qms_intakes.KEEP
    if not agent:
        release_after = None
    saved = await asyncio.to_thread(
        qms_intakes.connect, intake_id, agent=agent, trigger=trigger, actor=user.email, release_after=release_after,
    )
    log_event("qms.intake.connected", intake=intake_id, agent=agent or "-", pending=pending or "-", requested_by=user.email)
    released = None
    if agent and pending == "call":
        released = await qms_release.release(intake_id, actor=user.email)
    return {**_intake_view(saved), "released": released}


@router.post("/qms/intakes/{intake_id}/release")
async def release_intake(intake_id: str, user: SessionUser = Depends(require("calls.place"))):
    from pw_channel.intake import replay as qms_release

    if qms_intakes.get(intake_id) is None:
        raise HTTPException(status_code=404, detail="no such intake")
    result = await qms_release.release(intake_id, actor=user.email)
    if result["reason"]:
        raise HTTPException(status_code=409, detail=f"Not released: {result['reason']}")
    log_event("qms.released", intake=intake_id, released=result["released"], requested_by=user.email)
    return result


def _clean_intake(payload: dict, *, intake_id: str) -> dict:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    reserved = {f["key"] for f in qms_intakes.BASE_FIELDS + qms_intakes.SYSTEM_FIELDS}
    seen, fields = set(), []
    for raw in payload.get("fields") or []:
        key = str(raw.get("key") or "").strip()
        kind = raw.get("type") or "text"
        if not _KEY.match(key):
            raise HTTPException(status_code=422, detail=f"field key {key!r}: lowercase letters, digits and underscores, starting with a letter")
        if key in reserved:
            raise HTTPException(status_code=422, detail=f"{key} is always part of every intake; remove it from the list")
        if key in seen:
            raise HTTPException(status_code=422, detail=f"field {key} appears twice")
        if kind not in qms_intakes.FIELD_TYPES:
            raise HTTPException(status_code=422, detail=f"field {key}: unknown type {kind!r}")
        options = [str(o).strip() for o in raw.get("options") or [] if str(o).strip()]
        if kind == "enum" and not options:
            raise HTTPException(status_code=422, detail=f"field {key}: a choice field needs at least one option")
        seen.add(key)
        field = {
            "key": key, "label": str(raw.get("label") or key.replace("_", " ").capitalize()).strip(),
            "type": kind, "required": bool(raw.get("required")),
            "description": str(raw.get("description") or "").strip(),
        }
        if raw.get("example") not in (None, ""):
            field["example"] = raw["example"]
        if options:
            field["options"] = options
        for bound in ("min", "max"):
            if raw.get(bound) not in (None, ""):
                field[bound] = float(raw[bound])
        if raw.get("future_only"):
            field["future_only"] = True
        cond = raw.get("required_if") or {}
        if cond.get("field") and cond.get("equals") not in (None, ""):
            field["required_if"] = {"field": str(cond["field"]), "equals": str(cond["equals"])}
        fields.append(field)
    for f in fields:
        dep = (f.get("required_if") or {}).get("field")
        if dep and dep not in seen | reserved:
            raise HTTPException(status_code=422, detail=f"field {f['key']}: required_if names {dep}, which is not a field")
    return {
        "id": intake_id, "name": name, "description": str(payload.get("description") or "").strip(),
        "channel": payload.get("channel") or "acefone", "enabled": payload.get("enabled", True) is not False,
        "fields": fields,
    }


@router.post("/qms/intakes", status_code=201)
def create_intake(payload: dict, user: SessionUser = Depends(require("settings.edit"))):
    intake_id = str(payload.get("id") or "").strip().lower()
    if not _INTAKE_ID.match(intake_id):
        raise HTTPException(status_code=422, detail="identifier: 3 to 41 lowercase letters, digits or underscores, starting with a letter")
    if intake_id == qms.PHONE_TEST or qms_intakes.get(intake_id):
        raise HTTPException(status_code=409, detail=f"an intake called {intake_id} already exists")
    saved = qms_intakes.save(_clean_intake(payload, intake_id=intake_id), actor=user.email, create=True)
    token = qms_intakes.rotate_token(intake_id, actor=user.email)
    log_event("qms.intake.created", intake=intake_id, requested_by=user.email)
    return {"intake": _intake_view(qms_intakes.get(intake_id) or saved), "token": token}


@router.put("/qms/intakes/{intake_id}")
def update_intake(intake_id: str, payload: dict, user: SessionUser = Depends(require("settings.edit"))):
    current = qms_intakes.get(intake_id)
    if current is None:
        raise HTTPException(status_code=404, detail="no such intake")
    cleaned = _clean_intake({**current, **payload}, intake_id=intake_id)
    if current["kind"] == "cart":
        cleaned["fields"] = current["fields"]
    saved = qms_intakes.save(cleaned, actor=user.email, create=False)
    log_event("qms.intake.updated", intake=intake_id, requested_by=user.email)
    return _intake_view(saved)


@router.post("/qms/intakes/{intake_id}/token")
def new_intake_token(intake_id: str, user: SessionUser = Depends(require("settings.edit"))):
    if qms_intakes.get(intake_id) is None:
        raise HTTPException(status_code=404, detail="no such intake")
    token = qms_intakes.rotate_token(intake_id, actor=user.email)
    log_event("qms.intake.token", intake=intake_id, requested_by=user.email)
    return {"token": token}


@router.delete("/qms/intakes/{intake_id}", status_code=204)
def delete_intake(intake_id: str, user: SessionUser = Depends(require("settings.edit"))):
    current = qms_intakes.get(intake_id)
    if current is None:
        raise HTTPException(status_code=404, detail="no such intake")
    if current["builtin"]:
        raise HTTPException(status_code=409, detail="the built-in intake cannot be deleted; switch it off instead")
    qms_intakes.delete(intake_id)
    log_event("qms.intake.deleted", intake=intake_id, requested_by=user.email)
    from fastapi import Response

    return Response(status_code=204)


@router.post("/test-records")
async def create_test_record(payload: dict, user: SessionUser = Depends(require("calls.place"))):
    import secrets as _secrets

    from datetime import datetime, timezone

    from pw_channel.core import records
    from pw_channel.core.target import CallTarget
    from pw_channel.intake import service as intake_service

    intake = qms_intakes.get(str(payload.get("intake") or ""))
    if intake is None:
        raise HTTPException(status_code=404, detail="no such intake")
    record = dict(payload.get("record") or {})
    reference = f"TEST-{_secrets.token_hex(6).upper()}"
    record["reference_id"] = reference
    record.setdefault("phone_number", "9999999999")
    try:
        result, _ = await intake_service.transform(intake, record, "records", datetime.now(timezone.utc))
    except Exception as e:
        raise HTTPException(status_code=422, detail={"message": f"The adapter could not read this record: {e}", "errors": []})
    if not result.items:
        errors = [{"field": r.field or "", "error": r.error} for r in result.rejections]
        raise HTTPException(status_code=422, detail={"message": "Fill in: " + "; ".join(f"{e['field']} {e['error']}" for e in errors), "errors": errors})
    target = CallTarget(record=result.items[0].value, intake=intake["id"], agent=str(payload.get("agent") or intake["agent"]))
    records.save(target)
    log_event("qms.test_record", intake=intake["id"], reference_id=target.reference_id, requested_by=user.email)
    return {"testRecord": target.reference_id, "facts": target.facts}


@router.get("/history")
def call_history(
    limit: int = 200,
    status: str = "",
    q: str = "",
    agent: str = "",
    source: str = "",
    _: SessionUser = Depends(require("ingestion.view")),
):
    if status and status not in ingestion_events.STATUSES:
        raise HTTPException(status_code=400, detail=f"unknown status {status!r}")
    allowed = _client_agents(_)
    if allowed is not None and agent and agent not in allowed:
        raise HTTPException(status_code=404, detail=f"no agent {agent!r}")
    try:
        events = ingestion_events.recent(limit=limit, status=status, q=q.strip(), agent=agent, source=source)
        counts = ingestion_events.counts(agent=agent, source=source)
        agents = ingestion_events.agents_seen()
        if allowed is not None and not agent:
            events = [e for e in events if e.get("agent") in allowed]
            agents = [a for a in agents if (a.get("agent") if isinstance(a, dict) else a) in allowed]
            per_agent = [ingestion_events.counts(agent=a, source=source) for a in sorted(allowed)]
            counts = {k: sum(c.get(k) or 0 for c in per_agent) for k in counts if k != "lastAt"}
            counts["lastAt"] = max((c["lastAt"] for c in per_agent if c.get("lastAt")), default=None)
        note = ""
    except DatabaseUnavailable as e:
        events, counts, agents = [], None, []
        note = f"the database is unreachable, so persisted records cannot be shown: {e}"
    for event in events:
        event["sourceLabel"] = qms.label(event["source"])
    return {
        "events": events,
        "counts": counts,
        "agents": agents,
        "sources": [{"id": k, "label": v} for k, v in qms.labels().items()],
        "persisted": is_db_configured(),
        "note": note,
    }


@router.get("/ingestion/{event_id}")
def ingestion_event(event_id: int, _: SessionUser = Depends(require("ingestion.view"))):
    try:
        event = ingestion_events.get(event_id)
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    if event is None:
        raise HTTPException(status_code=404, detail="no such ingestion record")
    event["sourceLabel"] = qms.label(event["source"])
    return event


def _call_bundle(event_id: int) -> dict:
    from pw_channel.db import call_records
    from pw_channel.db import call_sessions
    from pw_channel.db import call_transcripts

    event = ingestion_events.get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="no such record")
    event["sourceLabel"] = qms.label(event["source"])
    record = session = None
    transcript: list = []
    if event.get("callRecordId") and is_db_configured():
        record = call_records.get(event["callRecordId"])
        session = call_sessions.by_call_record(event["callRecordId"])
        if session:
            transcript = call_transcripts.for_session(session["id"], limit=500)
    summary = None
    if record and record.get("summary"):
        try:
            summary = json.loads(record["summary"])
        except ValueError:
            summary = {"summary": record["summary"]}
        summary["at"] = record.get("summaryAt")
    return {"event": event, "record": record, "session": session, "transcript": transcript, "summary": summary}


@router.get("/history/{event_id}/call")
def call_detail(event_id: int, _: SessionUser = Depends(require("ingestion.view"))):
    try:
        return _call_bundle(event_id)
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/history/{event_id}/summary")
async def call_summary(event_id: int, refresh: bool = False, _: SessionUser = Depends(require("ingestion.view"))):
    import asyncio

    from pw_channel.db import call_records
    from pw_channel.admin.usecases import _brain

    bundle = await asyncio.to_thread(_call_bundle, event_id)
    if bundle["summary"] and not refresh:
        return bundle["summary"]
    if not bundle["record"] or not bundle["transcript"]:
        raise HTTPException(status_code=409, detail="this call has no conversation to summarise")
    record = bundle["record"]
    result = await _brain("POST", "/calls/summarize", json={
        "messages": [{"role": "user" if _is_customer(m["role"]) else "assistant", "text": m["text"]} for m in bundle["transcript"]],
        "agent": bundle["event"].get("agent"),
        "customer_name": record.get("customerName"),
        "reference_id": record.get("referenceId"),
        "ended_reason": record.get("endedReason"),
    }, timeout=45.0)
    await asyncio.to_thread(call_records.set_summary, record["id"], json.dumps(result, ensure_ascii=False))
    return {**result, "at": None}


@router.post("/ingestion/{event_id}/retry")
async def retry_ingestion_call(event_id: int, user: SessionUser = Depends(require("calls.place"))):
    import asyncio

    from pw_channel.intake.replay import replay_event

    event = await asyncio.to_thread(ingestion_events.get, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="no such ingestion record")
    if event["status"] not in ("failed", "rejected"):
        raise HTTPException(status_code=409, detail=f"only failed or rejected records can be retried; this one is {event['status']}")
    result = await replay_event(event, user.email)
    log_event("ingestion.retried", ingestion_id=event_id, new_id=result.get("ingestion_id"),
              status=result["status"], requested_by=user.email)
    if result["status"] not in ("scheduled", "merged"):
        errors = result.get("errors") or []
        detail = (
            "Not scheduled. " + "; ".join(f"{e['field'] or 'record'} {e['error']}" for e in errors)
            if errors else f"Not scheduled: {result.get('reason', result['status'])}"
        )
        raise HTTPException(status_code=422, detail={"message": detail, "errors": errors, "ingestionId": result.get("ingestion_id")})
    return {"ingestionId": result["ingestion_id"], "message": f"Retry scheduled as #{result['ingestion_id']}"}


@router.post("/ingestion/{event_id}/cancel")
async def cancel_ingestion_call(event_id: int, user: SessionUser = Depends(require("ingestion.cancel"))):
    import asyncio

    from pw_channel.intake.replay import cancel_journey_of

    event = await asyncio.to_thread(ingestion_events.get, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="no such ingestion record")
    if event["status"] != "scheduled":
        raise HTTPException(status_code=409, detail=f"this call is {event['status']}, not scheduled")
    if not await asyncio.to_thread(cancel_journey_of, event, user.email):
        raise HTTPException(
            status_code=409,
            detail="There are no pending steps left to cancel for this record",
        )
    await asyncio.to_thread(
        ingestion_events.update, event_id, status="cancelled", reason=f"cancelled by {user.email}"
    )
    log_event("ingestion.cancelled", ingestion_id=event_id, requested_by=user.email)
    return await asyncio.to_thread(ingestion_events.get, event_id)
