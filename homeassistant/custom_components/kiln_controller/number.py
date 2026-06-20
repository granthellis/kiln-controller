"""Start-at (minutes) control for the Kiln Controller integration."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
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
    """Set up the kiln start-at number."""
    data = entry.runtime_data
    async_add_entities(
        [KilnStartAtNumber(data.coordinator, entry.entry_id, data.selection)]
    )


class KilnStartAtNumber(KilnEntity, NumberEntity, RestoreEntity):
    """Minutes into the profile at which the next run should start."""

    _attr_translation_key = "startat"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(
        self,
        coordinator: KilnDataUpdateCoordinator,
        entry_id: str,
        selection: KilnSelection,
    ) -> None:
        super().__init__(coordinator, entry_id)
        self._selection = selection
        self._attr_unique_id = f"{entry_id}_startat"

    @property
    def native_max_value(self) -> float:
        """Cap at the active profile duration when one is loaded."""
        total = self.coordinator.status.get("totaltime")
        if isinstance(total, (int, float)) and total > 0:
            return float(int(total // 60))
        return 1440.0  # 24h fallback when nothing is loaded

    @property
    def native_value(self) -> float:
        return float(self._selection.startat)

    async def async_set_native_value(self, value: float) -> None:
        self._selection.startat = int(value)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore the previously set start-at value."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            try:
                self._selection.startat = int(float(last_state.state))
            except (TypeError, ValueError):
                self._selection.startat = 0
