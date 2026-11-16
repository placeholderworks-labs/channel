import json
import logging
from typing import Optional

from pipecat.audio.utils import create_stream_resampler
from pipecat.frames.frames import (
    AudioRawFrame,
    EndWorkerFrame,
    Frame,
    InputAudioRawFrame,
    StartFrame,
)
from pipecat.serializers.base_serializer import FrameSerializer

logger = logging.getLogger(__name__)


class RawPCMFrameSerializer(FrameSerializer):
    class InputParams(FrameSerializer.InputParams):
        client_sample_rate: int = 24000
        sample_rate: Optional[int] = None

    def __init__(self, params: Optional[InputParams] = None):
        super().__init__(params or RawPCMFrameSerializer.InputParams())

        self._client_sample_rate = self._params.client_sample_rate
        self._sample_rate = 0

        self._input_resampler = create_stream_resampler()
        self._output_resampler = create_stream_resampler()

    async def setup(self, frame: StartFrame):
        self._sample_rate = self._params.sample_rate or frame.audio_in_sample_rate

    async def serialize(self, frame: Frame) -> str | bytes | None:
        if isinstance(frame, AudioRawFrame):
            resampled = await self._output_resampler.resample(
                frame.audio, frame.sample_rate, self._client_sample_rate
            )
            return resampled or None
        return None

    async def deserialize(self, data: str | bytes) -> Frame | None:
        if isinstance(data, str):
            try:
                message = json.loads(data)
            except (ValueError, TypeError):
                return None

            if isinstance(message, dict) and message.get("type") == "hangup":
                logger.info("[website] client requested hangup")
                return EndWorkerFrame(reason="client hangup")

            return None

        resampled = await self._input_resampler.resample(
            data, self._client_sample_rate, self._sample_rate
        )
        if not resampled:
            return None

        return InputAudioRawFrame(audio=resampled, num_channels=1, sample_rate=self._sample_rate)
