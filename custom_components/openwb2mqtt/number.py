"""OpenWB Number Entity."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

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
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import slugify

from .common import OpenWBBaseEntity, OpenWBEntity, async_setup_numbers, is_supported
from .const import (
    COMM_METHOD_HTTP,
    COMMUNICATION_METHOD,
    CONF_WALLBOX_POWER,
    DEVICEID,
    DEVICETYPE,
    DOMAIN,
    NUMBERS_BY_DEVICE_TYPE,
    NUMBERS_PER_CHARGEPOINT,
    OpenWBNumberEntityDescription,
    max_current_for_wallbox_power,
    openwbDynamicNumberEntityDescription,
    openWBNumberEntityDescription,
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
    """Set up number entities for openWB."""
    if entry.data.get(COMMUNICATION_METHOD) == COMM_METHOD_HTTP:
        coordinator = entry.runtime_data
        descriptions = NUMBERS_BY_DEVICE_TYPE.get(coordinator.device_type, [])
        async_add_entities(
            OpenWBNumber(coordinator, description, Platform.NUMBER)
            for description in descriptions
            if is_supported(description, coordinator.transport)
        )
        return

    # MQTT setup (legacy entities)
    config = entry
    device_type = config.data[DEVICETYPE]
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


class OpenWBNumber(OpenWBEntity, NumberEntity):
    """Number of a simpleAPI device."""

    entity_description: OpenWBNumberEntityDescription
    # The openWB does not report every set value back (e.g. some limits),
    # so the entity keeps the last sent value as a fallback.
    _last_sent_value: float | None = None

    @property
    def native_max_value(self) -> float:
        """Return the maximum value (depends on the wallbox power for currents)."""
        if self.entity_description.max_from_wallbox_power:
            entry = self.coordinator.config_entry
            power = entry.options.get(
                CONF_WALLBOX_POWER, entry.data.get(CONF_WALLBOX_POWER)
            )
            return max_current_for_wallbox_power(power)
        return super().native_max_value

    @property
    def native_value(self) -> Any:
        """Return the current value."""
        if self.has_value():
            return self.get_value()
        return self._last_sent_value

    async def async_set_native_value(self, value: float) -> None:
        """Send a new value to the openWB."""
        await self.async_send_value(value)
        self._last_sent_value = value
        self.async_write_ha_state()


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
        self.entity_id = f"{NUMBER_DOMAIN}.{slugify(f'{uniqueID}_{description.name}')}"
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
        self.entity_id = f"{NUMBER_DOMAIN}.{slugify(f'{uniqueID}_{description.name}')}"
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
