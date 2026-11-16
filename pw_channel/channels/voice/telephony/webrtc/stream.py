import logging

from fastapi import WebSocket

from pipecat.transports.websocket.fastapi import FastAPIWebsocketTransport

from pw_channel import config
from pw_channel.channels.voice import usecases
from pw_channel.channels.voice.telephony.common import (
    CallContext,
    build_websocket_params,
    mint_chat_session_id,
    run_voice_pipeline,
    voice_user_type,
)
from pw_channel.channels.voice.processors.result_surface import BrowserResultSurface
from pw_channel.channels.voice.processors.transcript_relay import TranscriptRelayProcessor
from pw_channel.channels.voice.telephony.webrtc.serializer import RawPCMFrameSerializer

logger = logging.getLogger(__name__)


SAMPLE_RATES = (8000, 16000, 22050, 24000, 44100, 48000)


TEST_RECORD_PREFIX = "TEST-"


async def handle_website_websocket(
    websocket: WebSocket,
    *,
    session_id: str | None,
    sample_rate: int | None = None,
    tts_overrides: dict | None = None,
    use_case: str | None = None,
    test_record: str | None = None,
) -> None:
    await websocket.accept()

    user_type = voice_user_type("website")
    if use_case and use_case != user_type:
        if usecases.usable_on(await usecases.fetch(use_case), "website"):
            user_type = use_case
        else:
            logger.warning(f"[website] use_case {use_case!r} is not enabled for the website — using {user_type!r}")

    out_rate = sample_rate if sample_rate in SAMPLE_RATES else config.WEBSITE_SAMPLE_RATE

    pw_session_id = mint_chat_session_id(user_type)
    logger.info(
        f"[website] session started session_id={session_id} "
        f"pw_session_id={pw_session_id} out_rate={out_rate} "
        f"tts={tts_overrides or 'configured default'}"
    )

    serializer = RawPCMFrameSerializer(
        params=RawPCMFrameSerializer.InputParams(client_sample_rate=out_rate)
    )

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=build_websocket_params(serializer),
    )

    call_context = CallContext(
        reference_id=session_id or "",
        channel="website",
        language=config.DEFAULT_LANGUAGE,
    )
    if test_record and test_record.startswith(TEST_RECORD_PREFIX):
        call_context.booking_reference_id = test_record

    await run_voice_pipeline(
        transport,
        call_context,
        audio_in_sample_rate=config.WEBSITE_PIPELINE_SAMPLE_RATE,
        audio_out_sample_rate=out_rate,
        tts_overrides=tts_overrides,
        user_type=user_type,
        chat_session_id=pw_session_id,
        surface=BrowserResultSurface(websocket),
        enforce_max_duration=False,
        auto_end_session=False,
        post_stt_processors=[
            TranscriptRelayProcessor(
                websocket, relay_user=True, relay_bot=False, relay_text=False
            )
        ],
        post_llm_processors=[
            TranscriptRelayProcessor(
                websocket, relay_user=False, relay_bot=True, relay_text=False
            )
        ],
    )
