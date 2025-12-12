"""The openwbmqtt component for controlling the openWB wallbox via home assistant / MQTT."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api_client import OpenWB2MqttApiClient

# Import global values.
from .const import (
    API_TOKEN,
    API_URL,
    COMM_METHOD_HTTP,
    COMMUNICATION_METHOD,
    DEVICEID,
    DEVICETYPE,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import OpenWB2MqttDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the openWB2 MQTT integration from a config entry."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    if entry.data.get(COMMUNICATION_METHOD) == COMM_METHOD_HTTP:
        api_client = OpenWB2MqttApiClient(
            api_url=entry.data[API_URL],
            token=entry.data.get(API_TOKEN),
            session=async_get_clientsession(hass),
        )
        coordinator = OpenWB2MqttDataUpdateCoordinator(
            hass,
            client=api_client,
            device_type=entry.data[DEVICETYPE],
            device_id=entry.data[DEVICEID],
            config_entry=entry,
        )
        await coordinator.async_config_entry_first_refresh()
        hass.data[DOMAIN][entry.entry_id] = coordinator
    else:
        # MQTT setup remains unchanged
        pass

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    # This is all that's needed. Home Assistant handles the reload.
    await hass.config_entries.async_reload(entry.entry_id)
