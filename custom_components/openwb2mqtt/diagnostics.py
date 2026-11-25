"""Diagnostics support for openWB2 MQTT."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import API_TOKEN
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
    # Only a loaded entry has runtime_data. Entries of removed device types,
    # entries that failed to set up and unloaded entries have none.
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is None:
        return result
    result["values"] = coordinator.data
    return result
