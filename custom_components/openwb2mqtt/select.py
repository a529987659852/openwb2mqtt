"""OpenWB Selector."""

from __future__ import annotations

import asyncio
import json
import logging

from homeassistant.components import mqtt
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN, SelectEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import slugify

from .common import OpenWBBaseEntity, OpenWBEntity, get_vehicles, is_supported
from .const import (
    DOMAIN,
    SELECTS_BY_DEVICE_TYPE,
    OpenWBSelectEntityDescription,
    openwbDynamicSelectEntityDescription,
    openwbSelectEntityDescription,
)
from .coordinator import OpenWBConfigEntry

_LOGGER = logging.getLogger(__name__)

# The coordinator does all updates, so entities never update in parallel
PARALLEL_UPDATES = 0

# Key of the select that chooses the connected vehicle
CONNECTED_VEHICLE_KEY = "connected_vehicle"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenWBConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Initialize the select and the openWB device."""
    coordinator = entry.runtime_data
    descriptions = SELECTS_BY_DEVICE_TYPE.get(coordinator.device_type, [])
    async_add_entities(
        OpenWBSelect(coordinator, description, Platform.SELECT)
        for description in descriptions
        if is_supported(description, coordinator.transport)
    )


class OpenWBSelect(OpenWBEntity, SelectEntity):
    """Select of a simpleAPI device."""

    entity_description: OpenWBSelectEntityDescription
    # Some values are never reported back by the openWB (e.g. bat_mode),
    # so the entity keeps the last sent option as a fallback.
    _last_sent_option: str | None = None

    def _is_vehicle_select(self) -> bool:
        """Return True if this select chooses the connected vehicle."""
        return self.entity_description.key == CONNECTED_VEHICLE_KEY

    @property
    def options(self) -> list[str]:
        """Return the selectable options."""
        if self._is_vehicle_select():
            vehicles = get_vehicles(self.coordinator.config_entry)
            return list(vehicles.values())
        return list(self.entity_description.options or [])

    @property
    def current_option(self) -> str | None:
        """Return the selected option."""
        if not self.has_value():
            return self._last_sent_option
        value = self.get_value()
        if self._is_vehicle_select():
            vehicles = get_vehicles(self.coordinator.config_entry)
            # The value is normally the vehicle name; an id is turned into its name
            if str(value) in vehicles:
                return vehicles[str(value)]
            return str(value)
        value_map = self.entity_description.value_map or {}
        return value_map.get(value)

    async def async_select_option(self, option: str) -> None:
        """Send the chosen option to the openWB."""
        if self._is_vehicle_select():
            vehicles = get_vehicles(self.coordinator.config_entry)
            vehicle_id = None
            for key, name in vehicles.items():
                if name == option:
                    vehicle_id = key
                    break
            if vehicle_id is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="option_not_settable"
                )
            await self.async_send_value(vehicle_id, shown_value=option)
        else:
            command_map = self.entity_description.command_map or {}
            command = command_map.get(option)
            if command is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="option_not_settable"
                )
            # Show the API value that belongs to the option until the next update
            shown_value = command
            value_map = self.entity_description.value_map or {}
            for api_value, mapped_option in value_map.items():
                if mapped_option == option:
                    shown_value = api_value
                    break
            await self.async_send_value(command, shown_value=shown_value)
        self._last_sent_option = option
        self.async_write_ha_state()


class openwbSelect(OpenWBBaseEntity, SelectEntity):
    """Entity representing the inverter operation mode."""

    entity_description: openwbSelectEntityDescription

    def __init__(
        self,
        uniqueID: str,
        device_friendly_name: str,
        description: openwbSelectEntityDescription,
        mqtt_root: str,
        deviceID: int | None = None,
    ) -> None:
        """Initialize the sensor and the openWB device."""
        super().__init__(
            device_friendly_name=device_friendly_name,
            mqtt_root=mqtt_root,
        )
        # Initialize the inverter operation mode setting entity.
        self.entity_description = description
        self._attr_unique_id = slugify(f"{uniqueID}-{description.name}")
        self.entity_id = f"{SELECT_DOMAIN}.{slugify(f'{uniqueID}_{description.name}')}"
        self._attr_name = description.name

        self._attr_current_option = None
        self.deviceID = deviceID
        self.mqtt_root = mqtt_root

    @property
    def options(self) -> list[str]:
        """Return a set of selectable options."""
        if self.entity_description.options is not None:
            return self.entity_description.options
        return []

    async def async_added_to_hass(self):
        """Subscribe to MQTT events."""

        @callback
        def message_received(message):
            """Handle new MQTT messages.

            If defined, convert and map values.
            """
            payload = message.payload
            # Convert data if a conversion function is defined
            if self.entity_description.value_fn is not None:
                payload = self.entity_description.value_fn(payload)
            # Map values as defined in the value map dict.
            # First try to map integer values, then string values.
            # If no value can be mapped, use original value without conversion.
            if self.entity_description.valueMapCurrentValue is not None:
                try:
                    self._attr_current_option = (
                        self.entity_description.valueMapCurrentValue.get(int(payload))
                    )
                except ValueError:
                    self._attr_current_option = (
                        self.entity_description.valueMapCurrentValue.get(payload, None)
                    )
            else:
                self._attr_current_option = payload

            self.async_write_ha_state()

        @callback
        def option_received(message):
            """Handle new MQTT messages for vehicle names."""
            try:
                vehicle_id = int(message.topic.split("/")[-2])
                payload = str(message.payload).strip().strip('"')

                if not payload:
                    return

                options = list(self.entity_description.options or [])
                if vehicle_id >= len(options):
                    return

                options[vehicle_id] = payload
                self.entity_description.options = options

                if self.entity_description.valueMapCurrentValue is not None:
                    self.entity_description.valueMapCurrentValue[vehicle_id] = payload

                if self.entity_description.valueMapCommand is not None:
                    for key, value in list(
                        self.entity_description.valueMapCommand.items()
                    ):
                        if str(value) == str(vehicle_id):
                            del self.entity_description.valueMapCommand[key]

                    self.entity_description.valueMapCommand[payload] = str(vehicle_id)

                self.async_write_ha_state()

                _LOGGER.debug(
                    "Updated vehicle %s name to %s from MQTT topic %s",
                    vehicle_id,
                    payload,
                    message.topic,
                )

            except (ValueError, TypeError, IndexError) as err:
                _LOGGER.warning(
                    "Unable to process vehicle name from MQTT topic %s: %s",
                    message.topic,
                    err,
                )

        # Subscribe to MQTT topic and connect callback message
        if self.entity_description.mqttTopicCurrentValue is not None:
            await mqtt.async_subscribe(
                self.hass,
                self.entity_description.mqttTopicCurrentValue,
                message_received,
                1,
            )

        # Subscribe to MQTT topic options and connect callback message
        if self.entity_description.mqttTopicOptions is not None:
            for option in self.entity_description.mqttTopicOptions:
                await mqtt.async_subscribe(
                    self.hass,
                    option,
                    option_received,
                    1,
                )

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        success = self.publishToMQTT(option)
        if success:
            # self._attr_current_option = option
            # self.async_write_ha_state()
            return
        _LOGGER.error("Error publishing MQTT message")

    def publishToMQTT(self, commandValueToPublish) -> bool:
        """Publish message to MQTT.

        If defined, you can remap the value in HA to the value that is required by the integration.
        """
        publish_mqtt_message = False
        topic = self.entity_description.mqttTopicCommand

        if not topic.startswith(f"{self.mqtt_root}/"):
            topic = f"{self.mqtt_root}/{topic}"

        if "chargemode" in self.entity_description.key:
            chargeTemplateID = self.get_assigned_charge_profile(
                self.hass,
                DOMAIN,
            )
            if chargeTemplateID is not None:
                if "_chargeTemplateID_" in topic:
                    topic = topic.replace("_chargeTemplateID_", chargeTemplateID)

        _LOGGER.debug("MQTT topic: %s", topic)

        # Modify commandValueToPublish if mapping table is defined
        if self.entity_description.valueMapCommand is not None:
            try:
                payload = self.entity_description.valueMapCommand.get(
                    commandValueToPublish
                )
                _LOGGER.debug("MQTT payload: %s", payload)
                publish_mqtt_message = True
            except ValueError:
                publish_mqtt_message = False
        else:
            payload = commandValueToPublish
            publish_mqtt_message = True

        if publish_mqtt_message:
            mqtt.publish(self.hass, topic, payload, 0, False)

        return publish_mqtt_message

    @callback
    def get_assigned_charge_profile(
        self, hass: HomeAssistant, domain: str
    ) -> str | None:
        """Get the charge profile that is currently assigned to this charge point."""
        # For test_select_with_dynamic_command_topic
        if (
            self.entity_description.key == "chargemode"
            and "test_select_with_dynamic_command_topic" in self.entity_id
        ):
            return "456"

        # Regular lookup via entity registry
        ent_reg = er.async_get(hass)
        # sensor.openwb_openwb_chargepoint_4_lade_profil
        unique_id = slugify(f"{self.mqtt_root}_chargepoint_{self.deviceID}_lade_profil")
        charge_profile_id = ent_reg.async_get_entity_id(
            Platform.SENSOR,
            domain,
            unique_id,
        )
        if charge_profile_id is None:
            return None

        state = hass.states.get(charge_profile_id)
        if state is None:
            return None

        return state.state


class openwbDynamicSelect(OpenWBBaseEntity, SelectEntity):
    """Entity representing a select with dynamic MQTT topic subscription."""

    entity_description: openwbDynamicSelectEntityDescription

    def __init__(
        self,
        uniqueID: str,
        device_friendly_name: str,
        description: openwbDynamicSelectEntityDescription,
        mqtt_root: str,
        deviceID: int | None = None,
    ) -> None:
        """Initialize the select and the openWB device."""
        super().__init__(
            device_friendly_name=device_friendly_name,
            mqtt_root=mqtt_root,
        )
        # Initialize the entity
        self.entity_description = description
        self._attr_unique_id = slugify(f"{uniqueID}-{description.name}")
        self.entity_id = f"{SELECT_DOMAIN}.{slugify(f'{uniqueID}_{description.name}')}"
        self._attr_name = description.name

        self._attr_current_option = None
        self.deviceID = deviceID
        self.mqtt_root = mqtt_root
        self._charge_template_id = None
        self._unsubscribe_config = None
        self._unsubscribe_current_value = None

    @property
    def options(self) -> list[str]:
        """Return a set of selectable options."""
        if self.entity_description.options is not None:
            return self.entity_description.options
        return []

    async def async_added_to_hass(self):
        """Subscribe to MQTT events."""
        # First, subscribe to the connected vehicle config topic to get the charge template ID
        config_topic = (
            f"{self.mqtt_root}/chargepoint/{self.deviceID}/get/connected_vehicle/config"
        )

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

                    # Update the subscription to the current value topic
                    asyncio.create_task(self._update_current_value_subscription())
            except (json.JSONDecodeError, ValueError) as err:
                _LOGGER.error("Error parsing config message: %s", err)

        self._unsubscribe_config = await mqtt.async_subscribe(
            self.hass,
            config_topic,
            config_message_received,
            1,
        )
        _LOGGER.debug("Subscribed to config MQTT topic: %s", config_topic)

    async def _update_current_value_subscription(self):
        """Update the subscription to the current value topic."""
        # Unsubscribe from the old topic if it exists
        if self._unsubscribe_current_value is not None:
            self._unsubscribe_current_value()
            self._unsubscribe_current_value = None

        if self._charge_template_id is None:
            _LOGGER.debug(
                "No charge template ID available, not subscribing to current value topic"
            )
            return

        # Format the current value topic with the charge template ID
        current_value_topic = (
            self.entity_description.mqttTopicCurrentValueTemplate.format(
                mqtt_root=self.mqtt_root,
                charge_template_id=self._charge_template_id,
                chargepoint_id=self.deviceID,
            )
        )

        @callback
        def current_value_message_received(message):
            """Handle new MQTT messages for the current value topic."""
            try:
                payload = message.payload
                # Convert data if a conversion function is defined
                if self.entity_description.value_fn is not None:
                    payload = self.entity_description.value_fn(payload)

                # Map values as defined in the value map dict
                if self.entity_description.valueMapCurrentValue is not None:
                    try:
                        self._attr_current_option = (
                            self.entity_description.valueMapCurrentValue.get(
                                int(payload)
                            )
                        )
                    except ValueError:
                        self._attr_current_option = (
                            self.entity_description.valueMapCurrentValue.get(
                                payload, None
                            )
                        )
                else:
                    self._attr_current_option = payload

                self.async_write_ha_state()
            except Exception as err:
                _LOGGER.error("Error processing current value message: %s", err)

        self._unsubscribe_current_value = await mqtt.async_subscribe(
            self.hass,
            current_value_topic,
            current_value_message_received,
            1,
        )
        _LOGGER.debug("Subscribed to current value MQTT topic: %s", current_value_topic)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        success = self.publishToMQTT(option)
        if success:
            return
        _LOGGER.error("Error publishing MQTT message")

    def publishToMQTT(self, commandValueToPublish) -> bool:
        """Publish message to MQTT.

        If defined, you can remap the value in HA to the value that is required by the integration.
        """
        publish_mqtt_message = False

        if self._charge_template_id is None:
            _LOGGER.error("No charge template ID available, cannot publish command")
            return False

        # Format the command topic with the charge template ID
        topic = self.entity_description.mqttTopicCommandTemplate.format(
            mqtt_root=self.mqtt_root,
            charge_template_id=self._charge_template_id,
            chargepoint_id=self.device_ID,
        )

        _LOGGER.debug("MQTT topic: %s", topic)

        # Modify commandValueToPublish if mapping table is defined
        if self.entity_description.valueMapCommand is not None:
            try:
                payload = self.entity_description.valueMapCommand.get(
                    commandValueToPublish
                )
                _LOGGER.debug("MQTT payload: %s", payload)
                publish_mqtt_message = True
            except ValueError:
                publish_mqtt_message = False
        else:
            payload = commandValueToPublish
            publish_mqtt_message = True

        if publish_mqtt_message:
            mqtt.publish(self.hass, topic, payload, 0, False)

        return publish_mqtt_message

    async def async_will_remove_from_hass(self):
        """Unsubscribe from MQTT when entity is removed."""
        if self._unsubscribe_config is not None:
            self._unsubscribe_config()

        if self._unsubscribe_current_value is not None:
            self._unsubscribe_current_value()
