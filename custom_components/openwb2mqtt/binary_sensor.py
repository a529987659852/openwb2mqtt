"""The openwbmqtt component for controlling the openWB wallbox via home assistant / MQTT."""

from __future__ import annotations

import logging

from homeassistant.components import mqtt
from homeassistant.components.binary_sensor import (
    DOMAIN as BINARY_SENSOR_DOMAIN,
    BinarySensorEntity,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import slugify

from .common import OpenWBBaseEntity, OpenWBEntity, is_supported
from .const import (
    BINARY_SENSORS_BY_DEVICE_TYPE,
    OpenWBBinarySensorEntityDescription,
    _to_bool,
    openwbBinarySensorEntityDescription,
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


class openwbBinarySensor(OpenWBBaseEntity, BinarySensorEntity):
    """Representation of an openWB sensor that is updated via MQTT."""

    entity_description: openwbBinarySensorEntityDescription

    def __init__(
        self,
        uniqueID: str | None,
        device_friendly_name: str,
        mqtt_root: str,
        description: openwbBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor and the openWB device."""
        super().__init__(
            device_friendly_name=device_friendly_name,
            mqtt_root=mqtt_root,
        )

        self.entity_description = description
        self._attr_unique_id = slugify(f"{uniqueID}-{description.name}")
        self.entity_id = (
            f"{BINARY_SENSOR_DOMAIN}.{slugify(f'{uniqueID}_{description.name}')}"
        )
        self._attr_name = description.name

    async def async_added_to_hass(self):
        """Subscribe to MQTT events."""

        @callback
        def message_received(message):
            """Handle new MQTT messages."""
            payload = message.payload

            # Use custom state function if defined
            if (
                hasattr(self.entity_description, "state")
                and self.entity_description.state is not None
            ):
                self._attr_is_on = self.entity_description.state(payload)
            else:
                # Default behavior
                payload = payload.strip().lower()
                try:
                    self._attr_is_on = bool(int(payload))
                except ValueError:
                    if payload in {"true", "on"}:
                        self._attr_is_on = True
                    elif payload in {"false", "off"}:
                        self._attr_is_on = False
                    else:
                        self._attr_is_on = None

            # Update entity state with value published on MQTT.
            self.async_write_ha_state()

        await mqtt.async_subscribe(
            self.hass,
            self.entity_description.mqttTopicCurrentValue,
            message_received,
            1,
        )
