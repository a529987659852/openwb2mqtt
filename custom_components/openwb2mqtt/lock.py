"""OpenWB Lock Entity."""

from __future__ import annotations

import copy
import logging

from homeassistant.components import mqtt
from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN, LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .common import OpenWBBaseEntity, async_setup_locks
from .const import (
    COMM_METHOD_HTTP,
    COMMUNICATION_METHOD,
    DEVICEID,
    DEVICETYPE,
    DOMAIN,
    LOCKS_PER_CHARGEPOINT,
    MANUFACTURER,
    MQTT_ROOT_TOPIC,
    openwbLockEntityDescription,
)
from .coordinator import OpenWB2MqttDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, config: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up lock entities for openWB."""
    communication_method = config.data.get(COMMUNICATION_METHOD)
    device_type = config.data[DEVICETYPE]

    entities = []
    descriptions_copy = copy.deepcopy(LOCKS_PER_CHARGEPOINT)

    if communication_method == COMM_METHOD_HTTP:
        coordinator = hass.data[DOMAIN][config.entry_id]
        if device_type == "chargepoint":
            for description in descriptions_copy:
                if description.api_key is None:
                    continue
                entities.append(
                    OpenWbApiLock(
                        coordinator=coordinator,
                        description=description,
                        config_entry=config,
                    )
                )
        async_add_entities(entities)
    else:  # MQTT
        if device_type == "chargepoint":

            def process_chargepoint_locks(
                description, device_type, device_id, mqtt_root
            ):
                """Process chargepoint-specific lock setup."""
                if "_chargePointID_" in description.mqttTopicCommand:
                    description.mqttTopicCommand = description.mqttTopicCommand.replace(
                        "_chargePointID_", str(device_id)
                    )
                if "_chargePointID_" in description.mqttTopicCurrentValue:
                    description.mqttTopicCurrentValue = (
                        description.mqttTopicCurrentValue.replace(
                            "_chargePointID_", str(device_id)
                        )
                    )

                description.mqttTopicCommand = (
                    f"{mqtt_root}/{description.mqttTopicCommand}"
                )
                description.mqttTopicCurrentValue = (
                    f"{mqtt_root}/chargepoint/{description.mqttTopicCurrentValue}"
                )

                _LOGGER.debug("Lock Topic: %s", description.mqttTopicCurrentValue)

            await async_setup_locks(
                hass,
                config,
                async_add_entities,
                descriptions_copy,
                "{mqtt_root}/{device_type}/{device_id}/{key}",
                "Chargepoint",
                process_chargepoint_locks,
            )


class OpenWbMqttLock(OpenWBBaseEntity, LockEntity):
    """Representation of an openWB Lock via MQTT."""

    entity_description: openwbLockEntityDescription

    def __init__(
        self,
        uniqueID: str,
        description: openwbLockEntityDescription,
        device_friendly_name: str,
        mqtt_root: str,
        state_topic: str,
        command_topic: str,
        deviceID: int | None = None,
    ) -> None:
        """Initialize the lock entity."""
        super().__init__(device_friendly_name=device_friendly_name, mqtt_root=mqtt_root)

        self.entity_description = description
        self._attr_unique_id = slugify(f"{uniqueID}-{self.description.name}")
        self.entity_id = f"{LOCK_DOMAIN}.{uniqueID}-{self.description.name}"

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
            self._unsubscribe_state = await mqtt.async_subscribe(
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


class OpenWbApiLock(CoordinatorEntity[OpenWB2MqttDataUpdateCoordinator], LockEntity):
    """Representation of an openWB Lock via API."""

    entity_description: openwbLockEntityDescription

    def __init__(
        self,
        coordinator: OpenWB2MqttDataUpdateCoordinator,
        description: openwbLockEntityDescription,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the lock entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self.config_entry = config_entry
        if self.entity_description.name:
            self._attr_unique_id = slugify(
                f"{config_entry.title}-{self.entity_description.name}"
            )
            self.entity_id = f"{LOCK_DOMAIN}.{slugify(f'{config_entry.title}-{self.entity_description.name}')}"

    @property
    def is_locked(self) -> bool | None:
        """Return true if the lock is locked."""
        if self.entity_description.api_key and self.coordinator.data:
            return self.coordinator.data.get(self.entity_description.api_key)
        return None

    @property
    def device_info(self):
        """Return the device info."""
        return {
            "identifiers": {(DOMAIN, self.config_entry.title)},
            "name": self.config_entry.title,
            "manufacturer": MANUFACTURER,
        }

    async def async_lock(self, **kwargs) -> None:
        """Lock the device via API."""
        if (
            self.entity_description.api_key_command
            and self.entity_description.api_value_map_command
        ):
            value = self.entity_description.api_value_map_command["lock"]
            await self.coordinator.client.async_get_data(
                f"?{self.entity_description.api_key_command}={value}&chargepoint_nr={self.config_entry.data[DEVICEID]}"
            )
            await self.coordinator.async_request_refresh()

    async def async_unlock(self, **kwargs) -> None:
        """Unlock the device via API."""
        if (
            self.entity_description.api_key_command
            and self.entity_description.api_value_map_command
        ):
            value = self.entity_description.api_value_map_command["unlock"]
            await self.coordinator.client.async_get_data(
                f"?{self.entity_description.api_key_command}={value}&chargepoint_nr={self.config_entry.data[DEVICEID]}"
            )
            await self.coordinator.async_request_refresh()
