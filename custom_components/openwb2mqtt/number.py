"""OpenWB Number Entity."""

from __future__ import annotations

import asyncio
import json
import logging

from homeassistant.components import mqtt
from homeassistant.components.number import (
    DOMAIN as NUMBER_DOMAIN,
    NumberEntity,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .common import OpenWBBaseEntity, async_setup_numbers
from .const import (
    COMM_METHOD_HTTP,
    COMMUNICATION_METHOD,
    CONF_WALLBOX_POWER,
    DEVICEID,
    DEVICETYPE,
    DOMAIN,
    MANUFACTURER,
    NUMBERS_PER_CHARGEPOINT,
    openwbDynamicNumberEntityDescription,
    openWBNumberEntityDescription,
)
from .coordinator import OpenWB2MqttDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, config: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up number entities for openWB."""
    device_type = config.data[DEVICETYPE]
    entities_to_add = []

    if config.data.get(COMMUNICATION_METHOD) == COMM_METHOD_HTTP:
        coordinator = hass.data[DOMAIN][config.entry_id]
        if device_type == "chargepoint":
            for description in NUMBERS_PER_CHARGEPOINT:
                if description.api_key is None:
                    continue
                entities_to_add.append(
                    OpenWB2MqttApiNumber(coordinator, description, config)
                )
        async_add_entities(entities_to_add)
    else:
        if device_type == "chargepoint":
            regular_numbers = [
                desc
                for desc in NUMBERS_PER_CHARGEPOINT
                if not isinstance(desc, openwbDynamicNumberEntityDescription)
            ]
            dynamic_numbers = [
                desc
                for desc in NUMBERS_PER_CHARGEPOINT
                if isinstance(desc, openwbDynamicNumberEntityDescription)
            ]

            def process_chargepoint_numbers(
                description, device_type, device_id, mqtt_root
            ):
                description.mqttTopicCommand = (
                    f"{mqtt_root}/{description.mqttTopicCommand}"
                )
                description.mqttTopicCurrentValue = f"{mqtt_root}/{device_type}/{device_id}/{description.mqttTopicCurrentValue}"

            await async_setup_numbers(
                hass,
                config,
                async_add_entities,
                regular_numbers,
                "{mqtt_root}/{device_type}/{device_id}/{key}",
                "Chargepoint",
                process_chargepoint_numbers,
            )

            if dynamic_numbers:
                entities = [
                    openwbDynamicNumber(
                        config_entry=config,
                        uniqueID=config.unique_id,
                        description=desc,
                        device_friendly_name=f"Chargepoint {config.data[DEVICEID]}",
                        mqtt_root=config.data["mqttroot"],
                        device_id=config.data[DEVICEID],
                    )
                    for desc in dynamic_numbers
                ]
                async_add_entities(entities)


class OpenWB2MqttApiNumber(CoordinatorEntity, NumberEntity):
    """Entity representing openWB numbers that are updated via API."""

    entity_description: openWBNumberEntityDescription

    def __init__(
        self,
        coordinator: OpenWB2MqttDataUpdateCoordinator,
        description: openWBNumberEntityDescription,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self.config_entry = config_entry
        self._attr_unique_id = slugify(f"{config_entry.title}_{description.name}")
        self.entity_id = (
            f"{NUMBER_DOMAIN}.{slugify(f'{config_entry.title}_{description.name}')}"
        )

    @property
    def native_max_value(self) -> float:
        """Return the maximum value."""
        if self.entity_description.key in {
            "instant_charging_current_control",
            "pv_charging_min_current_control",
        }:
            power = self.config_entry.options.get(
                CONF_WALLBOX_POWER, self.config_entry.data.get(CONF_WALLBOX_POWER)
            )
            if power == "11":
                return 16
            return 32
        return self.entity_description.native_max_value

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None
        if self.entity_description.api_key:
            key = self.entity_description.api_key
        value = self.coordinator.data.get(key)
        if self.entity_description.api_value_fn:
            return self.entity_description.api_value_fn(value)
        return value

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        command_key = self.entity_description.api_key_command
        state_key = self.entity_description.api_key
        chargepoint_nr = self.config_entry.data[DEVICEID]

        if not command_key or not state_key:
            return

        payload = f"{command_key}={value}&chargepoint_nr={chargepoint_nr}"

        response = await self.coordinator.client.async_set_data(payload)
        if (
            response
            and response.get("success")
            and "data" in response
            and command_key in response["data"]
        ):
            new_data = self.coordinator.data.copy()
            if command_key == "instant_charging_amount":
                try:
                    new_data[state_key] = 1000 * float(response["data"][command_key])
                except (ValueError, TypeError):
                    new_data[state_key] = None
            else:
                new_data[state_key] = response["data"][command_key]
            self.coordinator.async_set_updated_data(new_data)
            return

        # Fallback to refresh if optimistic update fails
        await self.coordinator.async_request_refresh()

    @property
    def device_info(self):
        """Return the device info."""
        return {
            "identifiers": {(DOMAIN, self.config_entry.title)},
            "name": self.config_entry.title,
            "manufacturer": MANUFACTURER,
        }


class openWBNumber(OpenWBBaseEntity, NumberEntity):
    """Entity representing openWB numbers."""

    entity_description: openWBNumberEntityDescription

    def __init__(
        self,
        uniqueID: str,
        device_friendly_name: str,
        mqtt_root: str,
        description: openWBNumberEntityDescription,
        deviceID: int | None = None,
        state: float | None = None,
        native_min_value: float | None = None,
        native_max_value: float | None = None,
        native_step: float | None = None,
        mode: NumberMode = NumberMode.AUTO,
    ) -> None:
        """Initialize the sensor and the openWB device."""
        super().__init__(
            device_friendly_name=device_friendly_name,
            mqtt_root=mqtt_root,
        )

        self.entity_description = description
        self._attr_unique_id = slugify(f"{uniqueID}-{description.name}")
        self.entity_id = f"{NUMBER_DOMAIN}.{uniqueID}-{description.name}"
        self._attr_name = description.name

        self._attr_native_value = state
        self._attr_mode = mode

        self.deviceID = deviceID
        self.mqtt_root = mqtt_root

        if native_min_value is not None:
            self._attr_native_min_value = native_min_value
        if native_max_value is not None:
            self._attr_native_max_value = native_max_value
        if native_step is not None:
            self._attr_native_step = native_step

    async def async_added_to_hass(self):
        """Subscribe to MQTT events."""

        @callback
        def message_received(message):
            """Handle new MQTT messages.

            If defined, convert values.
            """
            if self.entity_description.value_fn is not None:
                self._attr_native_value = self.entity_description.value_fn(
                    message.payload
                )
            else:
                self._attr_native_value = message.payload
            self.async_write_ha_state()

        # Subscribe to MQTT topic and connect callack message
        _LOGGER.debug(
            "Subscribed to MQTT topic: %s",
            self.entity_description.mqttTopicCurrentValue,
        )
        await mqtt.async_subscribe(
            self.hass,
            self.entity_description.mqttTopicCurrentValue,
            message_received,
            1,
        )

    async def async_set_native_value(self, value):
        """Update the current value.

        After set_vative_value --> the result is published to MQTT.
        But the HA sensor shall only change when the MQTT message on the /get/ topic is received.
        Only then, openWB has changed the setting as well.
        """
        if slugify("Ladestromvorgabe (PV Laden)") in self.entity_id:
            success = self.publishToMQTT(int(value))
            if success:
                self._attr_native_value = value
                self.async_write_ha_state()
        else:
            success = self.publishToMQTT(value)
        if success:
            return
        _LOGGER.error("Error publishing MQTT message")

    def publishToMQTT(self, valueToPublish: float) -> bool:
        """Publish message to MQTT.

        If necessary, placeholders in MQTT topic are replaced.
        """
        publish_mqtt_message = False
        topic = self.entity_description.mqttTopicCommand

        # For the special SoC topic, we need to replace the _vehicleID_ placeholder
        # with the actual vehicle ID associated with this charge point
        if "_vehicleID_" in topic:
            vehicle_id = self.get_assigned_vehicle(self.hass, DOMAIN)
            if vehicle_id is not None:
                # Replace the placeholder with the actual vehicle ID
                topic = topic.replace("_vehicleID_", vehicle_id)
                publish_mqtt_message = True
        else:
            publish_mqtt_message = True

        _LOGGER.debug("MQTT topic: %s", topic)

        payload = str(valueToPublish)
        _LOGGER.debug("MQTT payload: %s", payload)

        if publish_mqtt_message:
            # Use the modified topic with replaced placeholders
            mqtt.publish(self.hass, topic, payload)

        return publish_mqtt_message

    def get_assigned_vehicle(self, hass: HomeAssistant, domain: str) -> int | None:
        """Get the vehicle that is currently assigned to this charge point."""
        ent_reg = er.async_get(hass)
        unique_id = slugify(f"{self.mqtt_root}_chargepoint_{self.deviceID}_fahrzeug_id")
        vehicle_id_entity = ent_reg.async_get_entity_id(
            Platform.SENSOR,
            domain,
            unique_id,
        )
        if vehicle_id_entity is None:
            return None

        state = hass.states.get(vehicle_id_entity)
        if state is None:
            return None

        return state.state


class openwbDynamicNumber(OpenWBBaseEntity, NumberEntity):
    """Entity representing openWB numbers with dynamic MQTT topic subscription."""

    entity_description: openwbDynamicNumberEntityDescription

    def __init__(
        self,
        config_entry: ConfigEntry,
        uniqueID: str,
        device_friendly_name: str,
        mqtt_root: str,
        description: openwbDynamicNumberEntityDescription,
        device_id: int,
        state: float | None = None,
        mode: NumberMode = NumberMode.AUTO,
    ) -> None:
        """Initialize the number entity and the openWB device."""
        super().__init__(
            device_friendly_name=device_friendly_name,
            mqtt_root=mqtt_root,
        )

        self.config_entry = config_entry
        self.entity_description = description
        self._attr_unique_id = slugify(f"{uniqueID}-{description.name}")
        self.entity_id = f"{NUMBER_DOMAIN}.{uniqueID}-{description.name}"
        self._attr_name = description.name

        self._attr_native_value = state
        self._attr_mode = mode

        self.mqtt_root = mqtt_root
        self.device_id = device_id
        self._charge_template_id = None
        self._unsubscribe_config = None
        self._unsubscribe_template = None

        # Set native min/max/step values from the entity description
        self._attr_native_min_value = description.native_min_value
        self._attr_native_max_value = description.native_max_value
        self._attr_native_step = description.native_step

        if self.entity_description.key in {
            "instant_charging_current_control",
            "pv_charging_min_current_control",
        }:
            power = self.config_entry.options.get(
                CONF_WALLBOX_POWER, self.config_entry.data.get(CONF_WALLBOX_POWER)
            )
            if power == "11":
                self._attr_native_max_value = 16
            else:
                self._attr_native_max_value = 32

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
            chargepoint_id=self.device_id,
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

    async def async_set_native_value(self, value):
        """Update the current value.

        After set_native_value --> the result is published to MQTT.
        But the HA number shall only change when the MQTT message on the template topic is received.
        Only then, openWB has changed the setting as well.
        """
        if self._charge_template_id is None:
            _LOGGER.error("Cannot set value: No charge template ID available")
            return

        # Format the command topic with the charge template ID
        command_topic = self.entity_description.mqttTopicCommandTemplate.format(
            mqtt_root=self.mqtt_root,
            charge_template_id=self._charge_template_id,
            chargepoint_id=self.device_id,
        )

        # Check if this value must be converted before publishing
        if self.entity_description.convert_before_publish_fn is not None:
            value = self.entity_description.convert_before_publish_fn(value)

        # Convert value to integer as required by openWB
        payload = str(int(value))

        _LOGGER.debug("Publishing to MQTT topic %s: %s", command_topic, payload)
        mqtt.publish(self.hass, command_topic, payload)
