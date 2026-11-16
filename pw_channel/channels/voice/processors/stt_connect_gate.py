import logging

from pipecat.frames.frames import Frame, InputAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

logger = logging.getLogger(__name__)

_MAX_BUFFERED_FRAMES = 150


class STTConnectGateProcessor(FrameProcessor):
    def __init__(self, ready_event, *, max_buffered_frames: int = _MAX_BUFFERED_FRAMES, **kwargs):
        super().__init__(**kwargs)
        self._ready_event = ready_event
        self._max_buffered_frames = max_buffered_frames
        self._buffer: list[tuple[Frame, FrameDirection]] = []
        self._flushed = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if self._flushed or not isinstance(frame, InputAudioRawFrame):
            await self.push_frame(frame, direction)
            return

        if self._ready_event.is_set():
            self._flushed = True
            if self._buffer:
                logger.info(
                    f"[stt_gate] STT connected — replaying {len(self._buffer)} "
                    "audio frames buffered during the handshake"
                )
                for buffered_frame, buffered_direction in self._buffer:
                    await self.push_frame(buffered_frame, buffered_direction)
                self._buffer.clear()
            await self.push_frame(frame, direction)
            return

        self._buffer.append((frame, direction))
        if len(self._buffer) > self._max_buffered_frames:
            self._buffer.pop(0)
