from pw_channel.channels.voice.vad.base import VADProvider


class SileroVAD(VADProvider):
    name = "silero"

    def build(self, params: dict):
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.audio.vad.vad_analyzer import VADParams

        return SileroVADAnalyzer(params=VADParams(**params))
