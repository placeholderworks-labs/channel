import asyncio

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    CancelFrame,
    EndFrame,
    Frame,
    OutputAudioRawFrame,
    StartFrame,
    TTSAudioRawFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from pw_channel.channels.voice.audio.ambience import AmbienceLoop


_CHUNK_MS = 20


class AmbienceMixerProcessor(FrameProcessor):
    def __init__(self, *, level_db: float, **kwargs):
        super().__init__(**kwargs)
        self._ambience = AmbienceLoop(level_db=level_db)
        self._sample_rate: int | None = None
        self._num_channels = 1
        self._tts_active = False
        self._filler_task: asyncio.Task | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, StartFrame):
            self._sample_rate = frame.audio_out_sample_rate
            await self.push_frame(frame, direction)
            self._start_filler_task()
            return

        if isinstance(frame, (EndFrame, CancelFrame)):
            await self._stop_filler_task()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, BotStartedSpeakingFrame):
            self._tts_active = True
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, BotStoppedSpeakingFrame):
            self._tts_active = False
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TTSAudioRawFrame):
            self._num_channels = frame.num_channels
            mixed_audio = self._ambience.mix(
                frame.audio, frame.sample_rate, frame.num_channels
            )
            frame = TTSAudioRawFrame(
                audio=mixed_audio,
                sample_rate=frame.sample_rate,
                num_channels=frame.num_channels,
                context_id=frame.context_id,
            )

        await self.push_frame(frame, direction)

    def _start_filler_task(self):
        if self._filler_task is None:
            self._filler_task = self.create_task(self._filler_loop(), name="ambience_filler")

    async def _stop_filler_task(self):
        if self._filler_task is not None:
            await self.cancel_task(self._filler_task)
            self._filler_task = None

    async def _filler_loop(self):
        chunk_frames = int(self._sample_rate * _CHUNK_MS / 1000)
        interval = _CHUNK_MS / 1000

        while True:
            await asyncio.sleep(interval)

            if self._tts_active:
                continue

            audio = self._ambience.generate(
                self._sample_rate, self._num_channels, chunk_frames
            )
            await self.push_frame(
                OutputAudioRawFrame(
                    audio=audio,
                    sample_rate=self._sample_rate,
                    num_channels=self._num_channels,
                )
            )
