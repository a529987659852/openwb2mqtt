"""The openwbmqtt component for controlling the openWB wallbox via home assistant / MQTT."""

from __future__ import annotations

import copy
import json
import logging

from homeassistant.components import mqtt
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

# Inside a component
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .common import OpenWBBaseEntity

# Import global values.
from .const import (
    MANUFACTURER,
    MQTT_ROOT_TOPIC,
    SENSORS_CONTROLLER,
    SENSORS_PER_BATTERY,
    SENSORS_PER_CHARGEPOINT,
    SENSORS_PER_COUNTER,
    SENSORS_PER_PVGENERATOR,
    SENSORS_PER_VEHICLE,
    openwbSensorEntityDescription,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, config: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensors for openWB."""

    integrationUniqueID = config.unique_id
    mqttRoot = config.data[MQTT_ROOT_TOPIC]
    devicetype = config.data["DEVICETYPE"]
    deviceID = config.data["DEVICEID"]
    sensorList = []

    if devicetype == "controller":
        SENSORS_CONTROLLER_CP = copy.deepcopy(SENSORS_CONTROLLER)
        for description in SENSORS_CONTROLLER_CP:
            description.mqttTopicCurrentValue = f"{mqttRoot}/{description.key}"
            sensorList.append(
                openwbSensor(
                    uniqueID=f"{integrationUniqueID}",
                    description=description,
                    device_friendly_name=MANUFACTURER,
                    mqtt_root=mqttRoot,
                )
            )

    if devicetype == "chargepoint":
        # Create sensors for chargepoint
        SENSORS_PER_CHARGEPOINT_CP = copy.deepcopy(SENSORS_PER_CHARGEPOINT)
        for description in SENSORS_PER_CHARGEPOINT_CP:
            description.mqttTopicCurrentValue = (
                f"{mqttRoot}/{devicetype}/{deviceID}/{description.key}"
            )
            sensorList.append(
                openwbSensor(
                    uniqueID=f"{integrationUniqueID}",
                    description=description,
                    device_friendly_name=f"Chargepoint {deviceID}",
                    mqtt_root=mqttRoot,
                )
            )
    if devicetype == "counter":
        # Create sensors for counters, for example EVU
        SENSORS_PER_COUNTER_CP = copy.deepcopy(SENSORS_PER_COUNTER)
        for description in SENSORS_PER_COUNTER_CP:
            description.mqttTopicCurrentValue = (
                f"{mqttRoot}/{devicetype}/{deviceID}/get/{description.key}"
            )
            sensorList.append(
                openwbSensor(
                    uniqueID=f"{integrationUniqueID}",
                    description=description,
                    device_friendly_name=f"Counter {deviceID}",
                    mqtt_root=mqttRoot,
                )
            )

    if devicetype == "bat":
        # Create sensors for batteries
        SENSORS_PER_BATTERY_CP = copy.deepcopy(SENSORS_PER_BATTERY)
        for description in SENSORS_PER_BATTERY_CP:
            description.mqttTopicCurrentValue = (
                f"{mqttRoot}/{devicetype}/{deviceID}/get/{description.key}"
            )
            sensorList.append(
                openwbSensor(
                    uniqueID=f"{integrationUniqueID}",
                    description=description,
                    device_friendly_name=f"Battery {deviceID}",
                    mqtt_root=mqttRoot,
                )
            )

    if devicetype == "pv":
        # Create sensors for pv generator
        SENSORS_PER_PVGENERATOR_CP = copy.deepcopy(SENSORS_PER_PVGENERATOR)
        for description in SENSORS_PER_PVGENERATOR_CP:
            description.mqttTopicCurrentValue = (
                f"{mqttRoot}/{devicetype}/{deviceID}/get/{description.key}"
            )
            sensorList.append(
                openwbSensor(
                    uniqueID=f"{integrationUniqueID}",
                    description=description,
                    device_friendly_name=f"PV {deviceID}",
                    mqtt_root=mqttRoot,
                )
            )

    if devicetype == "vehicle":
        # Create sensors for vehicle
        SENSORS_PER_VEHICLE_CP = copy.deepcopy(SENSORS_PER_VEHICLE)
        for description in SENSORS_PER_VEHICLE_CP:
            description.mqttTopicCurrentValue = (
                f"{mqttRoot}/{devicetype}/{deviceID}/get/{description.key}"
            )
            sensorList.append(
                openwbSensor(
                    uniqueID=f"{integrationUniqueID}",
                    description=description,
                    device_friendly_name=f"Vehicle {deviceID}",
                    mqtt_root=mqttRoot,
                )
            )

    async_add_entities(sensorList)


class openwbSensor(OpenWBBaseEntity, SensorEntity):
    """Representation of an openWB sensor that is updated via MQTT."""

    entity_description: openwbSensorEntityDescription

    def __init__(
        self,
        uniqueID: str | None,
        device_friendly_name: str,
        mqtt_root: str,
        description: openwbSensorEntityDescription,
    ) -> None:
        """Initialize the sensor and the openWB device."""
        super().__init__(
            device_friendly_name=device_friendly_name,
            mqtt_root=mqtt_root,
        )

        self.entity_description = description
        self._attr_unique_id = slugify(f"{uniqueID}-{description.name}")
        self.entity_id = f"sensor.{uniqueID}-{description.name}"
        self._attr_name = description.name

    async def async_added_to_hass(self):
        """Subscribe to MQTT events."""

        @callback
        def message_received(message):
            """Handle new MQTT messages."""
            self._attr_native_value = message.payload

            # Get device --> update from MMQT values below (e.g. IP, software version, etc.)
            device_registry = dr.async_get(self.hass)
            device = device_registry.async_get_device(
                self.device_info.get("identifiers")
            )

            # Convert data if a conversion function is defined
            if self.entity_description.value_fn is not None:
                self._attr_native_value = self.entity_description.value_fn(
                    self._attr_native_value
                )

            # Map values as defined in the value map dict.
            # First try to map integer values, then string values.
            # If no value can be mapped, use original value without conversion.
            if self.entity_description.valueMap is not None:
                try:
                    self._attr_native_value = self.entity_description.valueMap.get(
                        int(self._attr_native_value)
                    )
                except ValueError:
                    self._attr_native_value = self.entity_description.valueMap.get(
                        self._attr_native_value, self._attr_native_value
                    )

            # If MQTT message contains IP --> set up configuration_url to visit the device
            if "ip_adress" in self.entity_id:
                device_registry.async_update_device(
                    device.id,
                    configuration_url=f"http://{message.payload.strip('"')}",
                )
            # If MQTT message contains version --> set sw_version of the device
            if "version" in self.entity_id:
                device_registry.async_update_device(
                    device.id, sw_version=message.payload.strip('"')
                )

            if "ladepunkt" in self.entity_id:
                chargepointInfo = json.loads(message.payload)
                chargepointName = chargepointInfo.get("name")
                if chargepointName is not None:
                    device_registry.async_update_device(
                        device.id,
                        name=chargepointName,
                    )

            # Update icon of countPhasesInUse
            if "phases_in_use" in self.entity_description.key:
                if int(message.payload) == 0:
                    self._attr_icon = "mdi:numeric-0-circle-outline"
                elif int(message.payload) == 1:
                    self._attr_icon = "mdi:numeric-1-circle-outline"
                elif int(message.payload) == 3:
                    self._attr_icon = "mdi:numeric-3-circle-outline"
                else:
                    self._attr_icon = "mdi:numeric"

            # Update entity state with value published on MQTT.
            self.async_write_ha_state()

        # Subscribe to MQTT topic and connect callack message
        await mqtt.async_subscribe(
            self.hass,
            self.entity_description.mqttTopicCurrentValue,
            message_received,
            1,
        )
        _LOGGER.debug(
            "Subscribed to MQTT topic: %s",
            self.entity_description.mqttTopicCurrentValue,
        )
