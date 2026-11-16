import logging

from pipecat.frames.frames import CancelFrame, EndFrame, Frame, InputAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

logger = logging.getLogger(__name__)

_TOLERANCE = 0.15


class AudioRechunkerProcessor(FrameProcessor):
    def __init__(self, *, target_ms: int, **kwargs):
        super().__init__(**kwargs)
        self._target_ms = target_ms
        self._buffer = bytearray()
        self._sample_rate = 0
        self._num_channels = 0
        self._target_bytes = 0
        self._passthrough = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, InputAudioRawFrame) and direction == FrameDirection.DOWNSTREAM:
            await self._handle_audio(frame)
            return

        if isinstance(frame, (EndFrame, CancelFrame)):
            await self._flush()

        await self.push_frame(frame, direction)

    async def _handle_audio(self, frame: InputAudioRawFrame) -> None:
        if frame.sample_rate != self._sample_rate or frame.num_channels != self._num_channels:
            await self._flush()
            self._sample_rate = frame.sample_rate
            self._num_channels = frame.num_channels
            bytes_per_sec = frame.sample_rate * frame.num_channels * 2
            self._target_bytes = int(bytes_per_sec * self._target_ms / 1000)
            incoming_ms = len(frame.audio) * 1000 / bytes_per_sec if bytes_per_sec else 0.0
            self._passthrough = (
                abs(incoming_ms - self._target_ms) <= self._target_ms * _TOLERANCE
            )
            logger.info(
                f"[rechunk] in={incoming_ms:.1f}ms target={self._target_ms}ms "
                f"({self._target_bytes}B @ {frame.sample_rate}Hz) "
                + ("passthrough" if self._passthrough else "rechunking")
            )

        if self._passthrough or self._target_bytes <= 0:
            await self.push_frame(frame)
            return

        self._buffer.extend(frame.audio)
        while len(self._buffer) >= self._target_bytes:
            chunk = bytes(self._buffer[: self._target_bytes])
            del self._buffer[: self._target_bytes]
            await self._emit(chunk)

    async def _flush(self) -> None:
        if not self._buffer:
            return
        chunk = bytes(self._buffer)
        self._buffer.clear()
        await self._emit(chunk)

    async def _emit(self, audio: bytes) -> None:
        await self.push_frame(
            InputAudioRawFrame(
                audio=audio,
                sample_rate=self._sample_rate,
                num_channels=self._num_channels,
            )
        )
