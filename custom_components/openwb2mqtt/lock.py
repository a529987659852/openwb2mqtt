"""OpenWB Lock Entity."""

from __future__ import annotations

import logging

from homeassistant.components import mqtt
from homeassistant.components.lock import (
    DOMAIN as LOCK_DOMAIN,
    LockEntity,
    LockEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .common import OpenWBBaseEntity, async_setup_entities
from .const import (
    DEVICETYPE,
    LOCKS_PER_CHARGEPOINT,
    openwbLockEntityDescription,
    MQTT_ROOT_TOPIC,
    DEVICEID, # Hinzugefügt
)
import copy

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, config: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up lock entities for openWB."""
    device_type = config.data[DEVICETYPE]
    mqtt_root = config.data[MQTT_ROOT_TOPIC]
    device_id = config.data[DEVICEID]
    integration_unique_id = config.unique_id
    device_friendly_name = f"Chargepoint {device_id}"
    
    # setup for chargepoint only
    if device_type != "chargepoint":
        return

    entities = []
    
    descriptions_copy = copy.deepcopy(LOCKS_PER_CHARGEPOINT) 

    for description in descriptions_copy:
        # Template for the mqtt topic: {mqtt_root}/chargepoint/{device_id}/set/manual_lock
        full_key = description.key

        base_topic = f"{mqtt_root}/{device_type}/{device_id}"
        
        description.mqttTopicCurrentValue = f"{base_topic}/set/{full_key}"
        description.mqttTopicCommand = f"{base_topic}/set/{full_key}"
        
        _LOGGER.debug(
            "Lock Topic: %s", description.mqttTopicCurrentValue
        )

        entities.append(
            openWBLock(
                uniqueID=integration_unique_id,
                description=description,
                device_friendly_name=device_friendly_name,
                mqtt_root=mqtt_root,
                deviceID=device_id,
            )
        )

    async_add_entities(entities)


class openWBLock(OpenWBBaseEntity, LockEntity):
    """Representation of an openWB Lock."""

    entity_description: openwbLockEntityDescription

    def __init__(
        self,
        uniqueID: str,
        description: openwbLockEntityDescription,
        device_friendly_name: str,
        mqtt_root: str,
        deviceID: int | None = None,
    ) -> None:
        """Initialize the lock entity."""
        super().__init__(device_friendly_name, mqtt_root)
        self.entity_description = description
        self._attr_unique_id = slugify(f"{uniqueID}-{description.name}")
        self.entity_id = f"{LOCK_DOMAIN}.{uniqueID}_{slugify(description.name)}"
        self._attr_name = description.name
        self.deviceID = deviceID
        self._attr_is_locked = None # Anfangszustand

        self._state_topic = self.entity_description.mqttTopicCurrentValue
        self._command_topic = self.entity_description.mqttTopicCommand

    async def async_added_to_hass(self) -> None:
        """Subscribe to MQTT events."""
        
        @callback
        def message_received(message):
            """Handle new MQTT messages (state update)."""
            payload = message.payload.strip().lower()
            _LOGGER.warning("Lock received topic: %s, payload: %s", message.topic, message.payload)
            # Prüfen, ob der Payload den Zustand 'locked' oder 'unlocked' signalisiert
            if payload == self.entity_description.state_locked.lower():
                self._attr_is_locked = True
            elif payload == self.entity_description.state_unlocked.lower():
                self._attr_is_locked = False
            else:
                _LOGGER.warning(
                    "Unerwarteter Payload für Lock State: %s auf Topic %s",
                    payload,
                    self._state_topic,
                )
                self._attr_is_locked = None

            self.async_write_ha_state()

        # Abonnieren des State-Topics
        self._unsubscribe_state = await mqtt.async_subscribe(
            self.hass,
            self._state_topic,
            message_received,
            1, # QoS
        )
        _LOGGER.debug("Subscribed to lock state MQTT topic: %s", self._state_topic)


    async def async_lock(self, **kwargs) -> None:
        """Lock the device and publish 'true' payload."""
        payload = self.entity_description.payload_lock
        mqtt.publish(self.hass, self._command_topic, payload, 0, False)

    async def async_unlock(self, **kwargs) -> None:
        """Unlock the device and publish 'false' payload."""
        payload = self.entity_description.payload_unlock
        mqtt.publish(self.hass, self._command_topic, payload, 0, False)
        
    async def async_will_remove_from_hass(self):
        """Unsubscribe from MQTT when entity is removed."""
        if hasattr(self, '_unsubscribe_state') and self._unsubscribe_state is not None:

            self._unsubscribe_state()

