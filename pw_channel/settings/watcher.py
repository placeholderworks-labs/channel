import asyncio
import logging

from pw_channel import config

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None
_last: tuple[int, str] | None = None
_state: dict = {"running": False, "checks": 0, "reloads": 0, "error": None}


def status() -> dict:
    return {
        **_state,
        "intervalSecs": config.SETTINGS_REFRESH_SECS,
        "fingerprint": list(_last) if _last else None,
    }


async def start() -> None:
    global _task, _last

    if not config.USE_DB or config.SETTINGS_REFRESH_SECS <= 0:
        logger.info(
            "[settings] live refresh off — this process picks up changes only when it "
            "applies them itself (set USE_DB=true and SETTINGS_REFRESH_SECS>0 to change that)"
        )
        return

    _last = await _read_fingerprint()
    _task = asyncio.create_task(_loop(), name="settings-watcher")
    _state["running"] = True
    logger.info(
        f"[settings] watching app_settings every {config.SETTINGS_REFRESH_SECS:g}s "
        "— changes apply without a restart"
    )


async def stop() -> None:
    global _task
    _state["running"] = False
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except (asyncio.CancelledError, Exception):
        pass
    _task = None


async def _read_fingerprint() -> tuple[int, str] | None:
    from pw_channel.settings.store import fingerprint

    try:
        return await asyncio.to_thread(fingerprint)
    except Exception as e:
        _state["error"] = str(e)
        return None


async def _loop() -> None:
    global _last

    while True:
        try:
            await asyncio.sleep(config.SETTINGS_REFRESH_SECS)
            _state["checks"] += 1

            current = await _read_fingerprint()
            if current is None or current == _last:
                continue

            _last = current
            changes = await asyncio.to_thread(config.reload)
            _state["error"] = None
            if changes:
                _state["reloads"] += 1
                logger.info(
                    f"[settings] picked up {len(changes)} change(s) from the store: "
                    f"{', '.join(sorted(changes))}"
                )
        except asyncio.CancelledError:
            raise
        except ValueError as e:
            _state["error"] = str(e)
            logger.error(
                f"[settings] the stored settings do not validate ({e}) — staying on the "
                "values already in force"
            )
        except Exception as e:
            _state["error"] = str(e)
            logger.warning(f"[settings] refresh failed, will retry: {e}")
