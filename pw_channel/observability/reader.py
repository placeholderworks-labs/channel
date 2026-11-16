from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import AsyncIterator

_CHUNK = 64 * 1024

POLL_SECS = 0.25

MAX_LINE_BYTES = 64 * 1024

LOG_BACKUPS_TO_SCAN = 9


def tail_lines(path: Path | str, limit: int = 200) -> list[str]:
    path = Path(path)
    if limit <= 0:
        return []

    collected: list[str] = []
    for candidate in [path] + [
        path.with_name(f"{path.name}.{n}") for n in range(1, LOG_BACKUPS_TO_SCAN + 1)
    ]:
        if len(collected) >= limit:
            break
        chunk = _tail_one(candidate, limit - len(collected))
        if chunk:
            collected = chunk + collected
        elif not candidate.exists():
            break

    return collected[-limit:]


def _tail_one(path: Path, limit: int) -> list[str]:
    if limit <= 0:
        return []
    try:
        size = path.stat().st_size
    except OSError:
        return []
    if size == 0:
        return []

    try:
        with path.open("rb") as handle:
            blocks: list[bytes] = []
            newlines = 0
            position = size

            while position > 0 and newlines <= limit:
                read_size = min(_CHUNK, position)
                position -= read_size
                handle.seek(position)
                block = handle.read(read_size)
                newlines += block.count(b"\n")
                blocks.insert(0, block)

            data = b"".join(blocks)
    except OSError:
        return []

    lines = data.split(b"\n")
    if position > 0 and lines:
        lines = lines[1:]

    decoded = [line.decode("utf-8", "replace") for line in lines if line.strip()]
    return decoded[-limit:]


def _inode(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
        return (stat.st_ino, stat.st_dev)
    except OSError:
        return None


async def follow_lines(
    path: Path | str,
    *,
    from_end: bool = True,
    poll_secs: float = POLL_SECS,
) -> AsyncIterator[str | None]:
    path = Path(path)
    handle = None
    handle_id: tuple[int, int] | None = None
    buffer = b""

    def close() -> None:
        nonlocal handle, handle_id
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
        handle = None
        handle_id = None

    try:
        while True:
            if handle is None:
                try:
                    handle = path.open("rb")
                    handle_id = _inode(path)
                    if from_end:
                        handle.seek(0, os.SEEK_END)
                    buffer = b""
                except OSError:
                    await asyncio.sleep(poll_secs)
                    continue

            chunk = handle.read(_CHUNK)

            if chunk:
                buffer += chunk
                while b"\n" in buffer:
                    line, _, buffer = buffer.partition(b"\n")
                    if line.strip():
                        yield line[:MAX_LINE_BYTES].decode("utf-8", "replace")
                if len(buffer) > MAX_LINE_BYTES:
                    yield buffer[:MAX_LINE_BYTES].decode("utf-8", "replace")
                    buffer = b""
                continue

            if _rotated(path, handle, handle_id):
                close()
                from_end = False
                continue

            await asyncio.sleep(poll_secs)
            yield None
    finally:
        close()


def _rotated(path: Path, handle, handle_id: tuple[int, int] | None) -> bool:
    current = _inode(path)
    if current is None:
        return False
    if handle_id is not None and current != handle_id:
        return True
    try:
        return path.stat().st_size < handle.tell()
    except OSError:
        return False
