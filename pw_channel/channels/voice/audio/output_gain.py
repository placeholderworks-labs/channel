import logging

import numpy as np
from pipecat.frames.frames import (
    Frame,
    OutputAudioRawFrame,
    TTSAudioRawFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

logger = logging.getLogger(__name__)

_KNEE = 0.9
_FULL_SCALE = 32767.0


def apply_gain(pcm: bytes, gain: float) -> bytes:
    if not pcm or gain == 1.0:
        return pcm

    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / _FULL_SCALE
    samples = samples * gain

    over = np.abs(samples) > _KNEE
    if np.any(over):
        excess = (np.abs(samples[over]) - _KNEE) / (1.0 - _KNEE)
        compressed = _KNEE + (1.0 - _KNEE) * np.tanh(excess)
        samples[over] = np.sign(samples[over]) * compressed

    return (samples * _FULL_SCALE).astype(np.int16).tobytes()


class OutputGainProcessor(FrameProcessor):

    def __init__(self, *, gain_db: float, **kwargs):
        super().__init__(**kwargs)
        self._gain_db = gain_db
        self._gain = float(10.0 ** (gain_db / 20.0))

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TTSAudioRawFrame):
            frame = TTSAudioRawFrame(
                audio=apply_gain(frame.audio, self._gain),
                sample_rate=frame.sample_rate,
                num_channels=frame.num_channels,
                context_id=frame.context_id,
            )
        elif isinstance(frame, OutputAudioRawFrame):
            frame = OutputAudioRawFrame(
                audio=apply_gain(frame.audio, self._gain),
                sample_rate=frame.sample_rate,
                num_channels=frame.num_channels,
            )

        await self.push_frame(frame, direction)
