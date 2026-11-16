import logging
import os

from pw_channel.channels.whatsapp.handler import MessageHandler
from pw_channel.channels.whatsapp.providers.base import WhatsAppProvider
from pw_channel.channels.whatsapp.settings import settings
from pw_sdk.registry import ProviderRegistry

logger = logging.getLogger(__name__)

WHATSAPP: ProviderRegistry[WhatsAppProvider] = ProviderRegistry("whatsapp", group="pw.whatsapp")
WHATSAPP.add("meta", "pw_channel.channels.whatsapp.providers.meta:WhatsAppClient")
WHATSAPP.add("karix", "pw_channel.channels.whatsapp.providers.karix:KarixClient")
WHATSAPP.add("nowonextel", "pw_channel.channels.whatsapp.providers.nowonextel:NowonextelClient")


class ProviderPool:
    def __init__(self):
        self.by_name: dict[str, dict[str, WhatsAppProvider]] = {}
        self.handlers: dict[int, MessageHandler] = {}
        self._build()

    def _add(self, provider: WhatsAppProvider) -> None:
        self.by_name.setdefault(provider.name, {})[provider.sender] = provider
        self.handlers[id(provider)] = MessageHandler(wa_client=provider)

    def _build(self) -> None:
        if settings.meta_configured:
            self._add(WHATSAPP.create("meta"))
        for number in settings.karix_numbers_list:
            self._add(WHATSAPP.create("karix", number))
        for number in settings.nowonextel_numbers_list:
            self._add(WHATSAPP.create("nowonextel", number))

    def names(self) -> list[str]:
        return sorted(self.by_name)

    def providers(self, name: str) -> dict[str, WhatsAppProvider]:
        return self.by_name.get(name, {})

    def pick(self, name: str, to_number: str = "") -> WhatsAppProvider | None:
        found = self.providers(name)
        if not found:
            return None
        if to_number and to_number in found:
            return found[to_number]
        provider = next(iter(found.values()))
        if to_number and len(found) > 1:
            logger.warning(f"[whatsapp] {name}: bot number {to_number} is not configured; using {provider.sender}")
        return provider

    def for_sender(self, sender: str) -> WhatsAppProvider | None:
        sender = (sender or "").lstrip("+")
        for found in self.by_name.values():
            if sender in found:
                return found[sender]
        return None

    def default(self) -> WhatsAppProvider | None:
        sender = (os.getenv("WHATSAPP_SENDER_NUMBER") or settings.voicebot_sender_number or "").lstrip("+")
        if sender and self.for_sender(sender):
            return self.for_sender(sender)
        preferred = (os.getenv("WHATSAPP_PROVIDER") or "").strip().lower()
        if preferred and self.providers(preferred):
            return self.pick(preferred)
        for name in ("meta", "karix", "nowonextel"):
            if self.providers(name):
                return self.pick(name)
        return None

    def handler(self, provider: WhatsAppProvider) -> MessageHandler:
        return self.handlers[id(provider)]


_pool: ProviderPool | None = None


def pool() -> ProviderPool:
    global _pool
    if _pool is None:
        _pool = ProviderPool()
    return _pool
