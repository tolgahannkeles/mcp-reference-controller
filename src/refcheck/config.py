"""Settings, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_cache() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "refcheck" / "cache.sqlite3"


@dataclass
class Settings:
    # Contact e-mail sent to Crossref/OpenAlex ("polite pool": faster, more reliable).
    mailto: str | None = field(default_factory=lambda: os.environ.get("REFCHECK_MAILTO") or None)
    openalex_api_key: str | None = field(default_factory=lambda: os.environ.get("REFCHECK_OPENALEX_API_KEY") or None)
    cache_path: Path | None = field(
        default_factory=lambda: None
        if os.environ.get("REFCHECK_CACHE") == "off"
        else Path(os.environ.get("REFCHECK_CACHE") or _default_cache())
    )
    cache_ttl_days: int = 30
    timeout: float = 20.0
    max_concurrent_requests: int = 4
