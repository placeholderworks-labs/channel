import logging

logger = logging.getLogger(__name__)

ROUTE_TAG = "pw-dynamic"

_installers: list = []
_app = None


def installer(fn):
    if fn not in _installers:
        _installers.append(fn)
    return fn


def install(app) -> list[str]:
    global _app
    _app = app

    kept = [r for r in app.router.routes if getattr(r, "name", "") != ROUTE_TAG]
    removed = len(app.router.routes) - len(kept)
    app.router.routes = list(kept)

    boundary = len(kept)
    paths: list[str] = []
    for fn in _installers:
        paths.extend(fn(app) or [])

    fresh = app.router.routes[boundary:]
    app.router.routes = fresh + kept

    app.openapi_schema = None

    if removed:
        logger.info(f"[routes] rebuilt — {removed} replaced by {len(fresh)}")
    return paths


def rebuild(reason: str = "a config change") -> list[str]:
    if _app is None:
        logger.warning("[routes] rebuild requested before the app was installed")
        return []
    logger.info(f"[routes] rebuilding after {reason}")
    return install(_app)
