"""The openwbmqtt component for controlling the openWB wallbox via home assistant / MQTT."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
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
    REMOVED_DEVICE_TYPES,
)
from .coordinator import OpenWB2MqttDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def _get_issue_id(entry: ConfigEntry) -> str:
    """Return the repair issue ID for an entry with a removed device type."""
    return f"unsupported_device_type_{entry.entry_id}"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the openWB2 MQTT integration from a config entry."""
    device_type = entry.data.get(DEVICETYPE)
    if device_type in REMOVED_DEVICE_TYPES:
        # This device type is no longer supported. Show a repair issue and
        # create no entities. No config_entry_id= kwarg: it only exists
        # since HA 2026.11 (TypeError on older HA).
        ir.async_create_issue(
            hass,
            DOMAIN,
            _get_issue_id(entry),
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="unsupported_device_type",
            translation_placeholders={
                "title": entry.title,
                "device_type": device_type,
            },
        )
        return True

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
    if entry.data.get(DEVICETYPE) in REMOVED_DEVICE_TYPES:
        # Nothing was set up for removed device types.
        return True

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the repair issue when the entry is removed."""
    ir.async_delete_issue(hass, DOMAIN, _get_issue_id(entry))
