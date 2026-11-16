from abc import ABC, abstractmethod
from typing import ClassVar


class STTProvider(ABC):
    name: ClassVar[str]
    external_turns: ClassVar[bool] = False

    def model_for(self, model: str) -> str:
        return model

    @abstractmethod
    def build(self, params: dict, channel: str | None):
        pass

    async def warmup(self) -> None:
        return None
