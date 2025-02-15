"""The openwbmqtt component for controlling the openWB wallbox via home assistant / MQTT."""

from __future__ import annotations

import copy
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

from .common import OpenWBBaseEntity

# Import global values.
from .const import (
    BINARY_SENSORS_PER_BATTERY,
    BINARY_SENSORS_PER_CHARGEPOINT,
    BINARY_SENSORS_PER_COUNTER,
    BINARY_SENSORS_PER_PVGENERATOR,
    BINARY_SENSORS_PER_VEHICLE,
    DEVICEID,
    DEVICETYPE,
    MQTT_ROOT_TOPIC,
    openwbBinarySensorEntityDescription,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, config: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensors for openWB."""
    integrationUniqueID = config.unique_id
    mqttRoot = config.data[MQTT_ROOT_TOPIC]
    devicetype = config.data[DEVICETYPE]
    deviceID = config.data[DEVICEID]

    sensorList = []

    if devicetype == "chargepoint":
        # Create sensors for chargepoint
        BINARY_SENSORS_PER_CHARGEPOINT_CP = copy.deepcopy(
            BINARY_SENSORS_PER_CHARGEPOINT
        )

        for description in BINARY_SENSORS_PER_CHARGEPOINT_CP:
            description.mqttTopicCurrentValue = (
                f"{mqttRoot}/{devicetype}/{deviceID}/get/{description.key}"
            )
            _LOGGER.debug("mqttTopic: %s", description.mqttTopicCurrentValue)

            sensorList.append(
                openwbBinarySensor(
                    uniqueID=f"{integrationUniqueID}",
                    description=description,
                    device_friendly_name=f"Chargepoint {deviceID}",
                    mqtt_root=mqttRoot,
                )
            )
    if devicetype == "counter":
        # Create sensors for counter
        BINARY_SENSORS_PER_COUNTER_CP = copy.deepcopy(BINARY_SENSORS_PER_COUNTER)

        for description in BINARY_SENSORS_PER_COUNTER_CP:
            description.mqttTopicCurrentValue = (
                f"{mqttRoot}/{devicetype}/{deviceID}/get/{description.key}"
            )
            _LOGGER.debug("mqttTopic: %s", description.mqttTopicCurrentValue)

            sensorList.append(
                openwbBinarySensor(
                    uniqueID=f"{integrationUniqueID}",
                    description=description,
                    device_friendly_name=f"Counter {deviceID}",
                    mqtt_root=mqttRoot,
                )
            )

    if devicetype == "bat":
        # Create sensors for battery
        BINARY_SENSORS_PER_BATTERY_CP = copy.deepcopy(BINARY_SENSORS_PER_BATTERY)

        for description in BINARY_SENSORS_PER_BATTERY_CP:
            description.mqttTopicCurrentValue = (
                f"{mqttRoot}/{devicetype}/{deviceID}/get/{description.key}"
            )
            _LOGGER.debug("mqttTopic: %s", description.mqttTopicCurrentValue)

            sensorList.append(
                openwbBinarySensor(
                    uniqueID=f"{integrationUniqueID}",
                    description=description,
                    device_friendly_name=f"Battery {deviceID}",
                    mqtt_root=mqttRoot,
                )
            )

    if devicetype == "pv":
        # Create sensors for pv generators
        BINARY_SENSORS_PER_PVGENERATOR_CP = copy.deepcopy(
            BINARY_SENSORS_PER_PVGENERATOR
        )

        for description in BINARY_SENSORS_PER_PVGENERATOR_CP:
            description.mqttTopicCurrentValue = (
                f"{mqttRoot}/{devicetype}/{deviceID}/get/{description.key}"
            )
            _LOGGER.debug("mqttTopic: %s", description.mqttTopicCurrentValue)

            sensorList.append(
                openwbBinarySensor(
                    uniqueID=f"{integrationUniqueID}",
                    description=description,
                    device_friendly_name=f"PV {deviceID}",
                    mqtt_root=mqttRoot,
                )
            )

    if devicetype == "vehicle":
        # Create sensors for pv vehicles
        BINARY_SENSORS_PER_VEHICLE_CP = copy.deepcopy(BINARY_SENSORS_PER_VEHICLE)

        for description in BINARY_SENSORS_PER_VEHICLE_CP:
            description.mqttTopicCurrentValue = (
                f"{mqttRoot}/{devicetype}/{deviceID}/get/{description.key}"
            )
            _LOGGER.debug("mqttTopic: %s", description.mqttTopicCurrentValue)

            sensorList.append(
                openwbBinarySensor(
                    uniqueID=f"{integrationUniqueID}",
                    description=description,
                    device_friendly_name=f"Vehicle {deviceID}",
                    mqtt_root=mqttRoot,
                )
            )

    async_add_entities(sensorList)


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
