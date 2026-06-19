"""Thin async client for the kiln-controller HTTP API."""

from __future__ import annotations

from typing import Any

import aiohttp


class KilnApiError(Exception):
    """Raised when a request to the kiln-controller API fails."""


class KilnApiClient:
    """Minimal client wrapping the kiln-controller REST endpoints."""

    def __init__(self, host: str, port: int, session: aiohttp.ClientSession) -> None:
        self._base = f"http://{host}:{port}"
        self._session = session

    async def async_get_status(self) -> dict[str, Any]:
        """Return the current oven status (GET /api/status)."""
        return await self._get_json("/api/status")

    async def async_get_profiles(self) -> list[dict[str, Any]]:
        """Return the list of stored profiles (GET /api/profiles)."""
        data = await self._get_json("/api/profiles")
        if not isinstance(data, list):
            raise KilnApiError(f"Unexpected /api/profiles payload: {data!r}")
        return data

    async def async_run(self, profile: str, startat: int = 0) -> dict[str, Any]:
        """Start a firing for ``profile`` (POST /api cmd=run)."""
        return await self._post_json(
            {"cmd": "run", "profile": profile, "startat": startat}
        )

    async def async_stop(self) -> dict[str, Any]:
        """Abort the current run (POST /api cmd=stop)."""
        return await self._post_json({"cmd": "stop"})

    async def _get_json(self, path: str) -> Any:
        try:
            async with self._session.get(f"{self._base}{path}") as resp:
                resp.raise_for_status()
                # the server sends JSON with a text/html content type, so parse
                # the body ourselves rather than relying on resp.json()
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, ValueError) as err:
            raise KilnApiError(f"GET {path} failed: {err}") from err

    async def _post_json(self, body: dict[str, Any]) -> Any:
        try:
            async with self._session.post(f"{self._base}/api", json=body) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, ValueError) as err:
            raise KilnApiError(f"POST /api {body.get('cmd')} failed: {err}") from err
