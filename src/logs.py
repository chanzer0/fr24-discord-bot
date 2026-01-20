from __future__ import annotations

from collections import deque
import glob
import os
from typing import Iterable


def _iter_log_paths(log_dir: str, base_name: str = "bot.log") -> list[str]:
    pattern = os.path.join(log_dir, f"{base_name}*")
    paths = glob.glob(pattern)
    paths.sort(key=lambda path: os.path.getmtime(path))
    return paths


def read_log_tail(
    log_dir: str,
    lines: int = 200,
    contains: str | None = None,
    base_name: str = "bot.log",
) -> list[str]:
    if lines <= 0:
        return []
    if not os.path.isdir(log_dir):
        return []
    needle = contains.lower().strip() if contains else None
    buffer: deque[str] = deque(maxlen=lines)
    for path in _iter_log_paths(log_dir, base_name):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                for raw_line in handle:
                    line = raw_line.rstrip("\n")
                    if needle and needle not in line.lower():
                        continue
                    buffer.append(line)
        except OSError:
            continue
    return list(buffer)


def format_log_block(lines: Iterable[str], limit: int = 1900) -> str:
    text = "\n".join(lines)
    if len(text) > limit:
        text = text[-limit:]
    return text
