"""Base entity for the Kiln Controller integration."""

from __future__ import annotations

from homeassistant.helpers.device_info import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KilnDataUpdateCoordinator


class KilnEntity(CoordinatorEntity[KilnDataUpdateCoordinator]):
    """Base class that groups all kiln entities under one device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: KilnDataUpdateCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Kiln Controller",
            manufacturer="kiln-controller",
        )
