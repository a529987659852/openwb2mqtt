"""OpenWB Lock Entity."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import mqtt
from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN, LockEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import slugify

from .common import OpenWBBaseEntity, OpenWBEntity, is_supported
from .const import (
    LOCKS_BY_DEVICE_TYPE,
    OpenWBLockEntityDescription,
    _to_bool,
    openwbLockEntityDescription,
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
    """Set up lock entities for openWB."""
    coordinator = entry.runtime_data
    descriptions = LOCKS_BY_DEVICE_TYPE.get(coordinator.device_type, [])
    async_add_entities(
        OpenWBLock(coordinator, description, Platform.LOCK)
        for description in descriptions
        if is_supported(description, coordinator.transport)
    )


class OpenWBLock(OpenWBEntity, LockEntity):
    """Lock of a simpleAPI device."""

    entity_description: OpenWBLockEntityDescription

    @property
    def is_locked(self) -> bool | None:
        """Return True if the lock is locked."""
        return _to_bool(self.get_value())

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the device."""
        await self.async_send_value(True)

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the device."""
        await self.async_send_value(False)


class OpenWbMqttLock(OpenWBBaseEntity, LockEntity):
    """Representation of an openWB Lock via MQTT."""

    entity_description: openwbLockEntityDescription

    def __init__(
        self,
        uniqueID: str,
        description: openwbLockEntityDescription,
        device_friendly_name: str,
        mqtt_root: str,
        state_topic: str | None,
        command_topic: str | None,
        deviceID: int | None = None,
    ) -> None:
        """Initialize the lock entity."""
        super().__init__(device_friendly_name=device_friendly_name, mqtt_root=mqtt_root)

        self.entity_description = description
        self._attr_unique_id = slugify(f"{uniqueID}-{self.entity_description.name}")
        self.entity_id = f"{LOCK_DOMAIN}.{slugify(f'{uniqueID}_{description.name}')}"

        self._attr_is_locked = None
        self._state_topic = state_topic
        self._command_topic = command_topic
        self.deviceID = deviceID

    async def async_added_to_hass(self) -> None:
        """Subscribe to MQTT events."""

        @callback
        def message_received(message):
            """Handle new MQTT messages (state update)."""
            payload = message.payload.strip().lower()
            if payload == self.entity_description.state_locked.lower():
                self._attr_is_locked = True
            elif payload == self.entity_description.state_unlocked.lower():
                self._attr_is_locked = False
            else:
                _LOGGER.warning(
                    "Unexpected Payload for Lock State: %s on Topic %s",
                    payload,
                    self._state_topic,
                )
                self._attr_is_locked = None
            self.async_write_ha_state()

        if self._state_topic:
            await mqtt.async_subscribe(
                self.hass, self._state_topic, message_received, 1
            )
            _LOGGER.debug("Subscribed to lock state MQTT topic: %s", self._state_topic)

    async def async_lock(self, **kwargs) -> None:
        """Lock the device."""
        if self._command_topic:
            payload = self.entity_description.payload_lock
            await mqtt.async_publish(self.hass, self._command_topic, payload, 0, False)

    async def async_unlock(self, **kwargs) -> None:
        """Unlock the device."""
        if self._command_topic:
            payload = self.entity_description.payload_unlock
            await mqtt.async_publish(self.hass, self._command_topic, payload, 0, False)

    async def async_will_remove_from_hass(self):
        """Unsubscribe from MQTT when entity is removed."""
        if hasattr(self, "_unsubscribe_state") and self._unsubscribe_state:
            self._unsubscribe_state()
