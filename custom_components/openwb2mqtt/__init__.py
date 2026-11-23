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
    DEVICETYPE,
    DOMAIN,
    PLATFORMS,
    REMOVED_DEVICE_TYPES,
)
from .coordinator import OpenWBConfigEntry, OpenWBHttpCoordinator

_LOGGER = logging.getLogger(__name__)


def _get_issue_id(entry: ConfigEntry) -> str:
    """Return the repair issue ID for an entry with a removed device type."""
    return f"unsupported_device_type_{entry.entry_id}"


async def async_setup_entry(hass: HomeAssistant, entry: OpenWBConfigEntry) -> bool:
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

    if entry.data.get(COMMUNICATION_METHOD) == COMM_METHOD_HTTP:
        api_client = OpenWB2MqttApiClient(
            api_url=entry.data[API_URL],
            token=entry.data.get(API_TOKEN),
            session=async_get_clientsession(hass),
        )
        coordinator = OpenWBHttpCoordinator(hass, entry, api_client)
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
    # MQTT entries still use the legacy entities (no coordinator yet)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OpenWBConfigEntry) -> bool:
    """Unload a config entry."""
    if entry.data.get(DEVICETYPE) in REMOVED_DEVICE_TYPES:
        # Nothing was set up for removed device types.
        return True

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the repair issue when the entry is removed."""
    ir.async_delete_issue(hass, DOMAIN, _get_issue_id(entry))
