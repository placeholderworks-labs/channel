import base64
import json
import logging

from pipecat.frames.frames import AudioRawFrame, EndFrame, Frame, InterruptionFrame
from pipecat_acefone import AcefoneFrameSerializer

logger = logging.getLogger(__name__)


class PwAcefoneFrameSerializer(AcefoneFrameSerializer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._chunk = 0
        self._in_media_count = 0
        self._out_media_count = 0
        self._logged_first_in = False
        self._logged_first_out = False

    def disable_auto_hang_up(self, reason: str) -> None:
        if self._params.auto_hang_up:
            self._params.auto_hang_up = False
            logger.info(f"[acefone] auto hang-up disabled: {reason}")

    @property
    def inbound_media_count(self) -> int:
        return self._in_media_count

    @property
    def outbound_media_count(self) -> int:
        return self._out_media_count

    async def serialize(self, frame: Frame) -> str | bytes | None:
        payload = await super().serialize(frame)

        if isinstance(frame, InterruptionFrame):
            self._chunk = 0
            return payload

        if payload and isinstance(frame, AudioRawFrame) and isinstance(payload, str):
            try:
                message = json.loads(payload)
            except ValueError:
                return payload
            if message.get("event") == "media":
                self._chunk += 1
                message["media"]["chunk"] = self._chunk
                self._out_media_count += 1

                if not self._logged_first_out:
                    self._logged_first_out = True
                    wire_bytes = len(base64.b64decode(message["media"]["payload"]))
                    logger.info(
                        f"[acefone] first outbound media: wire_bytes={wire_bytes} "
                        f"multiple_of_160={wire_bytes % 160 == 0} "
                        f"format={self._params.media_format} "
                        f"rate={self._acefone_sample_rate}"
                    )

                return json.dumps(message)

        return payload

    async def deserialize(self, data: str | bytes) -> Frame | None:
        try:
            message = json.loads(data)
        except (ValueError, TypeError):
            logger.warning("[acefone] dropping non-JSON inbound message")
            return None

        if not isinstance(message, dict) or "event" not in message:
            logger.warning(
                f"[acefone] inbound message without an 'event' key, ignoring: "
                f"{str(message)[:200]}"
            )
            return None

        event = message["event"]

        if event == "stop":
            reason = (message.get("stop") or {}).get("reason") or "stream stopped"
            logger.info(
                f"[acefone] STOP event: {reason} | inbound_media={self._in_media_count} "
                f"outbound_media={self._out_media_count}"
            )
            return EndFrame()

        if event == "mark":
            return None

        if event == "media":
            self._in_media_count += 1
            if not self._logged_first_in:
                self._logged_first_in = True
                raw = message.get("media", {}).get("payload") or ""
                try:
                    wire_bytes = len(base64.b64decode(raw))
                except Exception:
                    wire_bytes = -1
                logger.info(
                    f"[acefone] first inbound media: wire_bytes={wire_bytes} "
                    f"— caller audio is reaching us"
                )
        elif event not in ("connected", "start", "dtmf"):
            logger.info(f"[acefone] unhandled inbound event {event!r}")

        return await super().deserialize(data)
