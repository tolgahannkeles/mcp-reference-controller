"""Shared HTTP client with an on-disk JSON cache and polite retry behaviour."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import httpx

from . import __version__
from .config import Settings


class NotFound(Exception):
    pass


class Cache:
    def __init__(self, path: Path | None, ttl_seconds: int):
        self.ttl = ttl_seconds
        self.db: sqlite3.Connection | None = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(path, check_same_thread=False)
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS http (key TEXT PRIMARY KEY, ts REAL, body TEXT)"
            )

    @staticmethod
    def key(url: str, params: dict | None) -> str:
        blob = url + "?" + json.dumps(params or {}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    def get(self, key: str) -> Any | None:
        if self.db is None:
            return None
        row = self.db.execute("SELECT ts, body FROM http WHERE key = ?", (key,)).fetchone()
        if row is None or time.time() - row[0] > self.ttl:
            return None
        return json.loads(row[1])

    def put(self, key: str, body: Any) -> None:
        if self.db is None:
            return
        self.db.execute(
            "INSERT OR REPLACE INTO http (key, ts, body) VALUES (?, ?, ?)",
            (key, time.time(), json.dumps(body)),
        )
        self.db.commit()


_NOT_FOUND_MARKER = {"__not_found__": True}


class HttpClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        ua = f"refcheck/{__version__} (reference checker MCP"
        ua += f"; mailto:{settings.mailto})" if settings.mailto else ")"
        self.client = client or httpx.AsyncClient(
            timeout=settings.timeout, headers={"User-Agent": ua}, follow_redirects=True
        )
        self.cache = Cache(settings.cache_path, settings.cache_ttl_days * 86400)
        self._sem = asyncio.Semaphore(settings.max_concurrent_requests)

    async def get_json(self, url: str, params: dict | None = None) -> Any:
        """GET JSON; raises NotFound on 404. 404s are cached too."""
        key = Cache.key(url, params)
        cached = self.cache.get(key)
        if cached == _NOT_FOUND_MARKER:
            raise NotFound(url)
        if cached is not None:
            return cached

        delay = 1.0
        for attempt in range(4):
            async with self._sem:
                resp = await self.client.get(url, params=params)
            if resp.status_code == 404:
                self.cache.put(key, _NOT_FOUND_MARKER)
                raise NotFound(url)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                retry_after = resp.headers.get("Retry-After")
                await asyncio.sleep(float(retry_after) if retry_after and retry_after.isdigit() else delay)
                delay *= 2
                continue
            resp.raise_for_status()
            body = resp.json()
            self.cache.put(key, body)
            return body
        raise RuntimeError("unreachable")

    async def aclose(self) -> None:
        await self.client.aclose()
