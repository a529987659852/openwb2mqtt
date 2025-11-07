"""Data update coordinator for the openWB2 MQTT integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api_client import (
    OpenWB2MqttApiClient,
    OpenWB2MqttApiClientCommunicationError,
    OpenWB2MqttApiClientError,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class OpenWB2MqttDataUpdateCoordinator(DataUpdateCoordinator):
    """Data update coordinator for the openWB2 MQTT integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: OpenWB2MqttApiClient,
        device_type: str,
        device_id: int,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the data update coordinator."""
        self._device_type = device_type
        self._device_id = device_id
        self.config_entry = config_entry
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{device_type}_{device_id}",
            update_interval=timedelta(seconds=30),
            update_method=self._async_update_data,
        )
        self.config_entry = config_entry
        self.client = client

    async def _async_update_data(self):
        """Update data via library."""
        try:
            if self._device_type == "chargepoint":
                response = await self.client.async_get_data(
                    f"?get_{self._device_type}_all={self._device_id}"
                )
                _LOGGER.debug(response)
                return response.get(f"{self._device_type}_{self._device_id}")
            if self._device_type == "counter":
                response = await self.client.async_get_data(
                    f"?get_{self._device_type}={self._device_id}"
                )
                _LOGGER.debug(response)
                return response.get(f"{self._device_type}_{self._device_id}")
            if self._device_type == "bat":
                response = await self.client.async_get_data(
                    f"?get_battery={self._device_id}"
                )
                _LOGGER.debug(response)
                return response.get(f"battery_{self._device_id}")
            if self._device_type == "pv":
                response = await self.client.async_get_data(
                    f"?get_{self._device_type}={self._device_id}"
                )
                _LOGGER.debug(response)
                return response.get(f"{self._device_type}_{self._device_id}")
            # Add other device types here in the future
            return {}
        except (
            OpenWB2MqttApiClientCommunicationError,
            OpenWB2MqttApiClientError,
        ) as exception:
            raise UpdateFailed(exception) from exception
