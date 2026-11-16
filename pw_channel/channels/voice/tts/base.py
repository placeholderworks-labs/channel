import logging
from abc import ABC, abstractmethod
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


class TTSProvider(ABC):
    name: ClassVar[str]
    voice_setting: ClassVar[str] = ""
    model_setting: ClassVar[str] = ""
    key_setting: ClassVar[str] = ""
    style_setting: ClassVar[str] = ""

    @staticmethod
    def setting(key: str) -> Any:
        from pw_channel import config

        return getattr(config, key, "") if key else ""

    def default_voice(self) -> str:
        return self.setting(self.voice_setting) or ""

    def default_model(self) -> str:
        return self.setting(self.model_setting) or ""

    def ready(self) -> bool:
        return bool(self.setting(self.key_setting))

    def setting_keys(self) -> dict[str, str]:
        keys = {"voice": self.voice_setting, "model": self.model_setting, "key": self.key_setting}
        if self.style_setting:
            keys["style"] = self.style_setting
        return keys

    @staticmethod
    def pick(overrides: dict, key: str, fallback: Any) -> Any:
        value = overrides.get(key)
        return value if value not in (None, "") else fallback

    @abstractmethod
    def build(self, overrides: dict):
        pass

    async def warmup(self) -> None:
        return None

    def set_language(self, service, locale: str) -> bool:
        logger.warning(f"[language] {self.name} cannot switch the spoken language during a call")
        return False
