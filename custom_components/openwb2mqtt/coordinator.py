"""Data update coordinator for the openWB2 MQTT integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.components import mqtt
from homeassistant.components.mqtt import ReceiveMessage
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api_client import (
    OpenWB2MqttApiClient,
    OpenWB2MqttApiClientError,
)
from .const import (
    COMM_METHOD_MQTT,
    COMMUNICATION_METHOD,
    DEVICEID,
    DEVICETYPE,
    DOMAIN,
    HTTP_CENT_KEYS,
    HTTP_READ_PARAMETER,
    HTTP_RESPONSE_PREFIX,
    HTTP_UPDATE_INTERVAL,
    MQTT_ROOT_TOPIC,
    OpenWBEntityDescription,
    _safeFloat,
    format_command_value,
    get_id_prefix,
    normalize_http_data,
    parse_mqtt_payload,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# simpleAPI coordinators (one per config entry = one openWB device).

type OpenWBConfigEntry = ConfigEntry[OpenWBCoordinator]


def _price_to_cent(value: str | float | bool) -> str | float | bool:
    """Turn a price in EUR/kWh into ct/kWh, the unit both set commands expect."""
    cent = _safeFloat(value, 100, "mult")
    if cent is None:
        return value
    return cent


class OpenWBCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Shared base of the HTTP and the MQTT coordinator."""

    config_entry: OpenWBConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: OpenWBConfigEntry,
        update_interval: timedelta | None,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.data[DEVICETYPE]}_{entry.data[DEVICEID]}",
            update_interval=update_interval,
        )
        self.device_type: str = entry.data[DEVICETYPE]
        self.device_id: int = entry.data[DEVICEID]
        # Entries from v0.3.x have no communication_method key -> they are MQTT
        self.transport: str = entry.data.get(COMMUNICATION_METHOD, COMM_METHOD_MQTT)

    async def async_send_command(
        self,
        description: OpenWBEntityDescription,
        value: str | float | bool,
        shown_value: Any,
    ) -> None:
        """Send a command to the openWB."""
        raise NotImplementedError


class OpenWBHttpCoordinator(OpenWBCoordinator):
    """Poll one device over the simpleAPI HTTP interface."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: OpenWBConfigEntry,
        client: OpenWB2MqttApiClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(hass, entry, timedelta(seconds=HTTP_UPDATE_INTERVAL))
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        """Read all values of the device."""
        parameter = HTTP_READ_PARAMETER[self.device_type]
        try:
            response = await self.client.async_get_data(
                {parameter: str(self.device_id)}
            )
        except OpenWB2MqttApiClientError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        response_key = f"{HTTP_RESPONSE_PREFIX[self.device_type]}_{self.device_id}"
        device_data = response.get(response_key)
        if not isinstance(device_data, dict):
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="no_data",
                translation_placeholders={"key": response_key},
            )
        # Also converts Wh -> kWh and ct/kWh -> EUR/kWh
        return normalize_http_data(device_data, self.device_type)

    async def async_send_command(
        self,
        description: OpenWBEntityDescription,
        value: str | float | bool,
        shown_value: Any,
    ) -> None:
        """Send a command over HTTP and show the sent value until the next poll."""
        command = description.http_command
        if command is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="not_available_http"
            )
        # The entity works in EUR/kWh, the openWB expects ct/kWh
        if description.value_key in HTTP_CENT_KEYS:
            value = _price_to_cent(value)
        data = {command: format_command_value(value, for_http=True)}
        if self.device_type == "chargepoint":
            data["chargepoint_nr"] = str(self.device_id)
        try:
            response = await self.client.async_set_data(data)
        except OpenWB2MqttApiClientError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"command": command},
            ) from err
        if isinstance(response, dict) and response.get("success") is False:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_rejected",
                translation_placeholders={"command": command},
            )
        # Optimistic: show the sent value until the next poll
        new_data = dict(self.data)
        new_data[description.value_key] = shown_value
        self.async_set_updated_data(new_data)  # also restarts the 15 s timer


class OpenWBMqttCoordinator(OpenWBCoordinator):
    """Receive the values of one device from the simpleAPI MQTT topics."""

    def __init__(self, hass: HomeAssistant, entry: OpenWBConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(hass, entry, update_interval=None)  # push, no polling
        self.mqtt_root: str = entry.data[MQTT_ROOT_TOPIC]
        self.topic_prefix: str = (
            f"{self.mqtt_root}/simpleAPI/{self.device_type}/{self.device_id}/"
        )
        # Entities are available and "unknown" until the first message
        self.data = {}

    async def async_start(self) -> None:
        """Subscribe to all topics of the device."""
        unsubscribe = await mqtt.async_subscribe(
            self.hass, f"{self.topic_prefix}#", self._message_received, qos=1
        )
        self.config_entry.async_on_unload(unsubscribe)

    @callback
    def _message_received(self, message: ReceiveMessage) -> None:
        """Store the value of one topic."""
        key = message.topic.removeprefix(self.topic_prefix)
        # Spec unclear: bat/pv/counter may keep "get/" (I2)
        key = key.removeprefix("get/")
        value = parse_mqtt_payload(message.payload)
        # MQTT delivers the price in EUR/Wh, the entities show EUR/kWh
        if key in HTTP_CENT_KEYS:
            price = _safeFloat(value, 1000, "mult")
            if price is not None:
                price = round(price, 4)
            value = price
        if key in self.data and self.data[key] == value:
            return  # nothing changed (N4)
        new_data = dict(self.data)
        new_data[key] = value
        self.async_set_updated_data(new_data)
        if key in ("config/name", "version"):
            self.update_device_info()

    @callback
    def update_device_info(self) -> None:
        """Show the openWB name and software version on the device."""
        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, get_id_prefix(self.config_entry))}
        )
        if device is None:
            return  # entities not set up yet
        # name_by_user is never touched, so a name set by the user still wins
        name = self.data.get("config/name")
        if isinstance(name, str) and name not in ("", device.name):
            device_registry.async_update_device(device.id, name=name)
        version = self.data.get("version")
        if version is not None and str(version) != device.sw_version:
            device_registry.async_update_device(device.id, sw_version=str(version))

    async def _async_update_data(self) -> dict[str, Any]:
        """Return the stored values; this coordinator is never polled."""
        return self.data

    async def async_send_command(
        self,
        description: OpenWBEntityDescription,
        value: str | float | bool,
        shown_value: Any,
    ) -> None:
        """Publish a command to the simpleAPI set topic."""
        command = description.mqtt_command
        if command is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="not_available_mqtt"
            )
        # The entity works in EUR/kWh, the openWB expects ct/kWh
        if description.value_key in HTTP_CENT_KEYS:
            value = _price_to_cent(value)
        topic = f"{self.mqtt_root}/simpleAPI/{command.format(device_id=self.device_id)}"
        await mqtt.async_publish(
            self.hass,
            topic,
            format_command_value(value, for_http=False),
            qos=0,
            retain=False,
        )
