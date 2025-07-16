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
from homeassistant.util import slugify

from .common import OpenWBBaseEntity, async_setup_numbers
from .const import (
    DEVICETYPE,
    DOMAIN as INTEGRATION_DOMAIN,
    NUMBERS_PER_CHARGEPOINT,
    openWBNumberEntityDescription,
    openwbDynamicNumberEntityDescription,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, config: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up number entities for openWB."""
    device_type = config.data[DEVICETYPE]

    if device_type == "chargepoint":
        # Process regular numbers and dynamic numbers separately
        regular_numbers = []
        dynamic_numbers = []

        # Split the numbers into regular and dynamic numbers
        for description in NUMBERS_PER_CHARGEPOINT:
            if isinstance(description, openwbDynamicNumberEntityDescription):
                dynamic_numbers.append(description)
            else:
                regular_numbers.append(description)

        # Special processing for regular chargepoint numbers
        def process_chargepoint_numbers(description, device_type, device_id, mqtt_root):
            description.mqttTopicCommand = f"{mqtt_root}/{description.mqttTopicCommand}"
            description.mqttTopicCurrentValue = f"{mqtt_root}/{device_type}/{device_id}/{description.mqttTopicCurrentValue}"

        # Set up regular numbers
        await async_setup_numbers(
            hass,
            config,
            async_add_entities,
            regular_numbers,
            "{mqtt_root}/{device_type}/{device_id}/{key}",  # This is a placeholder, actual topics are set in process_chargepoint_numbers
            "Chargepoint",
            process_chargepoint_numbers,
        )

        # Set up dynamic numbers
        if dynamic_numbers:
            mqtt_root = config.data["mqttroot"]
            device_id = config.data["DEVICEID"]
            device_friendly_name = f"Chargepoint {device_id}"

            # Create dynamic numbers
            entities = []
            for description in dynamic_numbers:
                entities.append(
                    openwbDynamicNumber(
                        uniqueID=config.unique_id,
                        description=description,
                        device_friendly_name=device_friendly_name,
                        mqtt_root=mqtt_root,
                        device_id=device_id,
                    )
                )

            async_add_entities(entities)


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
            vehicle_id = self.get_assigned_vehicle(self.hass, INTEGRATION_DOMAIN)
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
        vehicle_id = ent_reg.async_get_entity_id(
            Platform.SENSOR,
            domain,
            unique_id,
        )
        if vehicle_id is None:
            return None

        state = hass.states.get(vehicle_id)
        if state is None:
            return None

        return state.state


class openwbDynamicNumber(OpenWBBaseEntity, NumberEntity):
    """Entity representing openWB numbers with dynamic MQTT topic subscription."""

    entity_description: openwbDynamicNumberEntityDescription

    def __init__(
        self,
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
        )

        # Check if this value must be converted before publishing
        if self.entity_description.convert_before_publish_fn is not None:
            value = self.entity_description.convert_before_publish_fn(value)

        # Convert value to integer as required by openWB
        payload = str(int(value))

        _LOGGER.debug("Publishing to MQTT topic %s: %s", command_topic, payload)
        mqtt.publish(self.hass, command_topic, payload)
