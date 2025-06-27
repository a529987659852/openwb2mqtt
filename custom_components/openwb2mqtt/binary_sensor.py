"""The openwbmqtt component for controlling the openWB wallbox via home assistant / MQTT."""

from __future__ import annotations

import logging

from homeassistant.components import mqtt
from homeassistant.components.binary_sensor import (
    DOMAIN as BINARY_SENSOR_DOMAIN,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .common import OpenWBBaseEntity, async_setup_binary_sensors
from .const import (
    BINARY_SENSORS_PER_BATTERY,
    BINARY_SENSORS_PER_CHARGEPOINT,
    BINARY_SENSORS_PER_COUNTER,
    BINARY_SENSORS_PER_PVGENERATOR,
    BINARY_SENSORS_PER_VEHICLE,
    DEVICETYPE,
    openwbBinarySensorEntityDescription,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, config: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up binary sensors for openWB."""
    device_type = config.data[DEVICETYPE]
    topic_template = "{mqtt_root}/{device_type}/{device_id}/get/{key}"

    if device_type == "chargepoint":
        await async_setup_binary_sensors(
            hass,
            config,
            async_add_entities,
            BINARY_SENSORS_PER_CHARGEPOINT,
            topic_template,
            "Chargepoint",
        )
    elif device_type == "counter":
        await async_setup_binary_sensors(
            hass,
            config,
            async_add_entities,
            BINARY_SENSORS_PER_COUNTER,
            topic_template,
            "Counter",
        )
    elif device_type == "bat":
        await async_setup_binary_sensors(
            hass,
            config,
            async_add_entities,
            BINARY_SENSORS_PER_BATTERY,
            topic_template,
            "Battery",
        )
    elif device_type == "pv":
        await async_setup_binary_sensors(
            hass,
            config,
            async_add_entities,
            BINARY_SENSORS_PER_PVGENERATOR,
            topic_template,
            "PV",
        )
    elif device_type == "vehicle":
        await async_setup_binary_sensors(
            hass,
            config,
            async_add_entities,
            BINARY_SENSORS_PER_VEHICLE,
            topic_template,
            "Vehicle",
        )


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
        self.entity_id = f"{BINARY_SENSOR_DOMAIN}.{uniqueID}-{description.name}"
        self._attr_name = description.name

    async def async_added_to_hass(self):
        """Subscribe to MQTT events."""

        @callback
        def message_received(message):
            """Handle new MQTT messages."""
            try:
                self._attr_is_on = bool(int(message.payload))
            except ValueError:
                if message.payload == "true":
                    self._attr_is_on = True
                elif message.payload == "false":
                    self._attr_is_on = False
            # Update entity state with value published on MQTT.
            self.async_write_ha_state()

        await mqtt.async_subscribe(
            self.hass,
            self.entity_description.mqttTopicCurrentValue,
            message_received,
            1,
        )
