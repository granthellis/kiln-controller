"""DataUpdateCoordinator for the Kiln Controller integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import KilnApiClient, KilnApiError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class KilnDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls /api/status and /api/profiles and exposes a merged dict.

    ``data`` is ``{"status": {...}, "profiles": [{...}, ...]}``.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: KilnApiClient,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            status = await self.client.async_get_status()
            profiles = await self.client.async_get_profiles()
        except KilnApiError as err:
            raise UpdateFailed(str(err)) from err
        return {"status": status, "profiles": profiles}

    @property
    def status(self) -> dict[str, Any]:
        """Convenience accessor for the latest status dict."""
        return (self.data or {}).get("status", {})

    @property
    def profile_names(self) -> list[str]:
        """Names of all stored profiles, sorted."""
        profiles = (self.data or {}).get("profiles", [])
        return sorted(
            p["name"] for p in profiles if isinstance(p, dict) and "name" in p
        )
