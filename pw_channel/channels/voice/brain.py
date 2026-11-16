import logging
import re
from dataclasses import dataclass, field

import httpx

from pw_channel import config
from pw_channel.channels.voice import usecases
from pw_sdk.utils.http import base_url

logger = logging.getLogger(__name__)

_FRIENDLY_RULE = re.compile(r"<FRIENDLY_TEXT>(.*?)</FRIENDLY_TEXT>", re.DOTALL | re.IGNORECASE)
_TAG_RULE = re.compile(r"<[^>]+>")
_BLANK_LINES_RULE = re.compile(r"\n{2,}")

KNOWN_ACTIONS = frozenset(
    {
        "transfer_to_agent",
        "end_call",
        "switch_language",
        "log_disposition",
        "send_booking_link",
    }
)

_client: httpx.AsyncClient | None = None


class PWChatError(Exception):
    pass


@dataclass(frozen=True)
class VoiceAction:
    action_id: str
    type: str
    params: dict = field(default_factory=dict)
    execute_after_speech: bool = True
    turn_id: str = ""


@dataclass(frozen=True)
class PWChatReply:
    response_text: str
    response_html: str
    result_id: str
    spoken_text: str
    handoff_main_menu: bool
    handoff_agent: bool
    latency_ms: int
    action: VoiceAction | None = None
    diagnostics: dict = field(default_factory=dict)


def spoken_text(response_text: str) -> str:
    match = _FRIENDLY_RULE.search(response_text or "")
    raw = match.group(1) if match else (response_text or "")
    stripped = _TAG_RULE.sub(" ", raw)
    return _BLANK_LINES_RULE.sub("\n", stripped).strip()


def read_timeout_for(user_type: str) -> float:
    if usecases.is_phone(user_type):
        return config.PW_CHAT_PHONE_READ_TIMEOUT_SECS
    return config.PW_CHAT_READ_TIMEOUT_SECS


def hold_delay_for(user_type: str) -> float:
    if usecases.is_phone(user_type):
        return config.PW_CHAT_PHONE_HOLD_DELAY_SECS
    return config.PW_CHAT_HOLD_DELAY_SECS


def second_hold_for(user_type: str) -> float:
    if usecases.is_phone(user_type):
        return config.PW_CHAT_PHONE_SECOND_HOLD_SECS
    return config.PW_CHAT_SECOND_HOLD_SECS


def _timeout(user_type: str) -> httpx.Timeout:
    return httpx.Timeout(
        connect=config.PW_CHAT_CONNECT_TIMEOUT_SECS,
        read=read_timeout_for(user_type),
        write=5.0,
        pool=5.0,
    )


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=_timeout(config.PW_CHAT_USER_TYPE_PHONE),
            limits=httpx.Limits(
                max_keepalive_connections=8,
                max_connections=16,
                keepalive_expiry=60.0,
            ),
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


def _headers() -> dict:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if config.PW_CHAT_API_TOKEN:
        headers["X-Api-Token"] = config.PW_CHAT_API_TOKEN
    return headers


def _parse_action(raw, turn_id: str) -> VoiceAction | None:
    if not raw:
        return None
    if raw is True:
        return None
    if not isinstance(raw, dict):
        logger.warning(f"[pw_chat] voice_action was {type(raw).__name__}, ignoring")
        return None

    action_type = raw.get("type")
    if not isinstance(action_type, str) or not action_type:
        logger.warning("[pw_chat] voice_action carried no type, ignoring")
        return None

    if action_type not in KNOWN_ACTIONS:
        logger.warning(
            f"[pw_chat] voice_action type={action_type!r} is not one this pipeline "
            "knows how to run - ignoring it"
        )
        return None

    params = raw.get("params")
    if not isinstance(params, dict):
        params = {}

    action_id = raw.get("action_id") or f"{turn_id}:{action_type}"

    return VoiceAction(
        action_id=str(action_id),
        type=action_type,
        params=params,
        execute_after_speech=bool(raw.get("execute_after_speech", True)),
        turn_id=str(raw.get("turn_id") or turn_id),
    )


def _parse(response: httpx.Response, elapsed_ms: int, turn_id: str) -> PWChatReply:
    try:
        body = response.json()
    except ValueError:
        raise PWChatError(f"reply was not JSON (HTTP {response.status_code})")

    if not isinstance(body, dict):
        raise PWChatError(f"reply was {type(body).__name__}, expected an object")

    diagnostics = body.get("voice_diagnostics")
    if not isinstance(diagnostics, dict):
        diagnostics = {}

    response_text = body.get("response_text")
    if not isinstance(response_text, str) or not response_text.strip():
        raise PWChatError("reply carried no response_text")

    response_html = body.get("response_html") or ""
    if not isinstance(response_html, str):
        response_html = ""

    result_id = body.get("result_id") or ""
    if not isinstance(result_id, str):
        result_id = ""

    reply = PWChatReply(
        response_text=response_text,
        response_html=response_html,
        result_id=result_id,
        spoken_text=spoken_text(response_text),
        handoff_main_menu=bool(body.get("handoffToMainMenu")),
        handoff_agent=bool(body.get("handoffToCustomerAgent")),
        latency_ms=elapsed_ms,
        action=_parse_action(body.get("voice_action"), turn_id),
        diagnostics=diagnostics,
    )
    logger.debug(f"[pw_chat] remote session_id={body.get('session_id', '')}")
    return reply


async def chat(
    *,
    session_id: str,
    message: str,
    user_type: str,
    turn_id: str = "",
    turn_kind: str = "user",
    turn_reason: str = "",
    assistant_prefix: str = "",
    already_said: list | None = None,
    voice_context: dict | None = None,
    last_action_ack: dict | None = None,
    deadline_ms: int | None = None,
) -> PWChatReply:
    if not config.PW_CHAT_ENABLED:
        raise PWChatError("PW_CHAT_ENABLED is off")

    turn = {"turn_id": turn_id, "turn_kind": turn_kind}
    if turn_reason:
        turn["turn_reason"] = turn_reason
    if assistant_prefix:
        turn["assistant_prefix"] = assistant_prefix
    if already_said:
        turn["already_said"] = list(already_said)
    if last_action_ack:
        turn["last_action_ack"] = last_action_ack
    if deadline_ms:
        turn["client_deadline_ms"] = deadline_ms

    payload = {
        "session_id": session_id,
        "message": message,
        "user_type": user_type,
        "turn": turn,
    }
    if voice_context is not None:
        payload["voice_context"] = voice_context

    context_bytes = len(str(voice_context or ""))
    logger.info(
        f"[pw_chat] POST user_type={user_type} turn_kind={turn_kind} turn_id={turn_id!r} "
        f"session_id={session_id} ctx_bytes={context_bytes} chars={len(message or '')}"
    )

    last_error: Exception | None = None
    client = _get_client()
    timeout = _timeout(user_type)

    for attempt in range(1, config.PW_CHAT_MAX_ATTEMPTS + 1):
        try:
            response = await client.post(
                config.PW_CHAT_API_URL, json=payload, headers=_headers(), timeout=timeout
            )
            elapsed_ms = int(response.elapsed.total_seconds() * 1000)

            if response.status_code >= 500:
                last_error = PWChatError(f"chatbot API returned HTTP {response.status_code}")
            elif response.status_code >= 400:
                raise PWChatError(
                    f"chatbot API rejected the turn (HTTP {response.status_code})"
                )
            else:
                reply = _parse(response, elapsed_ms, turn_id)
                logger.info(
                    f"[pw_chat] reply session_id={session_id} latency_ms={elapsed_ms} "
                    f"spoken={len(reply.spoken_text)}chars "
                    f"html={len(reply.response_html)}bytes "
                    f"handoff_agent={reply.handoff_agent} "
                    f"action={reply.action.type if reply.action else 'none'} "
                    f"diagnostics={reply.diagnostics or '{}'} attempt={attempt}"
                )
                return reply
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            last_error = e
        except httpx.ReadTimeout as e:
            logger.warning(
                f"[pw_chat] read timed out after {read_timeout_for(user_type)}s "
                f"session_id={session_id} — not retried"
            )
            raise PWChatError(f"chatbot API did not answer in time ({e.__class__.__name__})")
        except httpx.HTTPError as e:
            raise PWChatError(f"{e.__class__.__name__}: {e}")

        logger.warning(
            f"[pw_chat] attempt {attempt}/{config.PW_CHAT_MAX_ATTEMPTS} failed "
            f"session_id={session_id}: {last_error}"
        )

    raise PWChatError(str(last_error))


async def greeting(
    *, session_id: str, user_type: str, voice_context: dict | None = None
) -> str:
    if not config.PW_CHAT_ENABLED:
        raise PWChatError("PW_CHAT_ENABLED is off")

    url = base_url(config.PW_CHAT_API_URL) + "/greeting"
    payload = {"session_id": session_id, "user_type": user_type}
    if voice_context is not None:
        payload["voice_context"] = voice_context

    client = _get_client()
    response = await client.post(url, json=payload, headers=_headers())
    if response.status_code >= 400:
        raise PWChatError(f"greeting endpoint returned HTTP {response.status_code}")

    body = response.json()
    if not isinstance(body, dict):
        raise PWChatError("greeting reply was not an object")

    text = body.get("greeting_text") or ""
    logger.info(
        f"[pw_chat] greeting session_id={session_id} chars={len(text)} "
        f"already_greeted={body.get('already_greeted')}"
    )
    return text
