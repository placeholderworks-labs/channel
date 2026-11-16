import os

from pw_channel.channels.voice.telephony.base import TelephonyError, TelephonyProvider
from pw_sdk.registry import ProviderRegistry

TELEPHONY: ProviderRegistry[TelephonyProvider] = ProviderRegistry("telephony", group="pw.telephony")
TELEPHONY.add("acefone", "pw_channel.channels.voice.telephony.acefone.provider:AcefoneTelephony")
TELEPHONY.add("website", "pw_channel.channels.voice.telephony.webrtc.provider:WebsiteTelephony")

_instances: dict[str, TelephonyProvider] = {}


def get(name: str) -> TelephonyProvider:
    if name not in _instances:
        _instances[name] = TELEPHONY.create(name)
    return _instances[name]


def all_providers() -> list[TelephonyProvider]:
    return [get(name) for name in TELEPHONY.names()]


def outbound() -> TelephonyProvider:
    name = (os.getenv("TELEPHONY_PROVIDER") or "acefone").strip().lower()
    provider = get(name)
    if not provider.supports_outbound:
        raise TelephonyError(f"{name} cannot place outbound calls; set TELEPHONY_PROVIDER", retryable=False)
    if not provider.enabled():
        raise TelephonyError(f"{name} is switched off; set ENABLE_{name.upper()}=true", retryable=False)
    return provider


def for_call(channel: str) -> TelephonyProvider | None:
    return get(channel) if channel in TELEPHONY else None
