import os

from pw_channel.channels.email.providers.base import EmailProvider
from pw_sdk.registry import ProviderRegistry

EMAIL: ProviderRegistry[EmailProvider] = ProviderRegistry("email", group="pw.email")
EMAIL.add("smtp", "pw_channel.channels.email.providers.smtp:SmtpEmail")

_instances: dict[str, EmailProvider] = {}


def provider(name: str | None = None) -> EmailProvider:
    key = (name or os.getenv("EMAIL_PROVIDER") or "smtp").strip().lower()
    if key not in _instances:
        _instances[key] = EMAIL.create(key)
    return _instances[key]
