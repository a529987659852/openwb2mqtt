"""The openwbmqtt component for controlling the openWB wallbox via home assistant / MQTT."""

import logging

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api_client import OpenWB2MqttApiClient

# Import global values.
from .const import (
    API_TOKEN,
    API_URL,
    COMM_METHOD_HTTP,
    COMM_METHOD_MQTT,
    COMMUNICATION_METHOD,
    DEVICE_TYPE_NAMES,
    DEVICEID,
    DEVICETYPE,
    DOMAIN,
    ID_PREFIX,
    MQTT_ROOT_TOPIC,
    PLATFORMS,
    REMOVED_DEVICE_TYPES,
    get_id_prefix,
)
from .coordinator import OpenWBConfigEntry, OpenWBHttpCoordinator, OpenWBMqttCoordinator

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
            # Old entries have no verify_ssl: check certificates as before
            session=async_get_clientsession(
                hass, verify_ssl=entry.data.get(CONF_VERIFY_SSL, True)
            ),
        )
        coordinator = OpenWBHttpCoordinator(hass, entry, api_client)
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
    else:
        if not await mqtt.async_wait_for_mqtt_client(hass):
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN, translation_key="mqtt_not_ready"
            )
        coordinator = OpenWBMqttCoordinator(hass, entry)
        await coordinator.async_start()
        entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if isinstance(coordinator, OpenWBMqttCoordinator):
        # Entity setup set the name "Chargepoint N"; use the openWB name if
        # the retained messages arrived first
        coordinator.update_device_info()
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old entries. IDs of entities and devices must stay the same."""
    if entry.version == 1 and entry.minor_version < 2:
        id_prefix = get_id_prefix(entry)  # old rule
        device_type = entry.data.get(DEVICETYPE)
        is_mqtt = (
            entry.data.get(COMMUNICATION_METHOD, COMM_METHOD_MQTT) == COMM_METHOD_MQTT
        )
        if is_mqtt and device_type in DEVICE_TYPE_NAMES:
            # Device identifier used by the removed legacy MQTT entities
            old_identifier = (
                DOMAIN,
                f"{DEVICE_TYPE_NAMES[device_type]} {entry.data[DEVICEID]}",
                entry.data[MQTT_ROOT_TOPIC],
            )
            device_registry = dr.async_get(hass)
            for device in dr.async_entries_for_config_entry(
                device_registry, entry.entry_id
            ):
                if old_identifier in device.identifiers:
                    try:
                        device_registry.async_update_device(
                            device.id, new_identifiers={(DOMAIN, id_prefix)}
                        )
                    except HomeAssistantError as err:  # DeviceIdentifierCollisionError
                        _LOGGER.warning(
                            "Could not migrate device %s: %s", device.name, err
                        )
        new_data = dict(entry.data)
        new_data[ID_PREFIX] = id_prefix
        new_data.setdefault(COMMUNICATION_METHOD, COMM_METHOD_MQTT)
        hass.config_entries.async_update_entry(entry, data=new_data, minor_version=2)
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
