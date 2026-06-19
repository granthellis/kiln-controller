"""Run/stop switch for the Kiln Controller integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import KilnConfigEntry, KilnSelection
from .api import KilnApiError
from .const import STATE_RUNNING
from .coordinator import KilnDataUpdateCoordinator
from .entity import KilnEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KilnConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the kiln run/stop switch."""
    data = entry.runtime_data
    async_add_entities(
        [KilnSwitch(data.coordinator, entry.entry_id, data.selection)]
    )


class KilnSwitch(KilnEntity, SwitchEntity):
    """Switch that runs the selected profile or stops the current run."""

    _attr_translation_key = "run"

    def __init__(
        self,
        coordinator: KilnDataUpdateCoordinator,
        entry_id: str,
        selection: KilnSelection,
    ) -> None:
        super().__init__(coordinator, entry_id)
        self._selection = selection
        self._attr_unique_id = f"{entry_id}_run"

    @property
    def is_on(self) -> bool:
        return self.coordinator.status.get("state") == STATE_RUNNING

    async def async_turn_on(self, **kwargs: Any) -> None:
        if not self._selection.profile:
            raise HomeAssistantError(
                "No kiln profile selected. Choose a profile before starting."
            )
        try:
            await self.coordinator.client.async_run(
                self._selection.profile, self._selection.startat
            )
        except KilnApiError as err:
            raise HomeAssistantError(f"Failed to start kiln: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.client.async_stop()
        except KilnApiError as err:
            raise HomeAssistantError(f"Failed to stop kiln: {err}") from err
        await self.coordinator.async_request_refresh()
