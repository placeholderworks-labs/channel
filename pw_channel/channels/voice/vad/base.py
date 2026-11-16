from abc import ABC, abstractmethod
from typing import ClassVar


class VADProvider(ABC):
    name: ClassVar[str]

    @abstractmethod
    def build(self, params: dict):
        pass
