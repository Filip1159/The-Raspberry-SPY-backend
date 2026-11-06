import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from threading import RLock
from typing import Any

# Requests are handled by several threads, so every read-modify-write of a JSON file goes through this lock
_lock = RLock()


def read_json(path: Path) -> Any:
    with _lock, open(path, encoding='utf-8') as file:
        return json.load(file)


def write_json(path: Path, data: Any) -> None:
    """Replaces the file atomically, so a crash or a concurrent reader never sees half-written JSON"""
    with _lock:
        fd, temp_path = tempfile.mkstemp(dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
            os.replace(temp_path, path)
        except BaseException:
            os.unlink(temp_path)
            raise


def update_json(path: Path, update: Callable[[Any], Any]) -> Any:
    with _lock:
        data = update(read_json(path))
        write_json(path, data)
        return data
