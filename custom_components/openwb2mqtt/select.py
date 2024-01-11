"""OpenWB Selector."""
from __future__ import annotations

import copy
import logging

from homeassistant.components import mqtt
from homeassistant.components.select import DOMAIN, SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .common import OpenWBBaseEntity
from .const import (
    DEVICEID,
    DEVICETYPE,
    DOMAIN as INTEGRATION_DOMAIN,
    MQTT_ROOT_TOPIC,
    SELECTS_PER_CHARGEPOINT,
    openwbSelectEntityDescription,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize the select and the openWB device."""
    integrationUniqueID = config_entry.unique_id
    mqttRoot = config_entry.data[MQTT_ROOT_TOPIC]
    devicetype = config_entry.data[DEVICETYPE]
    deviceID = config_entry.data[DEVICEID]

    selectList = []

    if devicetype == "chargepoint":
        SELECTS_PER_CHARGEPOINT_CP = copy.deepcopy(SELECTS_PER_CHARGEPOINT)
        for description in SELECTS_PER_CHARGEPOINT_CP:
            if "_chargePointID_" in description.mqttTopicCommand:
                description.mqttTopicCommand = description.mqttTopicCommand.replace(
                    "_chargePointID_", str(deviceID)
                )
            description.mqttTopicCommand = f"{mqttRoot}/{description.mqttTopicCommand}"
            description.mqttTopicCurrentValue = f"{mqttRoot}/{devicetype}/{deviceID}/{description.mqttTopicCurrentValue}"
            selectList.append(
                openwbSelect(
                    unique_id=f"{integrationUniqueID}",
                    description=description,
                    device_friendly_name=f"Chargepoint {deviceID}",
                    deviceID=deviceID,
                    mqtt_root=mqttRoot,
                )
            )
    async_add_entities(selectList)


class openwbSelect(OpenWBBaseEntity, SelectEntity):
    """Entity representing the inverter operation mode."""

    entity_description: openwbSelectEntityDescription

    def __init__(
        self,
        unique_id: str,
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
        self._attr_unique_id = slugify(f"{unique_id}-{description.name}")
        self.entity_id = f"{DOMAIN}.{unique_id}-{description.name}"
        self._attr_name = description.name

        self._attr_current_option = None
        self.deviceID = deviceID
        self.mqtt_root = mqtt_root

    async def async_added_to_hass(self):
        """Subscribe to MQTT events."""

        @callback
        def message_received(message):
            """Handle new MQTT messages.

            If defined, convert and map values.
            """
            # Convert data if a conversion function is defined
            if self.entity_description.value_fn is not None:
                message.payload = self.entity_description.value_fn(message.payload)
            # Map values as defined in the value map dict.
            # First try to map integer values, then string values.
            # If no value can be mapped, use original value without conversion.
            if self.entity_description.valueMapCurrentValue is not None:
                try:
                    self._attr_current_option = (
                        self.entity_description.valueMapCurrentValue.get(
                            int(message.payload)
                        )
                    )
                except ValueError:
                    self._attr_current_option = (
                        self.entity_description.valueMapCurrentValue.get(
                            message.payload, None
                        )
                    )
            else:
                self._attr_current_option = message.payload

            self.async_write_ha_state()

        # Subscribe to MQTT topic and connect callack message
        if self.entity_description.mqttTopicCurrentValue is not None:
            await mqtt.async_subscribe(
                self.hass,
                self.entity_description.mqttTopicCurrentValue,
                message_received,
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

        # Modify topic: Chargemode
        if "lademodus" in self.entity_id:
            chargeTemplateID = self.get_assigned_charge_profile(
                self.hass,
                INTEGRATION_DOMAIN,
            )
            if chargeTemplateID is not None:
                # Replace placeholders
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
            self.hass.components.mqtt.publish(self.hass, topic, payload)

        return publish_mqtt_message

    @callback
    def get_assigned_charge_profile(
        self, hass: HomeAssistant, domain: str
    ) -> str | None:
        """Get the charge profile that is currently assigned to this charge point."""
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
