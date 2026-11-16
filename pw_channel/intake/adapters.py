import logging

from pw_sdk import SDK_VERSION, Adapter
from pw_sdk.loader import AdapterLoadError, discover, instantiate

logger = logging.getLogger(__name__)

_instances: dict[str, Adapter] = {}
_errors: dict[str, str] = {}


def load_all() -> dict[str, Adapter]:
    _errors.clear()
    for name, cls in discover().items():
        if name in _instances:
            continue
        try:
            _instances[name] = instantiate(cls, name)
        except AdapterLoadError as error:
            _errors[name] = str(error)
            logger.error(f"[adapters] {error}")
    return dict(_instances)


def get(name: str) -> Adapter:
    if name not in _instances:
        load_all()
    if name not in _instances:
        reason = _errors.get(name) or f"adapter {name!r} is not installed"
        raise AdapterLoadError(reason)
    return _instances[name]


def register(name: str, adapter: Adapter) -> None:
    _instances[name] = adapter


def report() -> dict:
    load_all()
    return {
        "sdk": SDK_VERSION,
        "loaded": {name: adapter.describe() for name, adapter in sorted(_instances.items())},
        "errors": dict(_errors),
    }


def require(names: list[str]) -> None:
    load_all()
    missing = [name for name in names if name and name not in _instances]
    if missing:
        details = "; ".join(_errors.get(name, f"{name} not installed") for name in missing)
        raise AdapterLoadError(f"configured adapters could not be loaded: {details}")
