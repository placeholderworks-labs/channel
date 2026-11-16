import os

from pw_sdk import config as client_config

ENV_MAP = {
    "TELEPHONY_PROVIDER": "voice.telephony",
    "STT_PROVIDER": "voice.stt",
    "TTS_PROVIDER": "voice.tts",
    "WHATSAPP_PROVIDER": "whatsapp.provider",
    "WHATSAPP_SENDER_NUMBER": "whatsapp.sender",
    "EMAIL_PROVIDER": "email.provider",
    "EMAIL_SENDER": "email.sender",
    "COMPANY_NAME": "branding.company",
    "COMPANY_EMAIL_SPOKEN": "branding.email_spoken",
    "AGENT_NAME": "branding.agent_name",
    "CLIENT_TIMEZONE": "client.timezone",
    "CLIENT_COUNTRY": "client.country",
    "CLIENT_SLUG": "client.slug",
}

_prepared: client_config.ClientConfig | None = None


def prepare(config: client_config.ClientConfig | None = None) -> client_config.ClientConfig:
    global _prepared
    if _prepared is not None and config is None:
        return _prepared
    loaded = client_config.use(config or client_config.current())
    client_config.apply_env(loaded, ENV_MAP)
    os.environ.setdefault("PW_SERVICE", "channel")
    _prepared = loaded
    return loaded
