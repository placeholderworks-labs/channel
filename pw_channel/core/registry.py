import logging
import os

from pw_channel.core.channel import Channel
from pw_sdk.registry import ProviderRegistry

logger = logging.getLogger(__name__)

CHANNELS: ProviderRegistry[Channel] = ProviderRegistry("channel", group="pw.channels")
CHANNELS.add("voice", "pw_channel.channels.voice.channel:VoiceChannel")
CHANNELS.add("whatsapp", "pw_channel.channels.whatsapp.channel:WhatsAppChannel")
CHANNELS.add("email", "pw_channel.channels.email.channel:EmailChannel")

_active: dict[str, Channel] = {}


def enabled_names() -> list[str]:
    raw = os.getenv("ENABLED_CHANNELS", "voice,whatsapp,email")
    return [name.strip() for name in raw.split(",") if name.strip()]


def load() -> dict[str, Channel]:
    for name in enabled_names():
        if name in _active:
            continue
        try:
            _active[name] = CHANNELS.create(name)
        except ImportError as error:
            logger.warning(f"[channels] {name} is enabled but its extra is not installed: {error}")
    return _active


def get(name: str) -> Channel | None:
    return load().get(name)


def active() -> dict[str, Channel]:
    return dict(load())


def register(channel: Channel) -> None:
    _active[channel.name] = channel


def reset() -> None:
    _active.clear()
