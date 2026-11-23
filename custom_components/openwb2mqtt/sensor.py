"""The openwbmqtt component for controlling the openWB wallbox via home assistant / MQTT."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from homeassistant.components import mqtt
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import slugify

from .common import OpenWBBaseEntity, OpenWBEntity, is_supported
from .const import (
    SENSORS_BY_DEVICE_TYPE,
    OpenWBSensorEntityDescription,
    openwbDynamicSensorEntityDescription,
    openwbSensorEntityDescription,
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
        self._attr_unique_id = slugify(f"{uniqueID}_{description.name}")
        self.entity_id = f"sensor.{slugify(f'{uniqueID}_{description.name}')}"
        self._attr_name = description.name

    async def async_added_to_hass(self):
        """Subscribe to MQTT events."""

        @callback
        def message_received(message):
            """Handle new MQTT messages."""
            self._attr_native_value = message.payload
            device_registry = dr.async_get(self.hass)
            device = self.device_entry

            if device is None:
                return

            if self.entity_description.value_fn is not None:
                self._attr_native_value = self.entity_description.value_fn(
                    self._attr_native_value
                )
            if self.entity_description.valueMap is not None:
                try:
                    self._attr_native_value = self.entity_description.valueMap.get(
                        int(self._attr_native_value)
                    )
                except (ValueError, TypeError):
                    self._attr_native_value = self.entity_description.valueMap.get(
                        self._attr_native_value, self._attr_native_value
                    )
            if "ip_adress" in self.entity_id:
                device_registry.async_update_device(
                    device.id,
                    configuration_url=f"http://{message.payload.strip('\"')}"
                )
            if "version" in self.entity_id:
                device_registry.async_update_device(
                    device.id, sw_version=message.payload.strip('"')
                )
            if (
                self.entity_description.key == "name"
                and "vehicle" in self.entity_description.mqttTopicCurrentValue
            ):
                device_registry.async_update_device(
                    device.id, name=message.payload.strip('"')
                )
            if "ladepunkt" in self.entity_id:
                try:
                    chargepointInfo = json.loads(message.payload)
                    chargepointName = chargepointInfo.get("name")
                    if chargepointName is not None:
                        device_registry.async_update_device(
                            device.id,
                            name=chargepointName,
                        )
                except json.JSONDecodeError:
                    pass
            if "phases_in_use" in self.entity_description.key:
                try:
                    phases = int(message.payload)
                    if phases == 0:
                        self._attr_icon = "mdi:numeric-0-circle-outline"
                    elif phases == 1:
                        self._attr_icon = "mdi:numeric-1-circle-outline"
                    elif phases == 3:
                        self._attr_icon = "mdi:numeric-3-circle-outline"
                    else:
                        self._attr_icon = "mdi:numeric"
                except (ValueError, TypeError):
                    pass
            self.async_write_ha_state()

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


class openwbDynamicSensor(OpenWBBaseEntity, SensorEntity):
    """Representation of an openWB sensor with dynamic MQTT topic subscription."""

    entity_description: openwbDynamicSensorEntityDescription

    def __init__(
        self,
        uniqueID: str | None,
        device_friendly_name: str,
        mqtt_root: str,
        description: openwbDynamicSensorEntityDescription,
        device_id: int,
    ) -> None:
        """Initialize the sensor and the openWB device."""
        super().__init__(
            device_friendly_name=device_friendly_name,
            mqtt_root=mqtt_root,
        )

        self.entity_description = description
        self._attr_unique_id = slugify(f"{uniqueID}_{description.name}")
        self.entity_id = f"sensor.{slugify(f'{uniqueID}_{description.name}')}"
        self._attr_name = description.name
        self.mqtt_root = mqtt_root
        self.device_id = device_id
        self._charge_template_id = None
        self._unsubscribe_config = None
        self._unsubscribe_template = None

    async def async_added_to_hass(self):
        """Subscribe to MQTT events."""
        # First, subscribe to the connected vehicle config topic to get the charge template ID
        config_topic = f"{self.mqtt_root}/chargepoint/{self.device_id}/get/connected_vehicle/config"

        @callback
        def config_message_received(message):
            """Handle new MQTT messages for the config topic."""
            try:
                payload = json.loads(message.payload)
                new_charge_template_id = payload.get("charge_template")

                if (
                    new_charge_template_id is not None
                    and new_charge_template_id != self._charge_template_id
                ):
                    _LOGGER.debug(
                        "Charge template ID changed from %s to %s",
                        self._charge_template_id,
                        new_charge_template_id,
                    )
                    self._charge_template_id = new_charge_template_id

                    # Update the subscription to the charge template topic
                    asyncio.create_task(self._update_template_subscription())
            except (json.JSONDecodeError, ValueError) as err:
                _LOGGER.error("Error parsing config message: %s", err)

        self._unsubscribe_config = await mqtt.async_subscribe(
            self.hass,
            config_topic,
            config_message_received,
            1,
        )
        _LOGGER.debug("Subscribed to config MQTT topic: %s", config_topic)

    async def _update_template_subscription(self):
        """Update the subscription to the charge template topic."""
        # Unsubscribe from the old topic if it exists
        if self._unsubscribe_template is not None:
            self._unsubscribe_template()
            self._unsubscribe_template = None

        if self._charge_template_id is None:
            _LOGGER.debug(
                "No charge template ID available, not subscribing to template topic"
            )
            return

        # Format the template topic with the charge template ID
        template_topic = self.entity_description.mqttTopicTemplate.format(
            mqtt_root=self.mqtt_root,
            charge_template_id=self._charge_template_id,
        )

        @callback
        def template_message_received(message):
            """Handle new MQTT messages for the template topic."""
            try:
                self._attr_native_value = message.payload

                # Convert data if a conversion function is defined
                if self.entity_description.value_fn is not None:
                    self._attr_native_value = self.entity_description.value_fn(
                        self._attr_native_value
                    )

                # Map values as defined in the value map dict if it exists
                if self.entity_description.valueMap is not None:
                    try:
                        self._attr_native_value = self.entity_description.valueMap.get(
                            int(self._attr_native_value)
                        )
                    except ValueError:
                        self._attr_native_value = self.entity_description.valueMap.get(
                            self._attr_native_value, self._attr_native_value
                        )

                # Update entity state with value published on MQTT
                self.async_write_ha_state()
            except Exception as err:
                _LOGGER.error("Error processing template message: %s", err)

        self._unsubscribe_template = await mqtt.async_subscribe(
            self.hass,
            template_topic,
            template_message_received,
            1,
        )
        _LOGGER.debug("Subscribed to template MQTT topic: %s", template_topic)

    async def async_will_remove_from_hass(self):
        """Unsubscribe from MQTT when entity is removed."""
        if self._unsubscribe_config is not None:
            self._unsubscribe_config()

        if self._unsubscribe_template is not None:
            self._unsubscribe_template()
