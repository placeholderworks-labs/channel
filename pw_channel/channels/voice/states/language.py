from dataclasses import dataclass, field

from pw_channel import config


@dataclass
class LanguageState:

    current: str = field(default_factory=lambda: config.BOT_LANGUAGE)

    @property
    def profile(self) -> dict:
        return config.LANGUAGES[self.current]

    @property
    def locale(self) -> str:
        return self.profile["murf"]

    def is_supported(self, language: str) -> bool:
        return language.strip().lower() in config.LANGUAGES

    def set(self, language: str) -> bool:
        target = language.strip().lower()
        if target not in config.LANGUAGES or target == self.current:
            return False
        self.current = target
        return True
