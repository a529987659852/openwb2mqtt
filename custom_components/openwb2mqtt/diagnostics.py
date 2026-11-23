"""Diagnostics support for openWB2 MQTT."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import API_TOKEN, DEVICETYPE, REMOVED_DEVICE_TYPES
from .coordinator import OpenWBConfigEntry

TO_REDACT = {API_TOKEN}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: OpenWBConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    result: dict[str, Any] = {
        "data": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
    }
    if entry.data.get(DEVICETYPE) in REMOVED_DEVICE_TYPES:
        # Removed device types are not set up, so they have no runtime_data
        return result
    result["values"] = entry.runtime_data.data
    return result
