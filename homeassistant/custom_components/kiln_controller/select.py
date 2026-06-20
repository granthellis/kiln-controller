"""Profile selector for the Kiln Controller integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import KilnConfigEntry, KilnSelection
from .coordinator import KilnDataUpdateCoordinator
from .entity import KilnEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KilnConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the kiln profile selector."""
    data = entry.runtime_data
    async_add_entities(
        [KilnProfileSelect(data.coordinator, entry.entry_id, data.selection)]
    )


class KilnProfileSelect(KilnEntity, SelectEntity, RestoreEntity):
    """Selects which stored profile the run switch will fire."""

    _attr_translation_key = "profile"

    def __init__(
        self,
        coordinator: KilnDataUpdateCoordinator,
        entry_id: str,
        selection: KilnSelection,
    ) -> None:
        super().__init__(coordinator, entry_id)
        self._selection = selection
        self._attr_unique_id = f"{entry_id}_profile_select"

    @property
    def options(self) -> list[str]:
        return self.coordinator.profile_names

    @property
    def current_option(self) -> str | None:
        return self._selection.profile

    async def async_select_option(self, option: str) -> None:
        self._selection.profile = option
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore the previously selected profile, if still available."""
        await super().async_added_to_hass()
        if self._selection.profile is not None:
            return
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in self.options:
            self._selection.profile = last_state.state

    @callback
    def _handle_coordinator_update(self) -> None:
        # drop a stale selection if its profile was deleted on the kiln
        if self._selection.profile and self._selection.profile not in self.options:
            self._selection.profile = None
        super()._handle_coordinator_update()
