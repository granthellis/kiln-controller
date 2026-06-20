"""Sensor entities for the Kiln Controller integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import KilnConfigEntry
from .const import (
    ATTR_PROFILE_DATA,
    ATTR_START_TIME,
    ATTR_TOTALTIME,
    STATE_RUNNING,
)
from .coordinator import KilnDataUpdateCoordinator
from .entity import KilnEntity


@dataclass(frozen=True, kw_only=True)
class KilnSensorEntityDescription(SensorEntityDescription):
    """Describes a passthrough kiln sensor backed by a status field."""

    value_fn: Callable[[dict[str, Any]], Any]
    is_temperature: bool = False


PASSTHROUGH_SENSORS: tuple[KilnSensorEntityDescription, ...] = (
    KilnSensorEntityDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        is_temperature=True,
        value_fn=lambda s: _round(s.get("temperature"), 1),
    ),
    KilnSensorEntityDescription(
        key="target",
        translation_key="target",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        is_temperature=True,
        value_fn=lambda s: _round(s.get("target"), 1),
    ),
    KilnSensorEntityDescription(
        key="state",
        translation_key="state",
        value_fn=lambda s: s.get("state"),
    ),
    KilnSensorEntityDescription(
        key="profile",
        translation_key="profile",
        value_fn=lambda s: s.get("profile"),
    ),
    KilnSensorEntityDescription(
        key="cost",
        translation_key="cost",
        # kiln reports a currency symbol (e.g. "$"), not an ISO code, so this is
        # a plain numeric sensor rather than a MONETARY device class
        value_fn=lambda s: _round(s.get("cost"), 2),
    ),
    KilnSensorEntityDescription(
        key="kwh_rate",
        translation_key="kwh_rate",
        value_fn=lambda s: s.get("kwh_rate"),
    ),
    KilnSensorEntityDescription(
        key="heat",
        translation_key="heat",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.get("heat"),
    ),
    KilnSensorEntityDescription(
        key="runtime",
        translation_key="runtime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        value_fn=lambda s: _round(s.get("runtime"), 0),
    ),
    KilnSensorEntityDescription(
        key="totaltime",
        translation_key="totaltime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        value_fn=lambda s: _round(s.get("totaltime"), 0),
    ),
)


def _round(value: Any, digits: int) -> Any:
    """Round numeric values, passing through None / non-numerics untouched."""
    if isinstance(value, (int, float)):
        return round(value, digits) if digits else round(value)
    return value


def _temp_unit(status: dict[str, Any]) -> str:
    """Return the HA temperature unit for the configured kiln scale."""
    if str(status.get("temp_scale", "c")).lower().startswith("f"):
        return UnitOfTemperature.FAHRENHEIT
    return UnitOfTemperature.CELSIUS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KilnConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the kiln sensors."""
    coordinator = entry.runtime_data.coordinator
    entities: list[SensorEntity] = [
        KilnSensor(coordinator, entry.entry_id, description)
        for description in PASSTHROUGH_SENSORS
    ]
    entities.append(KilnTimeRemainingSensor(coordinator, entry.entry_id))
    entities.append(KilnProjectedFinishSensor(coordinator, entry.entry_id))
    entities.append(KilnProjectedTargetSensor(coordinator, entry.entry_id))
    async_add_entities(entities)


class KilnSensor(KilnEntity, SensorEntity):
    """A passthrough sensor mapped to a single status field."""

    entity_description: KilnSensorEntityDescription

    def __init__(
        self,
        coordinator: KilnDataUpdateCoordinator,
        entry_id: str,
        description: KilnSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, entry_id)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self.entity_description.is_temperature:
            return _temp_unit(self.coordinator.status)
        return self.entity_description.native_unit_of_measurement

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.status)


class KilnTimeRemainingSensor(KilnEntity, SensorEntity):
    """Seconds remaining in the current run, with an hh:mm attribute."""

    _attr_translation_key = "time_remaining"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS

    def __init__(
        self, coordinator: KilnDataUpdateCoordinator, entry_id: str
    ) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_time_remaining"

    def _remaining_seconds(self) -> float | None:
        status = self.coordinator.status
        if status.get("state") != STATE_RUNNING:
            return None
        if "time_remaining" in status:
            return max(0, float(status["time_remaining"]))
        total = status.get(ATTR_TOTALTIME)
        runtime = status.get("runtime")
        if total is None or runtime is None:
            return None
        return max(0, float(total) - float(runtime))

    @property
    def native_value(self) -> int | None:
        remaining = self._remaining_seconds()
        return None if remaining is None else int(remaining)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        remaining = self._remaining_seconds()
        if remaining is None:
            return {"hh_mm": None}
        minutes_total = int(remaining // 60)
        return {"hh_mm": f"{minutes_total // 60}:{minutes_total % 60:02d}"}


class KilnProjectedFinishSensor(KilnEntity, SensorEntity):
    """Wall-clock time the current run is projected to finish."""

    _attr_translation_key = "projected_finish"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self, coordinator: KilnDataUpdateCoordinator, entry_id: str
    ) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_projected_finish"

    @property
    def native_value(self) -> datetime | None:
        status = self.coordinator.status
        if status.get("state") != STATE_RUNNING:
            return None
        start = status.get(ATTR_START_TIME)
        total = status.get(ATTR_TOTALTIME)
        if start is None or total is None:
            return None
        return dt_util.utc_from_timestamp(float(start) + float(total))


class KilnProjectedTargetSensor(KilnEntity, SensorEntity):
    """Current target temperature, with the full projected target curve attached.

    The ``forecast`` attribute maps each profile point to a wall-clock time so a
    chart card can plot the projected target line across the whole run.
    """

    _attr_translation_key = "projected_target"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: KilnDataUpdateCoordinator, entry_id: str
    ) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_projected_target"

    @property
    def native_unit_of_measurement(self) -> str:
        return _temp_unit(self.coordinator.status)

    @property
    def native_value(self) -> Any:
        return _round(self.coordinator.status.get("target"), 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        status = self.coordinator.status
        profile_data = status.get(ATTR_PROFILE_DATA)
        start = status.get(ATTR_START_TIME)
        forecast: list[dict[str, Any]] = []
        if (
            status.get("state") == STATE_RUNNING
            and isinstance(profile_data, list)
            and start is not None
        ):
            for point in profile_data:
                try:
                    offset, temp = point[0], point[1]
                except (TypeError, IndexError):
                    continue
                when = dt_util.utc_from_timestamp(float(start) + float(offset))
                forecast.append(
                    {"datetime": when.isoformat(), "temperature": temp}
                )
        return {"forecast": forecast, ATTR_PROFILE_DATA: profile_data}
