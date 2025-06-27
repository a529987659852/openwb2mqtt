"""The openwbmqtt component for controlling the openWB wallbox via home assistant / MQTT."""

from __future__ import annotations

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

from .common import OpenWBBaseEntity, async_setup_sensors
from .const import (
    DEVICETYPE,
    MANUFACTURER,
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
    device_type = config.data[DEVICETYPE]

    if device_type == "controller":
        # Controller sensors have a different topic pattern
        await async_setup_sensors(
            hass,
            config,
            async_add_entities,
            SENSORS_CONTROLLER,
            "{mqtt_root}/{key}",
            MANUFACTURER,
        )
    elif device_type == "chargepoint":
        await async_setup_sensors(
            hass,
            config,
            async_add_entities,
            SENSORS_PER_CHARGEPOINT,
            "{mqtt_root}/{device_type}/{device_id}/{key}",
            "Chargepoint",
        )
    elif device_type == "counter":
        await async_setup_sensors(
            hass,
            config,
            async_add_entities,
            SENSORS_PER_COUNTER,
            "{mqtt_root}/{device_type}/{device_id}/get/{key}",
            "Counter",
        )
    elif device_type == "bat":
        await async_setup_sensors(
            hass,
            config,
            async_add_entities,
            SENSORS_PER_BATTERY,
            "{mqtt_root}/{device_type}/{device_id}/get/{key}",
            "Battery",
        )
    elif device_type == "pv":
        await async_setup_sensors(
            hass,
            config,
            async_add_entities,
            SENSORS_PER_PVGENERATOR,
            "{mqtt_root}/{device_type}/{device_id}/get/{key}",
            "PV",
        )
    elif device_type == "vehicle":
        # Vehicle sensors need special handling for the 'name' key
        def process_vehicle_topics(description, device_type, device_id, mqtt_root):
            if description.key == "name":
                description.mqttTopicCurrentValue = (
                    f"{mqtt_root}/{device_type}/{device_id}/{description.key}"
                )
            else:
                description.mqttTopicCurrentValue = (
                    f"{mqtt_root}/{device_type}/{device_id}/get/{description.key}"
                )

        await async_setup_sensors(
            hass,
            config,
            async_add_entities,
            SENSORS_PER_VEHICLE,
            "{mqtt_root}/{device_type}/{device_id}/get/{key}",  # This will be overridden for 'name'
            "Vehicle",
            process_vehicle_topics,
        )


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

            # Update device name for vehicle
            if (
                self.entity_description.key == "name"
                and "vehicle" in self.entity_description.mqttTopicCurrentValue
            ):
                device_registry.async_update_device(
                    device.id, name=message.payload.strip('"')
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
