"""The openwbmqtt component for controlling the openWB wallbox via home assistant / MQTT."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .common import OpenWBEntity, is_supported
from .const import (
    SENSORS_BY_DEVICE_TYPE,
    OpenWBSensorEntityDescription,
)
from .coordinator import OpenWBConfigEntry

_LOGGER = logging.getLogger(__name__)

# The coordinator does all updates, so entities never update in parallel
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenWBConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors for openWB."""
    coordinator = entry.runtime_data
    descriptions = SENSORS_BY_DEVICE_TYPE.get(coordinator.device_type, [])
    async_add_entities(
        OpenWBSensor(coordinator, description, Platform.SENSOR)
        for description in descriptions
        if is_supported(description, coordinator.transport)
    )


class OpenWBSensor(OpenWBEntity, SensorEntity):
    """Representation of an openWB sensor (simpleAPI)."""

    entity_description: OpenWBSensorEntityDescription

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        value = self.get_value()
        value_map = self.entity_description.value_map
        if value_map is not None and value is not None:
            return value_map.get(value, value)
        return value

    @property
    def icon(self) -> str | None:
        """Return the icon of the sensor."""
        if "phases_in_use" in self.entity_description.key:
            try:
                phases = int(self.native_value)
                match phases:
                    case 0:
                        return "mdi:numeric-0-circle-outline"
                    case 1:
                        return "mdi:numeric-1-circle-outline"
                    case 3:
                        return "mdi:numeric-3-circle-outline"
                    case _:
                        return "mdi:numeric"
            except (ValueError, TypeError):
                pass
        return self.entity_description.icon
