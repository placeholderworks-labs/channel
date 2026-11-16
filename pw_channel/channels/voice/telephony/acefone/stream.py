import json
import logging
import time

from fastapi import WebSocket

from pipecat_acefone import AcefoneFrameSerializer, AcefoneMediaFormat
from pipecat.transports.websocket.fastapi import FastAPIWebsocketTransport

from pw_channel import config
from pw_channel.core import records
from pw_channel.observability import bind_call
from pw_channel.channels.voice.telephony.common import (
    CallContext,
    build_websocket_params,
    mint_chat_session_id,
    run_voice_pipeline,
    voice_user_type,
)
from pw_channel.channels.voice.telephony.acefone.serializer import PwAcefoneFrameSerializer
from pw_channel.channels.voice.states import PendingCall, TransferHandle
from pw_channel.channels.voice.telephony import lifecycle as call_lifecycle
from pw_channel.channels.voice.telephony.tracker import note_websocket_connected
from pw_channel.channels.voice.telephony.acefone.ids import call_id_of as acefone_call_id
from pw_channel.channels.voice.telephony.acefone.ids import decode_custom_identifier as decode_acefone_custom_identifier
from pw_sdk.utils.phone import last10

logger = logging.getLogger(__name__)

_MEDIA_FORMATS = {
    "ulaw": AcefoneMediaFormat.ULAW,
    "pcm": AcefoneMediaFormat.PCM,
}


def _extract_custom_params(start: dict, data: dict) -> dict:
    raw = (
        start.get("customParameters")
        or start.get("custom_parameters")
        or data.get("customParameters")
        or data.get("custom_parameters")
        or {}
    )
    return raw if isinstance(raw, dict) else {}


def _bare_key_identifier(custom_params: dict) -> str:
    if len(custom_params) != 1:
        return ""
    key, value = next(iter(custom_params.items()))
    return key if not value else ""


def _origination_ref_id(pending: PendingCall | None, customer_number: str) -> str:
    if pending is None or not pending.ref_id or pending.ref_id == "unknown":
        return ""

    if last10(pending.phone_no) != last10(customer_number):
        logger.warning(
            f"[acefone] ref_id={pending.ref_id} was originated for "
            f"{pending.phone_no} but this call is with {customer_number} — "
            f"not using it to identify the call"
        )
        return ""

    return pending.ref_id


def _armed_did() -> str:
    if not config.ENABLE_CALL_TRANSFER:
        return ""
    if not (config.CALL_TRANSFER_NUMBER and config.ACEFONE_AUTH_TOKEN):
        return ""
    return config.CALL_TRANSFER_NUMBER


def _build_transfer_handle(
    *,
    call_sid: str,
    ref_id: str,
    serializer: PwAcefoneFrameSerializer,
    session_row_id: int | None = None,
) -> TransferHandle | None:
    if not config.ENABLE_CALL_TRANSFER:
        logger.info("[acefone] call transfer off (ENABLE_CALL_TRANSFER=false)")
        return None

    missing = [
        key
        for key, value in (
            ("CALL_TRANSFER_NUMBER", config.CALL_TRANSFER_NUMBER),
            ("ACEFONE_AUTH_TOKEN", config.ACEFONE_AUTH_TOKEN),
        )
        if not value
    ]
    if missing:
        logger.warning(
            f"[acefone] call transfer unavailable — {', '.join(missing)} not set"
        )
        return None

    handle = TransferHandle(
        call_id=acefone_call_id(call_sid),
        ref_id=ref_id,
        destination=config.CALL_TRANSFER_NUMBER,
        on_transferred=lambda: serializer.disable_auto_hang_up("call transferred"),
        session_row_id=session_row_id,
    )
    logger.info(
        f"[acefone] call transfer ready destination={handle.destination} "
        f"call_id={handle.call_id!r} (from call_sid={call_sid!r}) "
        f"ref_id={handle.ref_id!r}"
    )
    return handle


async def handle_acefone_websocket(websocket: WebSocket) -> None:
    await websocket.accept()

    connected_at = time.monotonic()
    origination = note_websocket_connected()

    stream_sid = None
    call_sid = None
    from_number = ""
    to_number = ""
    direction = ""
    booking_reference_id = ""
    customer_name = ""
    reported_encoding = ""
    reported_sample_rate = 0
    frames_before_start = 0

    while stream_sid is None:
        raw = await websocket.receive()
        elapsed_ms = (time.monotonic() - connected_at) * 1000

        if raw.get("type") == "websocket.disconnect":
            logger.warning(
                f"[acefone] Acefone CLOSED the socket before sending a start event "
                f"after {elapsed_ms:.0f}ms (close_code={raw.get('code')}, "
                f"frames_received={frames_before_start}). "
                f"We never closed it — this was initiated by Acefone. "
                f"Usually means the API key's destination is not pointed at the "
                f"streaming endpoint."
            )
            return

        frames_before_start += 1
        message = raw.get("text")
        if message is None:
            payload = raw.get("bytes")
            if payload is None:
                continue
            message = payload.decode("utf-8", "replace")

        try:
            data = json.loads(message)
        except ValueError:
            logger.warning("[acefone] pre-start message was not JSON, ignoring")
            continue
        if not isinstance(data, dict):
            continue

        event = data.get("event")

        if event == "start":
            start = data.get("start") or {}
            stream_sid = (
                data.get("streamSid")
                or data.get("stream_sid")
                or start.get("streamSid")
                or start.get("stream_sid")
            )
            call_sid = (
                data.get("call_sid")
                or data.get("callSid")
                or start.get("call_sid")
                or start.get("callSid")
            )
            from_number = (
                start.get("from")
                or start.get("From")
                or data.get("from")
                or data.get("caller_id_number")
                or ""
            )
            to_number = start.get("to") or start.get("To") or data.get("to") or ""
            direction = start.get("direction") or data.get("direction") or ""

            bind_call(call_id=call_sid or stream_sid or None, session_id=stream_sid or None)

            media_meta = start.get("mediaFormat") or start.get("media_format") or {}
            if isinstance(media_meta, dict):
                reported_encoding = str(media_meta.get("encoding") or "").lower()
                try:
                    reported_sample_rate = int(media_meta.get("sampleRate") or 0)
                except (TypeError, ValueError):
                    reported_sample_rate = 0

            custom_params = _extract_custom_params(start, data)
            booking_reference_id = custom_params.get("reference_id") or ""
            customer_name = custom_params.get("name") or ""

            if not booking_reference_id:
                identifier = (
                    custom_params.get("custom_identifier")
                    or start.get("custom_identifier")
                    or data.get("custom_identifier")
                    or _bare_key_identifier(custom_params)
                )
                if identifier:
                    booking_reference_id, decoded_name = (
                        decode_acefone_custom_identifier(identifier)
                    )
                    customer_name = customer_name or decoded_name

            if stream_sid is None:
                logger.warning(f"[acefone] start event carried no streamSid: {message}")
        elif event == "connected":
            continue
        else:
            logger.warning(f"[acefone] unexpected pre-start event: {event}")


    if str(direction).lower() == "outbound":
        customer_number = to_number or from_number
    else:
        customer_number = from_number or to_number

    logger.info(
        f"[acefone] call started stream_sid={stream_sid} call_sid={call_sid} "
        f"from={from_number} to={to_number} direction={direction} "
        f"customer_number={customer_number} "
        f"booking_reference_id={booking_reference_id} customer_name={customer_name}"
    )

    origination_ref_id = _origination_ref_id(origination, customer_number)
    session_row_id = call_lifecycle.answered(
        ref_id=origination_ref_id,
        call_id=acefone_call_id(call_sid or ""),
        customer_number=customer_number,
        booking_reference_id=booking_reference_id,
        customer_name=customer_name,
        direction=direction,
        did=_armed_did(),
    )

    media_format = _MEDIA_FORMATS[config.ACEFONE_MEDIA_FORMAT]
    sample_rate = config.ACEFONE_SAMPLE_RATE
    if reported_encoding:
        if "mulaw" in reported_encoding or "pcmu" in reported_encoding:
            media_format = AcefoneMediaFormat.ULAW
        elif "l16" in reported_encoding or "slin" in reported_encoding:
            media_format = AcefoneMediaFormat.PCM
        else:
            logger.warning(
                f"[acefone] unrecognised mediaFormat encoding {reported_encoding!r} — "
                f"falling back to ACEFONE_MEDIA_FORMAT={config.ACEFONE_MEDIA_FORMAT}"
            )
    if reported_sample_rate:
        sample_rate = reported_sample_rate
    if media_format is not _MEDIA_FORMATS[config.ACEFONE_MEDIA_FORMAT] or (
        sample_rate != config.ACEFONE_SAMPLE_RATE
    ):
        logger.warning(
            f"[acefone] start event advertised encoding={reported_encoding!r} "
            f"sampleRate={reported_sample_rate} — using those over env "
            f"({config.ACEFONE_MEDIA_FORMAT}/{config.ACEFONE_SAMPLE_RATE})"
        )

    auto_hang_up = config.ACEFONE_AUTO_HANG_UP and bool(call_sid)
    if config.ACEFONE_AUTO_HANG_UP and not call_sid:
        logger.warning(
            "[acefone] auto hang-up disabled for this call — no call_sid on start event"
        )

    serializer = PwAcefoneFrameSerializer(
        AcefoneFrameSerializer.InputParams(
            stream_sid=stream_sid,
            call_sid=call_sid,
            auto_hang_up=auto_hang_up,
            media_format=media_format,
            acefone_sample_rate=sample_rate,
        )
    )

    logger.info(
        f"[acefone] pipeline config | media_format={media_format} "
        f"sample_rate={sample_rate} auto_hang_up={auto_hang_up} "
        f"out_10ms_chunks={config.ACEFONE_OUT_10MS_CHUNKS} "
        f"(={config.ACEFONE_OUT_10MS_CHUNKS * 10}ms per media message)"
    )

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=build_websocket_params(
            serializer,
            audio_out_10ms_chunks=config.ACEFONE_OUT_10MS_CHUNKS,
        ),
    )

    call_context = CallContext(
        reference_id=call_sid or stream_sid,
        booking_reference_id=booking_reference_id,
        customer_name=customer_name,
        phone_number=customer_number,
        channel="acefone",
        language=config.DEFAULT_LANGUAGE,
    )

    try:
        target = records.get(reference_id=booking_reference_id, phone_number=call_context.phone_number)
        user_type = (target.agent if target else "") or voice_user_type("acefone")
        await run_voice_pipeline(
            transport,
            call_context,
            audio_in_sample_rate=sample_rate,
            audio_out_sample_rate=sample_rate,
            user_type=user_type,
            chat_session_id=mint_chat_session_id(
                user_type, phone_number=call_context.phone_number
            ),
            transfer=_build_transfer_handle(
                call_sid=call_sid or "",
                ref_id=origination_ref_id,
                serializer=serializer,
                session_row_id=session_row_id,
            ),
            session_row_id=session_row_id,
        )
    finally:
        call_lifecycle.bot_leg_closed(session_row_id, reason="websocket_closed")
        logger.info(
            f"[acefone] call ENDED stream_sid={stream_sid} "
            f"duration={time.monotonic() - connected_at:.1f}s "
            f"inbound_media={serializer.inbound_media_count} "
            f"outbound_media={serializer.outbound_media_count}"
        )
        if serializer.inbound_media_count == 0:
            logger.warning(
                "[acefone] no inbound media for the whole call — Acefone never "
                "streamed the caller's audio to us, so STT had nothing to hear"
            )
