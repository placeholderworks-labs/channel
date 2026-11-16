from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    help: str
    type: str = "text"
    default: str = ""
    options: tuple[str, ...] = ()
    secret: bool = False
    restart: bool = False
    unit: str = ""
    placeholder: str = ""
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    advanced: bool = False
    depends_on: tuple[str, str] | None = None
    group: str = ""
    sub: str = ""
    inherits: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "help": self.help,
            "type": self.type,
            "default": self.default,
            "options": list(self.options),
            "secret": self.secret,
            "restart": self.restart,
            "unit": self.unit,
            "placeholder": self.placeholder,
            "min": self.minimum,
            "max": self.maximum,
            "step": self.step,
            "advanced": self.advanced,
            "dependsOn": list(self.depends_on) if self.depends_on else None,
            "group": self.group,
            "sub": self.sub,
            "inherits": self.inherits,
        }


@dataclass(frozen=True)
class SettingGroup:
    id: str
    title: str
    blurb: str
    section: str
    settings: tuple[Setting, ...] = field(default_factory=tuple)
    category: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "blurb": self.blurb,
            "section": self.section,
            "category": self.category,
            "settings": [s.to_dict() for s in self.settings],
        }


LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
LOG_COLORS = ("auto", "always", "never")
MURF_VOICES = ("Anisha", "Ayushi", "Pooja")
CHANNELS = ("acefone", "website")


def _vad_for(channel: str) -> tuple[Setting, ...]:
    return tuple(x for x in _vad_overrides() if x.key.endswith(f"_{channel.upper()}"))


def _stt_for(channel: str) -> tuple[Setting, ...]:
    return tuple(x for x in _stt_overrides() if x.key.endswith(f"_{channel.upper()}"))


def _switch_for(channel: str, label: str, help_text: str, default: str = "false") -> tuple[Setting, ...]:
    up = channel.upper()
    return (
        Setting(
            key=f"ENABLE_{up}",
            label=f"Answer {label}",
            help=help_text + " Applies to the next connection; no restart.",
            type="bool",
            default=default,
        ),
        Setting(
            key=f"{up}_WS_PATH",
            label="WebSocket path",
            help=f"Path {label} streams audio to. Changing it applies immediately, so "
                 "update the provider's URL to match.",
            default=f"/ws/{channel}",
        ),
    )


def _vad_overrides() -> tuple[Setting, ...]:
    params = (
        ("CONFIDENCE", "Speech confidence", "How sure the detector must be that this is speech.", 0.0, 1.0, 0.05),
        ("START_SECS", "Speech start", "Speech must last this long before a turn opens.", 0.0, 2.0, 0.05),
        ("STOP_SECS", "Speech stop", "Silence this long counts as the end of speech.", 0.0, 3.0, 0.05),
        ("MIN_VOLUME", "Minimum volume", "Audio quieter than this is ignored entirely.", 0.0, 1.0, 0.05),
    )
    out: list[Setting] = []
    for channel in CHANNELS:
        for suffix, label, help_text, lo, hi, step in params:
            out.append(
                Setting(
                    key=f"VAD_{suffix}_{channel.upper()}",
                    label=f"{channel.title()}: {label}",
                    help=f"{help_text} Leave empty to use the global value.",
                    type="number",
                    default="",
                    minimum=lo,
                    maximum=hi,
                    step=step,
                    advanced=True,
                    placeholder="global",
                    inherits=f"VAD_{suffix}",
                )
            )
    return tuple(out)


def _voice_user_type_overrides() -> tuple[Setting, ...]:
    return tuple(
        Setting(
            key=f"PW_CHAT_BRAIN_{channel.upper()}",
            label=f"{channel.title()}: chatbot user type",
            help="Overrides the phone/website default for this channel only. Leave empty "
                 "unless you are deliberately testing one channel against another brain.",
            default="",
            advanced=True,
            placeholder="default",
            inherits="PW_CHAT_USER_TYPE_WEBSITE" if channel == "website"
            else "PW_CHAT_USER_TYPE_PHONE",
        )
        for channel in CHANNELS
    )


def _stt_overrides() -> tuple[Setting, ...]:
    params = (
        ("PROVIDER", "transcriber", "deepgram or deepgram_flux for this channel."),
        ("LANGUAGE", "language", "Transcription language for this channel."),
        ("MODEL", "model", "Deepgram model for this channel."),
    )
    out: list[Setting] = []
    for channel in CHANNELS:
        for suffix, label, help_text in params:
            out.append(
                Setting(
                    key=f"STT_{suffix}_{channel.upper()}",
                    label=f"{channel.title()}: {label}",
                    help=f"{help_text} Leave empty to use the global value.",
                    default="hi" if (channel == "website" and suffix == "LANGUAGE")
                    else "nova-2" if (channel == "website" and suffix == "MODEL")
                    else "",
                    advanced=True,
                    placeholder="global",
                    inherits=f"STT_{suffix}",
                )
            )
    return tuple(out)


_GROUPS: tuple[SettingGroup, ...] = (
    SettingGroup(
        id="runtime",
        title="Language & identity",
        blurb="What the bot speaks, and the address providers dial into.",
        section="Common",
        settings=(
                        Setting(
                key="BOT_LANGUAGE",
                label="Bot language",
                help="The language the bot opens in. This also picks the TTS locale and the "
                     "script the model is told to write in.",
                type="select",
                options=("hindi", "english"),
                default="hindi",
            ),
            Setting(
                key="PUBLIC_WSS_BASE",
                label="Public WebSocket base",
                help="The public wss:// address of this server. Telephony providers dial back "
                     "into it to stream audio, so a call cannot connect while this is wrong.",
                placeholder="wss://voicebot.example.com",
            ),
        ),
    ),
    SettingGroup(
        id="stt",
        title="Speech to text",
        blurb="Deepgram, shared by every channel. A channel that needs its own language or model overrides it in that channel's own group.",
        section="Common",
        settings=(
            Setting(
                key="STT_PROVIDER",
                label="Provider",
                help="deepgram is Deepgram's v1 streaming API with local turn-taking. "
                     "deepgram_flux is the v2 turn-based API, which detects end-of-turn "
                     "itself and replaces the VAD and smart-turn settings below.",
                type="select",
                options=("deepgram", "deepgram_flux"),
                default="deepgram",
            ),
            Setting(
                key="STT_MODEL",
                label="Model",
                help="Deepgram model name for the v1 provider. nova-3 handles Hindi–English "
                     "code-switching best. Ignored when the provider is deepgram_flux.",
                default="nova-3",
            ),
            Setting(
                key="STT_FLUX_MODEL",
                label="Flux model",
                help="Model used when the provider is deepgram_flux. flux-general-multi "
                     "handles Hindi–English code-switching; flux-general-en is English only "
                     "and rejects language hints.",
                type="select",
                options=("flux-general-multi", "flux-general-en"),
                default="flux-general-multi",
            ),
            Setting(
                key="STT_LANGUAGE",
                label="Language",
                help="Transcription language. 'multi' lets one call mix Hindi and English, "
                     "which is how most callers actually speak.",
                default="multi",
                placeholder="multi",
            ),
            Setting(
                key="DEEPGRAM_API_KEY",
                label="Deepgram API key",
                help="From console.deepgram.com. Required whenever Deepgram is the transcriber.",
                type="password",
                secret=True,
            ),
        ),
    ),
    SettingGroup(
        id="tts",
        title="Text to speech",
        blurb="Which engine speaks, and how it sounds. Shared by every channel.",
        section="Common",
        settings=(
            Setting(
                key="TTS_PROVIDER",
                label="Provider",
                help="Murf is the production voice. Gemini has the widest emotional range but "
                     "the highest latency; Sarvam is strongest on Indian languages; OpenAI is "
                     "the fallback.",
                type="select",
                options=("murf", "gemini", "sarvam", "openai"),
                default="murf",
            ),
            Setting(
                key="TTS_MODEL",
                label="Gemini model",
                help="Gemini TTS model id.",
                default="gemini-3.1-flash-tts-preview",
                depends_on=("TTS_PROVIDER", "gemini"),
            ),
            Setting(
                key="TTS_VOICE",
                label="Gemini voice",
                help="Gemini voice name, e.g. Kore.",
                default="Kore",
                depends_on=("TTS_PROVIDER", "gemini"),
            ),
            Setting(
                key="TTS_SAMPLE_RATE",
                label="Gemini sample rate",
                help="Audio rate Gemini renders at, in Hz.",
                type="number",
                default="24000",
                minimum=8000,
                maximum=48000,
                step=1000,
                unit="Hz",
                depends_on=("TTS_PROVIDER", "gemini"),
            ),
            Setting(
                key="GOOGLE_API_KEY",
                label="Google API key",
                help="Gemini Developer API key. Required when Gemini is the voice.",
                type="password",
                secret=True,
                depends_on=("TTS_PROVIDER", "gemini"),
            ),
            Setting(
                key="MURF_API_KEY",
                label="Murf API key",
                help="From murf.ai. Required when Murf is the voice.",
                type="password",
                secret=True,
                depends_on=("TTS_PROVIDER", "murf"),
            ),
            Setting(
                key="MURF_TTS_VOICE",
                label="Murf voice",
                help="Which of the three Hindi voices speaks. They differ in pitch and "
                     "pace, so re-check the speaking rate below after switching.",
                type="select",
                options=MURF_VOICES,
                default="Anisha",
                depends_on=("TTS_PROVIDER", "murf"),
            ),
            Setting(
                key="MURF_TTS_MODEL",
                label="Murf model",
                help="Murf synthesis model, e.g. falcon-2.",
                default="falcon-2",
                depends_on=("TTS_PROVIDER", "murf"),
            ),
            Setting(
                key="MURF_TTS_STYLE",
                label="Murf style",
                help="Delivery style the voice performs, e.g. Conversational.",
                default="Conversational",
                depends_on=("TTS_PROVIDER", "murf"),
            ),
            Setting(
                key="MURF_TTS_LANGUAGE",
                label="Murf locale",
                help="Locale override such as hi-IN. Empty follows the bot language.",
                default="",
                placeholder="follows bot language",
                depends_on=("TTS_PROVIDER", "murf"),
            ),
            Setting(
                key="MURF_TTS_RATE",
                label="Murf speaking rate",
                help="Speed offset. 0 is the voice's natural pace; negative is slower.",
                type="number",
                default="0",
                minimum=-50,
                maximum=50,
                step=1,
                depends_on=("TTS_PROVIDER", "murf"),
            ),
            Setting(
                key="MURF_TTS_PITCH",
                label="Murf pitch",
                help="Pitch offset. 0 is the voice's natural pitch.",
                type="number",
                default="0",
                minimum=-50,
                maximum=50,
                step=1,
                depends_on=("TTS_PROVIDER", "murf"),
            ),
            Setting(
                key="MURF_TTS_VARIATION",
                label="Murf variation",
                help="How much the delivery varies between sentences. 1 is a light, natural "
                     "amount; higher can sound unstable on a business call.",
                type="number",
                default="1",
                minimum=0,
                maximum=5,
                step=1,
                depends_on=("TTS_PROVIDER", "murf"),
            ),
            Setting(
                key="MURF_TTS_PRONUNCIATION_DICTIONARY",
                label="Pronunciation dictionary",
                help='JSON map of words to how they should be said, so brand names survive. '
                     'Example: {"PlaceholderWorks":{"type":"IPA","pronunciation":"ˈpleɪshoʊldərwɜːrks"}}',
                type="json",
                default="",
                depends_on=("TTS_PROVIDER", "murf"),
            ),
            Setting(
                key="MURF_TTS_URL",
                label="Murf stream URL",
                help="Murf streaming endpoint. Change only if Murf tells you to.",
                default="wss://global.api.murf.ai/v1/speech/stream-input",
                advanced=True,
                depends_on=("TTS_PROVIDER", "murf"),
            ),
            Setting(
                key="MURF_TTS_SAMPLE_RATE",
                label="Murf sample rate",
                help="Audio rate Murf renders at, in Hz.",
                type="number",
                default="24000",
                minimum=8000,
                maximum=48000,
                step=1000,
                unit="Hz",
                advanced=True,
                depends_on=("TTS_PROVIDER", "murf"),
            ),
            Setting(
                key="MURF_TTS_CHANNEL_TYPE",
                label="Murf channel type",
                help="MONO is what every telephony leg expects.",
                type="select",
                options=("MONO", "STEREO"),
                default="MONO",
                advanced=True,
                depends_on=("TTS_PROVIDER", "murf"),
            ),
            Setting(
                key="MURF_TTS_FORMAT",
                label="Murf audio format",
                help="Wire format Murf sends back.",
                type="select",
                options=("PCM", "WAV", "MP3"),
                default="PCM",
                advanced=True,
                depends_on=("TTS_PROVIDER", "murf"),
            ),
            Setting(
                key="MURF_TTS_MIN_BUFFER_SIZE",
                label="Murf minimum buffer",
                help="How much text Murf waits for before it starts speaking. Smaller starts "
                     "sooner but can clip the phrasing.",
                type="number",
                default="40",
                minimum=5,
                maximum=200,
                step=5,
                advanced=True,
                depends_on=("TTS_PROVIDER", "murf"),
            ),
            Setting(
                key="MURF_TTS_MAX_BUFFER_DELAY_MS",
                label="Murf maximum buffer delay",
                help="Longest Murf holds text back while filling that buffer.",
                type="number",
                default="300",
                minimum=0,
                maximum=2000,
                step=50,
                unit="ms",
                advanced=True,
                depends_on=("TTS_PROVIDER", "murf"),
            ),
            Setting(
                key="SARVAM_API_KEY",
                label="Sarvam API key",
                help="From dashboard.sarvam.ai.",
                type="password",
                secret=True,
                depends_on=("TTS_PROVIDER", "sarvam"),
            ),
            Setting(
                key="SARVAM_TTS_MODEL",
                label="Sarvam model",
                help="Sarvam synthesis model, e.g. bulbul:v2.",
                default="bulbul:v2",
                depends_on=("TTS_PROVIDER", "sarvam"),
            ),
            Setting(
                key="SARVAM_TTS_VOICE",
                label="Sarvam voice",
                help="Sarvam speaker name, e.g. anushka.",
                default="anushka",
                depends_on=("TTS_PROVIDER", "sarvam"),
            ),
            Setting(
                key="SARVAM_TTS_LANGUAGE",
                label="Sarvam locale",
                help="Locale such as hi-IN. Empty follows the bot language.",
                default="",
                placeholder="follows bot language",
                depends_on=("TTS_PROVIDER", "sarvam"),
            ),
            Setting(
                key="SARVAM_TTS_PACE",
                label="Sarvam pace",
                help="Speaking speed multiplier. 1.0 is natural.",
                type="number",
                default="1.0",
                minimum=0.5,
                maximum=2.0,
                step=0.05,
                depends_on=("TTS_PROVIDER", "sarvam"),
            ),
            Setting(
                key="SARVAM_TTS_SAMPLE_RATE",
                label="Sarvam sample rate",
                help="Audio rate Sarvam renders at, in Hz.",
                type="number",
                default="22050",
                minimum=8000,
                maximum=48000,
                step=1000,
                unit="Hz",
                advanced=True,
                depends_on=("TTS_PROVIDER", "sarvam"),
            ),
            Setting(
                key="OPENAI_TTS_API_KEY",
                label="OpenAI API key",
                help="Used only for OpenAI speech.",
                type="password",
                secret=True,
                depends_on=("TTS_PROVIDER", "openai"),
            ),
            Setting(
                key="OPENAI_TTS_MODEL",
                label="OpenAI model",
                help="OpenAI speech model, e.g. gpt-4o-mini-tts.",
                default="gpt-4o-mini-tts",
                depends_on=("TTS_PROVIDER", "openai"),
            ),
            Setting(
                key="OPENAI_TTS_VOICE",
                label="OpenAI voice",
                help="OpenAI voice name, e.g. alloy.",
                default="alloy",
                depends_on=("TTS_PROVIDER", "openai"),
            ),
            Setting(
                key="OPENAI_TTS_INSTRUCTIONS",
                label="OpenAI delivery notes",
                help="Free-text direction for how the voice should sound. Empty uses a warm "
                     "customer-care tone in the bot's language.",
                type="textarea",
                default="",
                depends_on=("TTS_PROVIDER", "openai"),
            ),
            Setting(
                key="OPENAI_TTS_SPEED",
                label="OpenAI speed",
                help="Speaking speed multiplier. 1.0 is natural.",
                type="number",
                default="1.0",
                minimum=0.25,
                maximum=4.0,
                step=0.05,
                depends_on=("TTS_PROVIDER", "openai"),
            ),
            Setting(
                key="OPENAI_TTS_SAMPLE_RATE",
                label="OpenAI sample rate",
                help="Audio rate OpenAI renders at, in Hz.",
                type="number",
                default="24000",
                minimum=8000,
                maximum=48000,
                step=1000,
                unit="Hz",
                advanced=True,
                depends_on=("TTS_PROVIDER", "openai"),
            ),
        ),
    ),
    SettingGroup(
        id="turn",
        title="Turn-taking",
        blurb="When the bot decides you have finished speaking, and when it may be interrupted.",
        section="Common",
        settings=(
            Setting(
                key="VAD_CONFIDENCE",
                label="Speech confidence",
                help="How sure the detector must be that incoming audio is speech. Raise it on "
                     "a noisy line, lower it if soft speakers get cut off.",
                type="number",
                default="0.7",
                minimum=0,
                maximum=1,
                step=0.05,
            ),
            Setting(
                key="VAD_START_SECS",
                label="Speech start",
                help="Speech must last this long before the bot treats it as a turn.",
                type="number",
                default="0.2",
                minimum=0,
                maximum=2,
                step=0.05,
                unit="s",
            ),
            Setting(
                key="VAD_STOP_SECS",
                label="Speech stop",
                help="Silence this long marks the end of speech.",
                type="number",
                default="0.5",
                minimum=0,
                maximum=3,
                step=0.05,
                unit="s",
            ),
            Setting(
                key="VAD_MIN_VOLUME",
                label="Minimum volume",
                help="Audio quieter than this never counts as speech.",
                type="number",
                default="0.6",
                minimum=0,
                maximum=1,
                step=0.05,
            ),
            Setting(
                key="MIN_WORDS_TO_INTERRUPT",
                label="Words needed to interrupt",
                help="While the bot is speaking, this many words must be transcribed before a "
                     "barge-in counts. Stops breath and background chatter from cutting it off. "
                     "When the bot is silent, one word is always enough.",
                type="number",
                default="2",
                minimum=1,
                maximum=10,
                step=1,
                unit="words",
            ),
            Setting(
                key="SMART_TURN_STOP_SECS",
                label="Turn analyzer silence",
                help="How long the turn analyzer waits before deciding the caller is done. "
                     "Must stay below the turn watchdog below.",
                type="number",
                default="2.5",
                minimum=0.2,
                maximum=5,
                step=0.1,
                unit="s",
            ),
            Setting(
                key="USER_TURN_STOP_TIMEOUT_SECS",
                label="Turn watchdog",
                help="Fallback for a turn that opened but produced no transcript: close it after "
                     "this long and re-prompt, so the line never sits silent. Must be greater "
                     "than the turn analyzer silence.",
                type="number",
                default="3.5",
                minimum=0.5,
                maximum=10,
                step=0.1,
                unit="s",
            ),
            Setting(
                key="USER_IDLE_TIMEOUT_SECS",
                label="Silence nudge",
                help="Re-prompt when the caller says nothing at all for this long after the bot "
                     "finishes. Different from the watchdog above, which needs words first. On "
                     "a phone line total silence is the common case. 0 disables it.",
                type="number",
                default="7",
                minimum=0,
                maximum=60,
                step=0.5,
                unit="s",
            ),
            Setting(
                key="MAX_CONSECUTIVE_REPROMPTS",
                label="Nudges before hanging up",
                help="How many times in a row the bot re-prompts an unresponsive caller before "
                     "it ends the call.",
                type="number",
                default="3",
                minimum=0,
                maximum=10,
                step=1,
            ),
            Setting(
                key="ENABLE_LANGUAGE_SWITCH",
                label="Allow language switch mid-call",
                help="Lets the caller ask for the other language (Hindi or English). Switches "
                     "both the voice locale and the prompt.",
                type="bool",
                default="true",
            ),
            Setting(
                key="SMART_TURN_PRE_SPEECH_MS",
                label="Turn analyzer pre-roll",
                help="Audio kept from before speech started, so the analyzer hears the onset.",
                type="number",
                default="800",
                minimum=0,
                maximum=3000,
                step=50,
                unit="ms",
                advanced=True,
            ),
            Setting(
                key="SMART_TURN_MAX_DURATION_SECS",
                label="Turn analyzer window",
                help="Longest stretch of speech the analyzer considers at once.",
                type="number",
                default="12",
                minimum=2,
                maximum=60,
                step=1,
                unit="s",
                advanced=True,
            ),
            Setting(
                key="FLUX_EOT_THRESHOLD",
                label="End-of-turn confidence",
                help="How sure Flux must be that the caller has finished before it closes the "
                     "turn. Higher waits longer but interrupts the caller less.",
                type="number",
                default="0.7",
                minimum=0.5,
                maximum=1,
                step=0.05,
            ),
            Setting(
                key="FLUX_EOT_TIMEOUT_MS",
                label="End-of-turn timeout",
                help="Longest silence Flux tolerates before closing the turn anyway. This "
                     "stacks on top of the turn watchdog, so keep it tight on phone lines.",
                type="number",
                default="5000",
                minimum=500,
                maximum=60000,
                step=100,
                unit="ms",
            ),
            Setting(
                key="FLUX_SHOULD_INTERRUPT",
                label="Flux may interrupt the bot",
                help="Let Flux cut the bot off the moment it detects the caller speaking. "
                     "Turning this off means the bot talks over a real interruption.",
                type="bool",
                default="true",
                advanced=True,
            ),
            Setting(
                key="FLUX_TURN_AGGREGATION_MS",
                label="Flux turn settle",
                help="How long Flux's turn end waits for its own transcript to catch up. "
                     "Only has to cover a queue hop. Pipecat's 0.5s default is dead air "
                     "in front of every reply.",
                type="number",
                default="50",
                minimum=10,
                maximum=500,
                step=10,
                unit="ms",
                advanced=True,
            ),
            Setting(
                key="FLUX_INPUT_CHUNK_MS",
                label="Flux audio chunk",
                help="Re-frame incoming audio to this many milliseconds before Flux. Deepgram "
                     "recommends 80. 0 forwards the telephony provider's own framing unchanged.",
                type="number",
                default="0",
                minimum=0,
                maximum=200,
                step=10,
                unit="ms",
                advanced=True,
            ),
                    ),
    ),
                SettingGroup(
        id="audio",
        title="Audio output",
        blurb="Loudness and room tone on the outgoing audio.",
        section="Common",
        settings=(
            Setting(
                key="BOT_OUTPUT_GAIN_DB",
                label="Output gain",
                help="Loudness of the bot's voice, in dB. Nothing else in the pipeline touches "
                     "the level, so this is the only lever when the bot sounds quiet. Try 4–6 "
                     "first; past about 12 the limiter squashes the voice.",
                type="number",
                default="0",
                minimum=-24,
                maximum=24,
                step=0.5,
                unit="dB",
            ),
            Setting(
                key="ENABLE_BACKGROUND_AMBIENCE",
                label="Call-centre ambience",
                help="Mixes faint room noise under the bot so the line doesn't sound "
                     "unnaturally dead between sentences.",
                type="bool",
                default="false",
            ),
            Setting(
                key="BACKGROUND_AMBIENCE_LEVEL_DB",
                label="Ambience level",
                help="How loud that room noise sits, in dB. More negative is quieter.",
                type="number",
                default="-28",
                minimum=-60,
                maximum=-6,
                step=1,
                unit="dB",
                depends_on=("ENABLE_BACKGROUND_AMBIENCE", "true"),
            ),
        ),
    ),
    SettingGroup(
        id="acefone",
        title="Acefone",
        blurb="The production dialer. Everything this provider needs, including whether it is armed and the path it streams to.",
        section="Call",
        settings=(
            *_switch_for("acefone", "Acefone", "Acefone click-to-call, the dialer used for production abandoned-cart calls.", "false"),
            Setting(
                key="ACEFONE_API_KEY",
                label="API key",
                help="Acefone API token for placing calls.",
                type="password",
                secret=True,
            ),
            Setting(
                key="ACEFONE_CALLER_ID",
                label="Caller ID",
                help="The number the customer sees. Must be a DID registered with Acefone.",
                placeholder="911140000000",
            ),
            Setting(
                key="ACEFONE_AUTH_TOKEN",
                label="Access token",
                help="Acefone access token. Sent as the Authorization header when placing a call "
                     "(required since 30 Sep 2026) and for live call transfer. "
                     "Paste the bare token; a 'Bearer ' prefix is added automatically.",
                type="password",
                secret=True,
            ),
            Setting(
                key="ACEFONE_API_BASE",
                label="API base URL",
                help="Acefone API root.",
                default="https://api.acefone.in/v1",
                advanced=True,
            ),
            Setting(
                key="ACEFONE_RING_TIMEOUT",
                label="Ring timeout",
                help="How long the customer's phone rings before the attempt is abandoned. "
                     "Acefone only accepts 10–30 seconds.",
                type="number",
                default="30",
                minimum=10,
                maximum=30,
                step=1,
                unit="s",
            ),
            Setting(
                key="ACEFONE_CALL_TIMEOUT",
                label="Call timeout",
                help="Provider-side ceiling on a connected call. 0 leaves it to the call "
                     "limits above.",
                type="number",
                default="0",
                minimum=0,
                maximum=3600,
                step=10,
                unit="s",
                advanced=True,
            ),
            Setting(
                key="ACEFONE_AUTO_HANG_UP",
                label="Hang up automatically",
                help="Drop the line ourselves when the conversation is finished, instead of "
                     "waiting for Acefone.",
                type="bool",
                default="true",
            ),
            Setting(
                key="ACEFONE_MEDIA_FORMAT",
                label="Media format",
                help="Wire codec for the audio stream. ulaw is standard telephony.",
                type="select",
                options=("ulaw", "pcm"),
                default="ulaw",
                advanced=True,
            ),
            Setting(
                key="ACEFONE_SAMPLE_RATE",
                label="Sample rate",
                help="Stream rate in Hz. Telephony is 8000.",
                type="number",
                default="8000",
                minimum=8000,
                maximum=16000,
                step=8000,
                unit="Hz",
                advanced=True,
            ),
            Setting(
                key="ACEFONE_OUT_10MS_CHUNKS",
                label="Outbound chunk size",
                help="How many 10 ms frames go in each media message. 2 (20 ms) is recommended; "
                     "with ulaw it must be an even number.",
                type="number",
                default="2",
                minimum=2,
                maximum=10,
                step=2,
                advanced=True,
            ),
            *_vad_for("acefone"),
            *_stt_for("acefone"),
        ),
    ),
    SettingGroup(
        id="call_tracking",
        title="Live call tracking",
        blurb="Where Acefone reports call lifecycle events, and how the live-call list is "
              "reconciled against them. Feeds the Live Calls screen.",
        section="Call",
        settings=(
            Setting(
                key="ACEFONE_WEBHOOK_PATH",
                label="Webhook path",
                help="Path both Acefone triggers POST to: 'Call answered by Agent' and "
                     "'Call hangup (Answered)'. Changing it re-registers the route without "
                     "a restart; update the Acefone panel to match.",
                default="/webhooks/acefone",
            ),
            Setting(
                key="ACEFONE_WEBHOOK_TOKEN",
                label="Webhook token",
                help="Shared secret checked on each delivery, and the token guarding "
                     "GET /api/calls/active. Leave empty to accept unauthenticated "
                     "deliveries and disable that endpoint.",
                type="password",
                secret=True,
            ),
            Setting(
                key="ACEFONE_WEBHOOK_REQUIRE_AUTH",
                label="Require the token",
                help="Refuse a delivery that carries no token at all. Leave off while "
                     "bringing the webhook up; a wrong token is always refused either way.",
                type="bool",
                default="false",
            ),
            Setting(
                key="CALL_TRANSCRIPT_ENABLED",
                label="Record transcripts",
                help="Store each turn so the agent taking a transfer can read what the "
                     "customer already told the bot.",
                type="bool",
                default="true",
            ),
            Setting(
                key="ACEFONE_LIVE_CALLS_ENABLED",
                label="Reconcile against Acefone",
                help="Poll Acefone's live call list as a cross-check. Advisory only: a "
                     "transferred call is never closed from this, because the bot's leg is "
                     "gone by design while the customer is still talking.",
                type="bool",
                default="false",
            ),
            Setting(
                key="ACEFONE_LIVE_CALLS_POLL_SECS",
                label="Reconciliation interval",
                help="How often to poll the live call list.",
                type="number",
                default="30",
                minimum=10,
                maximum=600,
                step=5,
                unit="s",
                advanced=True,
            ),
            Setting(
                key="CALL_SESSION_STALE_SECS",
                label="Stale call cutoff",
                help="Last-resort age at which a call still marked as with an agent is "
                     "closed, when no hangup webhook ever arrived. Deliberately far outside "
                     "a normal call.",
                type="number",
                default="14400",
                minimum=600,
                maximum=86400,
                step=600,
                unit="s",
                advanced=True,
            ),
        ),
    ),
    SettingGroup(
        id="call_transfer",
        title="Transfer to a human",
        blurb="Where a call goes when the bot hands it to customer care.",
        section="Call",
        settings=(
            Setting(
                key="ENABLE_CALL_TRANSFER",
                label="Allow call transfer",
                help="Give the bot a tool to transfer the live call to human customer care. "
                     "Needs the Acefone access token above.",
                type="bool",
                default="true",
            ),
            Setting(
                key="CALL_TRANSFER_NUMBER",
                label="Transfer number",
                help="The number a call is transferred to. Default for every agent; an agent "
                     "can hand its calls to its own line under Agent > Channels & calls.",
                default="01143131313",
                placeholder="01143131313",
                depends_on=("ENABLE_CALL_TRANSFER", "true"),
            ),
            Setting(
                key="CALL_TRANSFER_HOLD_SECS",
                label="Handoff line grace",
                help="The least time to wait before transferring, so the bot's "
                     "\"connecting you now\" line finishes playing. A longer line gets longer "
                     "automatically; the transfer still happens the moment the line ends.",
                type="number",
                default="4",
                minimum=0,
                maximum=15,
                step=0.5,
                unit="s",
                depends_on=("ENABLE_CALL_TRANSFER", "true"),
            ),
        ),
    ),
    SettingGroup(
        id="website",
        title="Website widget",
        blurb="The browser voicebot: the channel Browser test talks to, and what a real visitor gets.",
        section="Website",
        settings=(
            *_switch_for("website", "the website widget", "The browser voice surface, including Playground → WebRTC.", "false"),
                        Setting(
                key="WEBSITE_SAMPLE_RATE",
                label="Browser sample rate",
                help="Rate the browser records and plays at, in Hz.",
                type="number",
                default="24000",
                minimum=8000,
                maximum=48000,
                step=1000,
                unit="Hz",
            ),
            Setting(
                key="WEBSITE_PIPELINE_SAMPLE_RATE",
                label="Pipeline sample rate",
                help="Rate the pipeline and voice detector run at. Only 8000 or 16000 work; "
                     "the serializer resamples the browser audio to match.",
                type="select",
                options=("16000", "8000"),
                default="16000",
                advanced=True,
            ),
            *_vad_for("website"),
            *_stt_for("website"),
        ),
    ),
    SettingGroup(
        id="pw_chat",
        title="The brain",
        blurb="How this service reaches pw-llm and how long it will wait. The prompts, the model and the tools live in that service's own settings.",
        section="Common",
        settings=(
            Setting(
                key="PW_CHAT_ENABLED",
                label="Enabled",
                help="Off leaves the bot with nothing to answer from, so it will apologise on "
                     "every turn. There is no local model to fall back to.",
                type="bool",
                default="true",
            ),
            Setting(
                key="PW_CHAT_API_URL",
                label="Chat endpoint",
                help="POST target for the chat turn.",
                default="http://localhost:8010/api/pw-ai-service/chat",
            ),
            Setting(
                key="PW_CHAT_API_TOKEN",
                label="Chat API token",
                help="Sent as X-Api-Token on every turn. The chatbot rejects voice requests "
                     "without it, because a phone call's session id is derived from the "
                     "customer's number and is guessable.",
                type="password",
                secret=True,
                default="",
            ),
            Setting(
                key="PW_CHAT_USER_TYPE_PHONE",
                label="Phone user type",
                help="Which brain the chatbot runs for telephony calls. Selects the prompt "
                     "layer and the tool set on their side.",
                default="callvoice",
            ),
            Setting(
                key="PW_CHAT_USER_TYPE_WEBSITE",
                label="Website user type",
                help="Which brain the chatbot runs for the browser voice widget.",
                default="webvoice",
            ),
            Setting(
                key="POST_CALL_MOM_ENABLED",
                label="Send call minutes on WhatsApp",
                help="After every call or website voice chat with a real conversation, the brain "
                     "writes the minutes and next steps and sends them to the customer's WhatsApp. "
                     "Needs the WhatsApp settings in the brain switched on.",
                type="bool",
                default="true",
            ),
            Setting(
                key="PW_CHAT_ACTIONS_ENABLED",
                label="Honour chatbot actions",
                help="Off parses the transfer / hang-up / language-switch requests the chatbot "
                     "sends but never runs them. Use it to neuter a misbehaving brain without "
                     "taking the bot off the air.",
                type="bool",
                default="true",
            ),
            Setting(
                key="PW_CHAT_MAX_CONSECUTIVE_FAILURES",
                label="Give up after",
                help="Consecutive failed turns before the bot speaks a fixed closing line and "
                     "ends the call. Without this a chatbot outage leaves a metered line open "
                     "apologising until the duration cap.",
                type="number",
                default="3",
                minimum=1,
                maximum=5,
                step=1,
            ),
            Setting(
                key="VOICE_REPLY_WARN_CHARS",
                label="Reply length warning",
                help="Log a warning when a spoken reply is longer than this. An early signal "
                     "that the chatbot's voice output policy has regressed into screen copy.",
                type="number",
                default="400",
                minimum=100,
                maximum=2000,
                step=50,
                advanced=True,
            ),
            Setting(
                key="PW_CHAT_CONNECT_TIMEOUT_SECS",
                label="Connect timeout",
                help="How long to wait for the connection itself.",
                type="number",
                default="5.0",
                minimum=1,
                maximum=30,
                step=0.5,
                unit="s",
            ),
            Setting(
                key="PW_CHAT_READ_TIMEOUT_SECS",
                label="Reply timeout",
                help="A tool call that hits a slow API can take 9-12s, so this has to be generous. A read timeout "
                     "is never retried, because the customer has already waited it out once.",
                type="number",
                default="30.0",
                minimum=5,
                maximum=60,
                step=1,
                unit="s",
            ),
            Setting(
                key="PW_CHAT_MAX_ATTEMPTS",
                label="Attempts",
                help="Connection failures and 5xx are retried up to this many times.",
                type="number",
                default="2",
                minimum=1,
                maximum=4,
                step=1,
                advanced=True,
            ),
            Setting(
                key="PW_CHAT_HOLD_DELAY_SECS",
                label="Hold line delay",
                help="How long the chatbot may take before the bot says it is looking. Ordinary "
                     "questions come back in 1.4-4.7s and searches in 9-13s, so this sits in the "
                     "empty gap between them: plain answers get no needless \"one second\" in "
                     "front of them, and the page is already showing a searching state by then.",
                type="number",
                default="1.8",
                minimum=0.5,
                maximum=20,
                step=0.1,
                unit="s",
            ),
            Setting(
                key="PW_CHAT_HOLD_BUDGET_SECS",
                label="Hold line budget",
                help="How long to wait for the chatbot to compose a hold line that names "
                     "back what the customer asked for, before falling back to a fixed "
                     "line. It runs on a tiny prompt in parallel with the real answer, so "
                     "this is a small slice carved off the hold delay, not added to it.",
                type="number",
                default="3.0",
                minimum=0.3,
                maximum=5,
                step=0.1,
                unit="s",
            ),
            Setting(
                key="PW_CHAT_PHONE_READ_TIMEOUT_SECS",
                label="Reply timeout (phone)",
                help="A caller hears nothing while the brain thinks, and dead air reads as a "
                     "dropped call in about a second. Far tighter than the website's, which "
                     "has a visible searching state to sit behind.",
                type="number",
                default="8.0",
                minimum=5,
                maximum=30,
                step=1,
                unit="s",
            ),
            Setting(
                key="PW_CHAT_HOLD_GRACE_SECS",
                label="Hold line grace",
                help="A last look at whether the real answer has already landed, taken "
                     "after the hold delay passes but before the line is spoken. A line "
                     "that beats the answer by a breath covers no silence, so it is "
                     "dropped. Keep it short: the caller hearing nothing at all is what "
                     "makes the bot feel slow. Set to 0 to always speak it.",
                type="number",
                default="0.2",
                minimum=0,
                maximum=3,
                step=0.1,
                unit="s",
            ),
            Setting(
                key="PW_CHAT_PHONE_HOLD_DELAY_SECS",
                label="Hold line delay (phone)",
                help="How long a caller may wait before the bot says it is looking. On a phone "
                     "this is load-bearing, not cosmetic.",
                type="number",
                default="1.4",
                minimum=0.5,
                maximum=10,
                step=0.1,
                unit="s",
            ),
            Setting(
                key="PW_CHAT_PHONE_SECOND_HOLD_SECS",
                label="Second hold line (phone)",
                help="When to say a second holding line if the brain still has not answered.",
                type="number",
                default="4.5",
                minimum=1,
                maximum=20,
                step=0.5,
                unit="s",
            ),
            Setting(
                key="PW_CHAT_SECOND_HOLD_SECS",
                label="Second hold line",
                help="A search still running at this point gets one more short line, filling the "
                     "gap between the first one and the answer. Sits inside the measured search "
                     "band (9-13s) on purpose: a quick search finishes first and stays silent, a "
                     "slow one gets covered.",
                type="number",
                default="8.0",
                minimum=3,
                maximum=25,
                step=0.5,
                unit="s",
                advanced=True,
            ),
            Setting(
                key="PW_CHAT_MAX_HTML_BYTES",
                label="Maximum result size",
                help="Result carousels larger than this are dropped rather than pushed to the "
                     "browser. A rich result card set measures about 50KB.",
                type="number",
                default="262144",
                minimum=16384,
                maximum=2097152,
                step=16384,
                unit="bytes",
                advanced=True,
            ),
            Setting(
                key="PW_CHAT_HTML_CHUNK_BYTES",
                label="Result chunk size",
                help="Results are sent to the browser in chunks this big, so live audio on the "
                     "same socket is not held up behind one large message.",
                type="number",
                default="8192",
                minimum=1024,
                maximum=65536,
                step=1024,
                unit="bytes",
                advanced=True,
            ),
            *_voice_user_type_overrides(),
        ),
    ),
    SettingGroup(
        id="limits",
        title="Call limits",
        blurb="How long a call may run and when it starts wrapping up. Phone only; the browser has no timer.",
        section="Call",
        settings=(
            Setting(
                key="MAX_CALL_DURATION_SECS",
                label="Maximum call length",
                help="Hard ceiling. The call is ended when it is reached, mid-sentence if needed.",
                type="number",
                default="300",
                minimum=30,
                maximum=1800,
                step=10,
                unit="s",
            ),
            Setting(
                key="CALL_WRAP_UP_WARNING_SECS",
                label="Wrap-up warning",
                help="How long before the ceiling the bot is told to start closing, so the call "
                     "ends on a sentence rather than a cut.",
                type="number",
                default="30",
                minimum=0,
                maximum=300,
                step=5,
                unit="s",
            ),
            Setting(
                key="CALL_END_WATCHDOG_SECS",
                label="Hang-up watchdog",
                help="After the bot decides to hang up, force the line down this long later if "
                     "the provider has not dropped it.",
                type="number",
                default="20",
                minimum=1,
                maximum=120,
                step=1,
                unit="s",
                advanced=True,
            ),
        ),
    ),
SettingGroup(
        id="ingestion",
        title="QMS",
        blurb="The intake APIs upstream systems post customer records to. Each intake's fields, token, "
              "agent and timing live on the QMS page and the agent's QMS tab; these are the shared parts.",
        section="Call",
        settings=(
            Setting(
                key="QMS_PUBLIC_BASE_URL",
                label="Public API base URL",
                help="The address upstream systems reach this server on, shown in every intake's endpoint "
                     "and curl. Empty derives it from the public WebSocket base.",
                placeholder="https://voice.placeholderworks.com",
            ),
            Setting(
                key="INGESTION_ENABLED",
                label="Accept QMS requests",
                help="Off answers every intake endpoint with a 503 and dials nothing. Applies immediately.",
                type="bool",
                default="true",
            ),
            Setting(
                key="INGESTION_AGENT",
                label="Abandoned cart agent (first boot)",
                help="The agent the built-in Abandoned cart intake is connected to on first boot. "
                     "After that, connect it from the agent's QMS tab.",
                default="callvoice",
                placeholder="callvoice",
                advanced=True,
            ),
            Setting(
                key="INGESTION_API_TOKEN",
                label="Abandoned cart legacy token",
                help="The original shared token for /api/ingestion/calls, accepted until the Abandoned cart "
                     "intake is given its own token on the QMS page.",
                type="password",
                secret=True,
            ),
            Setting(
                key="INGESTION_CALL_CHANNEL",
                label="Dialer",
                help="Which provider places these calls. Its channel must be armed too.",
                type="select",
                options=("acefone",),
                default="acefone",
            ),
            Setting(
                key="INGESTION_CALL_DELAY_SECS",
                label="Default delay before dialling",
                help="Used by an intake whose agent sets no delay of its own. A record's scheduled_at "
                     "always wins. 0 dials immediately.",
                type="number",
                default="120",
                minimum=0,
                maximum=7200,
                step=10,
                unit="s",
            ),
            Setting(
                key="INGESTION_DEDUPE_WINDOW_SECS",
                label="Default duplicate window",
                help="A record for a reference id or phone number that already has a call scheduled "
                     "or placed within this window is logged as a duplicate and not dialled.",
                type="number",
                default="3600",
                minimum=0,
                maximum=86400,
                step=60,
                unit="s",
            ),
            Setting(
                key="INGESTION_CART_TTL_SECS",
                label="Cart lifetime",
                help="How long a received cart stays available to its call. Must outlive the "
                     "delay above, or the call rings with no cart behind it.",
                type="number",
                default="7200",
                minimum=60,
                maximum=86400,
                step=60,
                unit="s",
                advanced=True,
            ),
            Setting(
                key="INGESTION_MAX_BATCH",
                label="Largest batch",
                help="Most records one request may carry. A bigger batch is rejected whole.",
                type="number",
                default="200",
                minimum=1,
                maximum=1000,
                step=1,
                advanced=True,
            ),
        ),
    ),
            SettingGroup(
        id="webhooks",
        title="Outbound webhooks",
        blurb="Where the disposition is posted after a call.",
        section="Call",
        settings=(
            Setting(
                key="DISPOSITION_LOG_WEBHOOK",
                label="Disposition webhook",
                help="Every call outcome is posted here as JSON. Empty logs locally only.",
                placeholder="https://crm.example.com/hooks/voicebot",
            ),
        ),
    ),
    SettingGroup(
        id="deploy_server",
        title="Server",
        blurb="Where this process listens, how loudly it logs, and how often it re-reads its settings.",
        section="Common",
        settings=(
            Setting(
                key="LOG_LEVEL",
                label="Log level",
                help="How much the server writes to the log stream. DEBUG is loud but shows "
                     "every frame; INFO is the normal setting.",
                type="select",
                options=LOG_LEVELS,
                default="INFO",
                restart=True,
            ),
            Setting(
                key="LOG_COLOR",
                label="Console colour",
                help="Colour on the console only. The JSON log file is never coloured. "
                     "auto means colour when stdout is a terminal, which `docker compose "
                     "up` is not, so set always to keep the boot report coloured there.",
                type="select",
                options=LOG_COLORS,
                default="auto",
                restart=True,
            ),
            Setting(
                key="SETTINGS_REFRESH_SECS",
                label="Settings refresh",
                help="How often this server re-reads the settings table, in seconds. This is "
                     "what carries a change made on another worker (or straight in the "
                     "database) over to this one. 0 switches it off, in which case a "
                     "process only ever sees changes it applied itself.",
                type="number",
                default="15",
                minimum=0,
                maximum=3600,
                step=1,
                unit="s",
            ),
            Setting(
                key="HOST",
                label="Bind address",
                help="Network interface uvicorn listens on. 0.0.0.0 accepts traffic from "
                     "anywhere the container is reachable.",
                default="0.0.0.0",
                restart=True,
            ),
            Setting(
                key="PORT",
                label="Port",
                help="HTTP port for this server. In Docker the container port is fixed at "
                     "8410 and this is only the number uvicorn binds inside it.",
                type="number",
                default="8410",
                minimum=1,
                maximum=65535,
                step=1,
                restart=True,
            ),
        ),
    ),
)

_SUBS: tuple[tuple[str, str], ...] = (
    ("MURF_", "Murf"),
    ("SARVAM_", "Sarvam"),
    ("OPENAI_TTS", "OpenAI"),
    ("GOOGLE_", "Gemini"),
    ("TTS_", "Shared"),
    ("VAD_", "Voice detection"),
    ("SMART_TURN_", "Smart turn"),
    ("FLUX_", "Deepgram Flux"),
    ("STT_", "Transcription"),
    ("PW_CHAT_PHONE_", "Phone budgets"),
    ("PW_CHAT_BRAIN_", "Per-channel brain"),
    ("PW_CHAT_USER_TYPE", "Which brain"),
    ("PW_CHAT_HOLD", "Hold lines"),
    ("PW_CHAT_SECOND_HOLD", "Hold lines"),
    ("PW_CHAT_MAX_HTML", "Results"),
    ("PW_CHAT_HTML", "Results"),
    ("PW_CHAT_", "Connection"),
    ("ACEFONE_", "Acefone API"),
    ("WEBSITE_", "Audio"),
    ("ENABLE_", "Switch"),
    ("CALL_TRANSFER_", "Transfer"),
)

_SUB_EXACT = {
    "ACEFONE_WS_PATH": "Switch",
    "WEBSITE_WS_PATH": "Switch",
    "MIN_WORDS_TO_INTERRUPT": "Interruption",
    "USER_TURN_STOP_TIMEOUT_SECS": "Turn end",
    "USER_IDLE_TIMEOUT_SECS": "Turn end",
    "MAX_CONSECUTIVE_REPROMPTS": "Turn end",
    "ENABLE_LANGUAGE_SWITCH": "Interruption",
}


def _sub_for(key: str) -> str:
    if key in _SUB_EXACT:
        return _SUB_EXACT[key]
    for prefix, label in _SUBS:
        if key.startswith(prefix):
            return label
    return ""


def _with_subs(group: SettingGroup) -> tuple[Setting, ...]:
    tagged = [
        Setting(**{**s.__dict__, "group": group.id, "sub": _sub_for(s.key)})
        for s in group.settings
    ]

    if len(tagged) <= 6 or len({s.sub for s in tagged if s.sub}) < 2:
        return tuple(Setting(**{**s.__dict__, "sub": ""}) for s in tagged)

    order: list[str] = []
    for s in tagged:
        if s.sub not in order:
            order.append(s.sub)
    return tuple(sorted(tagged, key=lambda s: order.index(s.sub)))


_CATEGORY = {
    "website": "Browser surface",
    "acefone": "Telephony",
    "call_transfer": "During a call", "limits": "During a call",
    "ingestion": "Campaign triggers",
    "webhooks": "Campaign triggers",
    "stt": "Voice stack", "tts": "Voice stack",
    "turn": "Voice stack", "audio": "Voice stack",
    "pw_chat": "Language model",
    "runtime": "Server", "deploy_server": "Server",
}

CATEGORY_ORDER: dict[str, tuple[str, ...]] = {
    "Website": ("Browser surface",),
    "Call": ("Telephony", "During a call", "Campaign triggers"),
    "Common": ("Voice stack", "Language model", "Server"),
}

GROUPS: tuple[SettingGroup, ...] = tuple(
    SettingGroup(
        id=g.id,
        title=g.title,
        blurb=g.blurb,
        section=g.section,
        category=_CATEGORY.get(g.id, ""),
        settings=_with_subs(g),
    )
    for g in _GROUPS
)

SETTINGS: dict[str, Setting] = {s.key: s for g in GROUPS for s in g.settings}

SECTIONS: tuple[str, ...] = ("Website", "Call", "Common")


def all_keys() -> tuple[str, ...]:
    return tuple(SETTINGS)


def get_setting(key: str) -> Setting | None:
    return SETTINGS.get(key)


def describe() -> dict[str, Any]:
    out = []
    for name in SECTIONS:
        groups = [g for g in GROUPS if g.section == name]
        order = CATEGORY_ORDER.get(name, ())
        categories = []
        for category in order:
            members = [g.to_dict() for g in groups if g.category == category]
            if members:
                categories.append({"name": category, "groups": members})
        loose = [g.to_dict() for g in groups if g.category not in order]
        if loose:
            categories.append({"name": "", "groups": loose})
        out.append(
            {
                "name": name,
                "categories": categories,
                "groups": [g.to_dict() for g in groups],
            }
        )
    return {"sections": out}


class ValidationError(ValueError):

    def __init__(self, key: str, message: str):
        self.key = key
        super().__init__(message)


def coerce(key: str, raw: Any) -> str:
    setting = SETTINGS.get(key)
    if setting is None:
        raise ValidationError(key, f"{key} is not a known setting")

    if raw is None:
        raw = ""
    if isinstance(raw, bool):
        raw = "true" if raw else "false"
    value = str(raw).strip()

    if setting.type == "bool":
        if value.lower() not in ("true", "false", "1", "0", "yes", "no", "on", "off"):
            raise ValidationError(key, f"{setting.label} must be on or off")
        return "true" if value.lower() in ("true", "1", "yes", "on") else "false"

    if setting.type == "number":
        if value == "":
            return ""
        try:
            number = float(value)
        except ValueError:
            raise ValidationError(key, f"{setting.label} must be a number")
        if setting.minimum is not None and number < setting.minimum:
            raise ValidationError(key, f"{setting.label} cannot be below {_trim(setting.minimum)}")
        if setting.maximum is not None and number > setting.maximum:
            raise ValidationError(key, f"{setting.label} cannot be above {_trim(setting.maximum)}")
        if setting.step is not None and float(setting.step).is_integer() and setting.step >= 1:
            if not number.is_integer():
                raise ValidationError(key, f"{setting.label} must be a whole number")
        return _trim(number)

    if setting.type == "select":
        if value not in setting.options:
            allowed = ", ".join(o or "(empty)" for o in setting.options)
            raise ValidationError(key, f"{setting.label} must be one of: {allowed}")
        return value

    if setting.type == "json":
        if value == "":
            return ""
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as e:
            raise ValidationError(key, f"{setting.label} is not valid JSON: {e.msg}")
        if not isinstance(parsed, dict):
            raise ValidationError(key, f"{setting.label} must be a JSON object")
        return json.dumps(parsed, ensure_ascii=False)

    return value


def _trim(number: float) -> str:
    return str(int(number)) if float(number).is_integer() else str(number)
