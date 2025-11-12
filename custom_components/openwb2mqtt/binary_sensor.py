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
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .common import OpenWBBaseEntity, async_setup_binary_sensors
from .const import (
    BINARY_SENSORS_PER_BATTERY,
    BINARY_SENSORS_PER_CHARGEPOINT,
    BINARY_SENSORS_PER_COUNTER,
    BINARY_SENSORS_PER_PVGENERATOR,
    BINARY_SENSORS_PER_VEHICLE,
    COMM_METHOD_HTTP,
    COMMUNICATION_METHOD,
    DEVICETYPE,
    DOMAIN,
    MANUFACTURER,
    openwbBinarySensorEntityDescription,
)
from .coordinator import OpenWB2MqttDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, config: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up binary sensors for openWB."""
    device_type = config.data[DEVICETYPE]
    sensors_to_add = []

    if config.data.get(COMMUNICATION_METHOD) == COMM_METHOD_HTTP:
        coordinator = hass.data[DOMAIN][config.entry_id]
        if device_type == "chargepoint":
            for description in BINARY_SENSORS_PER_CHARGEPOINT:
                if description.api_key is None:
                    continue
                sensors_to_add.append(
                    OpenWB2MqttApiBinarySensor(coordinator, description, config)
                )
        elif device_type == "counter":
            for description in BINARY_SENSORS_PER_COUNTER:
                if description.api_key is None:
                    continue
                sensors_to_add.append(
                    OpenWB2MqttApiBinarySensor(coordinator, description, config)
                )
        elif device_type == "bat":
            for description in BINARY_SENSORS_PER_BATTERY:
                if description.api_key is None:
                    continue
                sensors_to_add.append(
                    OpenWB2MqttApiBinarySensor(coordinator, description, config)
                )
        elif device_type == "pv":
            for description in BINARY_SENSORS_PER_PVGENERATOR:
                if description.api_key is None:
                    continue
                sensors_to_add.append(
                    OpenWB2MqttApiBinarySensor(coordinator, description, config)
                )
        # Device type vehicle not yet implemented in API
        # elif device_type == "vehicle":
        #     for description in BINARY_SENSORS_PER_VEHICLE:
        #         if description.api_key is None:
        #             continue
        #         sensors_to_add.append(
        #             OpenWB2MqttApiBinarySensor(coordinator, description, config)
        #         )
        async_add_entities(sensors_to_add)
    else:
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


class OpenWB2MqttApiBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of an openWB binary sensor that is updated via API."""

    entity_description: openwbBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: OpenWB2MqttDataUpdateCoordinator,
        description: openwbBinarySensorEntityDescription,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self.config_entry = config_entry
        self._attr_unique_id = slugify(f"{config_entry.title}_{description.name}")
        self.entity_id = f"{BINARY_SENSOR_DOMAIN}.{slugify(f'{config_entry.title}_{description.name}')}"

    @property
    def is_on(self):
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None
        key = self.entity_description.api_key or self.entity_description.key
        value = self.coordinator.data.get(key)

        if self.entity_description.state:
            return self.entity_description.state(value)

        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            value = value.strip().lower()
            if value in {"true", "on"}:
                return True
            if value in {"false", "off"}:
                return False

        try:
            return bool(int(value))
        except (ValueError, TypeError):
            return None

    @property
    def device_info(self):
        """Return the device info."""
        return {
            "identifiers": {(DOMAIN, self.config_entry.title)},
            "name": self.config_entry.title,
            "manufacturer": MANUFACTURER,
        }


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
