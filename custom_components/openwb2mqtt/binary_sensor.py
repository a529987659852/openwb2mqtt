"""The openwbmqtt component for controlling the openWB wallbox via home assistant / MQTT."""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .common import OpenWBEntity, is_supported
from .const import (
    BINARY_SENSORS_BY_DEVICE_TYPE,
    OpenWBBinarySensorEntityDescription,
    _to_bool,
)
from .coordinator import OpenWBConfigEntry

# The coordinator does all updates, so entities never update in parallel
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenWBConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors for openWB."""
    coordinator = entry.runtime_data
    descriptions = BINARY_SENSORS_BY_DEVICE_TYPE.get(coordinator.device_type, [])
    async_add_entities(
        OpenWBBinarySensor(coordinator, description, Platform.BINARY_SENSOR)
        for description in descriptions
        if is_supported(description, coordinator.transport)
    )


class OpenWBBinarySensor(OpenWBEntity, BinarySensorEntity):
    """Binary sensor of a simpleAPI device."""

    entity_description: OpenWBBinarySensorEntityDescription

    @property
    def is_on(self) -> bool | None:
        """Return the state of the binary sensor."""
        return _to_bool(self.get_value())
