"""OpenWB Number Entity."""
from __future__ import annotations

import copy
import logging

from homeassistant.components import mqtt
from homeassistant.components.number import DOMAIN, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .common import OpenWBBaseEntity

# Import global values.
from .const import (
    DEVICEID,
    DEVICETYPE,
    DOMAIN as INTEGRATION_DOMAIN,
    MQTT_ROOT_TOPIC,
    NUMBERS_PER_CHARGEPOINT,
    openWBNumberEntityDescription,
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
    numberList = []

    if devicetype == "chargepoint":
        # Create numbers for chargepoint
        NUMBERS_PER_CHARGEPOINT_CP = copy.deepcopy(NUMBERS_PER_CHARGEPOINT)
        for description in NUMBERS_PER_CHARGEPOINT_CP:
            description.mqttTopicCommand = f"{mqttRoot}/{description.mqttTopicCommand}"
            description.mqttTopicCurrentValue = f"{mqttRoot}/{devicetype}/{deviceID}/{description.mqttTopicCurrentValue}"

            numberList.append(
                openWBNumber(
                    unique_id=f"{integrationUniqueID}",
                    description=description,
                    device_friendly_name=f"Chargepoint {deviceID}",
                    deviceID=deviceID,
                    mqtt_root=mqttRoot,
                )
            )

    async_add_entities(numberList)


class openWBNumber(OpenWBBaseEntity, NumberEntity):
    """Entity representing openWB numbers."""

    entity_description: openWBNumberEntityDescription

    def __init__(
        self,
        unique_id: str,
        device_friendly_name: str,
        mqtt_root: str,
        description: openWBNumberEntityDescription,
        deviceID: int | None = None,
        state: float | None = None,
        # currentChargePoint: int | None = None,
        # nChargePoints: int | None = None,
        native_min_value: float | int | None = None,
        native_max_value: float | int | None = None,
        native_step: float | int | None = None,
        mode: NumberMode = NumberMode.AUTO,
    ) -> None:
        """Initialize the sensor and the openWB device."""
        super().__init__(
            device_friendly_name=device_friendly_name,
            mqtt_root=mqtt_root,
        )

        self.entity_description = description
        self._attr_unique_id = slugify(f"{unique_id}-{description.name}")
        self.entity_id = f"{DOMAIN}.{unique_id}-{description.name}"
        self._attr_name = description.name

        # if state is not None:
        #     self._attr_value = state
        # else:
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

        # Modify topic: Manual SoC
        if slugify("Aktueller SoC (Manuelles SoC Modul)") in self.entity_id:
            vehicle_id = self.get_assigned_vehicle(self.hass, INTEGRATION_DOMAIN)
            if vehicle_id is not None:
                # Replace placeholders
                if "_vehicleID_" in topic:
                    topic = topic.replace("_vehicleID_", vehicle_id)
                    publish_mqtt_message = True
        # # Modify topic: pv_charging_min_current
        # elif slugify("Ladestromvorgabe (PV Laden)") in self.entity_id:
        #     charge_template = self.get_assigned_charge_profile(
        #         self.hass, INTEGRATION_DOMAIN
        #     )
        #     if charge_template is not None:
        #         # Replace placeholders
        #         if "_chargeTemplateID_" in topic:
        #             topic = topic.replace("_chargeTemplateID_", charge_template)
        #             publish_mqtt_message = True

        else:
            publish_mqtt_message = True

        _LOGGER.debug("MQTT topic: %s", topic)

        payload = str(valueToPublish)
        _LOGGER.debug("MQTT payload: %s", payload)

        if publish_mqtt_message:
            self.hass.components.mqtt.publish(self.hass, topic, payload)

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

    # def get_assigned_charge_profile(
    #     self, hass: HomeAssistant, domain: str
    # ) -> int | None:
    #     """Get the charge profile that is currently assigned to the vehicle connected to this charge point."""
    #     ent_reg = er.async_get(hass)
    #     unique_id = slugify(f"{self.mqtt_root}_chargepoint_{self.deviceID}_lade_profil")
    #     charge_profile = ent_reg.async_get_entity_id(
    #         Platform.SENSOR,
    #         domain,
    #         unique_id,
    #     )
    #     if charge_profile is None:
    #         return None

    #     state = hass.states.get(charge_profile)
    #     if state is None:
    #         return None

    #     return state.state
