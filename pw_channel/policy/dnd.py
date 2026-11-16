import os
from abc import ABC, abstractmethod

from pw_sdk.registry import ProviderRegistry


class DndChecker(ABC):
    name: str

    @abstractmethod
    async def is_blocked(self, phone_e164: str) -> bool:
        pass


class NoDndCheck(DndChecker):
    name = "none"

    async def is_blocked(self, phone_e164: str) -> bool:
        return False


class StaticDndList(DndChecker):
    name = "static"

    def __init__(self):
        self.numbers = {item.strip() for item in os.getenv("DND_NUMBERS", "").split(",") if item.strip()}

    async def is_blocked(self, phone_e164: str) -> bool:
        return phone_e164 in self.numbers


DND_PROVIDERS: ProviderRegistry[DndChecker] = ProviderRegistry("dnd", group="pw.dnd")
DND_PROVIDERS.add("none", NoDndCheck)
DND_PROVIDERS.add("static", StaticDndList)

_checker: DndChecker | None = None


def checker() -> DndChecker:
    global _checker
    if _checker is None:
        _checker = DND_PROVIDERS.create(os.getenv("DND_PROVIDER", "none"))
    return _checker
