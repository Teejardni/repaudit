import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

_xdg_cache = os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")
CACHE_DIR = Path(_xdg_cache) / ".repaudit" / "cache"

DEFAULT_TTL = 60 * 60 * 36


def _cache_path(key: str) -> Path:
    hashed = hashlib.md5(key.encode()).hexdigest()
    return CACHE_DIR / f"{hashed}.json"


def _is_fresh(path: Path, ttl: int) -> bool:
    return (time.time() - path.stat().st_mtime) < ttl


def get(key: str, ttl: int = DEFAULT_TTL) -> Any | None:
    path = _cache_path(key)
    if path.exists() and _is_fresh(path, ttl):
        return json.loads(path.read_text())
    return None


def set(key: str, value: Any) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(key).write_text(json.dumps(value))


def clear() -> int:
    if not CACHE_DIR.exists():
        return 0
    deleted = 0
    for f in CACHE_DIR.glob("*.json"):
        f.unlink()
        deleted += 1
    return deleted


def stats() -> dict:
    if not CACHE_DIR.exists():
        return {"entries": 0, "size_bytes": 0, "path": str(CACHE_DIR)}
    files = list(CACHE_DIR.glob("*.json"))
    return {
        "entries": len(files),
        "size_bytes": sum(f.stat().st_size for f in files),
        "path": str(CACHE_DIR),
    }
