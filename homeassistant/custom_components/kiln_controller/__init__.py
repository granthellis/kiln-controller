"""The Kiln Controller integration."""

from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KilnApiClient
from .const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
from .coordinator import KilnDataUpdateCoordinator

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
]


@dataclass
class KilnSelection:
    """In-memory selection shared between the select/number and switch entities."""

    profile: str | None = None
    startat: int = 0


@dataclass
class KilnRuntimeData:
    """Runtime data stored on the config entry."""

    coordinator: KilnDataUpdateCoordinator
    selection: KilnSelection = field(default_factory=KilnSelection)


KilnConfigEntry = ConfigEntry[KilnRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: KilnConfigEntry) -> bool:
    """Set up Kiln Controller from a config entry."""
    session = async_get_clientsession(hass)
    client = KilnApiClient(entry.data[CONF_HOST], entry.data[CONF_PORT], session)

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = KilnDataUpdateCoordinator(hass, client, scan_interval)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = KilnRuntimeData(coordinator=coordinator)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KilnConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: KilnConfigEntry) -> None:
    """Reload the entry when options change (e.g. scan interval)."""
    await hass.config_entries.async_reload(entry.entry_id)
