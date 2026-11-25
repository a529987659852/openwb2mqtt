"""The openwbmqtt component for controlling the openWB wallbox via home assistant / MQTT."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import (
    COMM_METHOD_HTTP,
    COMM_METHOD_MQTT,
    COMMUNICATION_METHOD,
    CONF_VEHICLES,
    DEVICE_TYPE_NAMES,
    DEVICEID,
    DEVICETYPE,
    DOMAIN,
    MANUFACTURER,
    MODEL,
    OpenWBEntityDescription,
    get_id_prefix,
)
from .coordinator import OpenWBCoordinator


def build_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return the device info of a config entry."""
    if entry.data.get(COMMUNICATION_METHOD, COMM_METHOD_MQTT) == COMM_METHOD_HTTP:
        name = entry.title
    else:
        device_type_name = DEVICE_TYPE_NAMES[entry.data[DEVICETYPE]]
        name = f"{device_type_name} {entry.data[DEVICEID]}"
    return DeviceInfo(
        identifiers={(DOMAIN, get_id_prefix(entry))},
        name=name,
        manufacturer=MANUFACTURER,
        model=MODEL,
    )


def is_supported(description: OpenWBEntityDescription, transport: str) -> bool:
    """Return True if the entity is available for the transport (HTTP or MQTT)."""
    if transport == COMM_METHOD_HTTP:
        return description.supports_http
    return description.supports_mqtt


def get_vehicles(entry: ConfigEntry) -> dict[str, str]:
    """Return vehicle id -> name from the options (fallback: data)."""
    return entry.options.get(CONF_VEHICLES, entry.data.get(CONF_VEHICLES, {}))


class OpenWBEntity(CoordinatorEntity[OpenWBCoordinator]):
    """Base class of all simpleAPI entities."""

    entity_description: OpenWBEntityDescription

    def __init__(
        self,
        coordinator: OpenWBCoordinator,
        description: OpenWBEntityDescription,
        platform: Platform,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        entry = coordinator.config_entry
        # Same formula as the legacy entities, so the IDs do not change
        self._attr_unique_id = slugify(f"{get_id_prefix(entry)}_{description.name}")
        # Only used when the entity is registered for the first time
        self.entity_id = f"{platform}.{self._attr_unique_id}"
        self._attr_name = description.name
        self._attr_device_info = build_device_info(entry)

    def has_value(self) -> bool:
        """Return True if the coordinator has a value for this entity."""
        data = self.coordinator.data
        if data is None:
            return False
        return data.get(self.entity_description.value_key) is not None

    def get_value(self) -> Any:
        """Return the value for this entity, converted by value_fn if there is one."""
        if not self.has_value():
            return None
        value = self.coordinator.data[self.entity_description.value_key]
        if self.entity_description.value_fn is not None:
            return self.entity_description.value_fn(value)
        return value

    async def async_send_value(
        self, value: str | float | bool, shown_value: Any = None
    ) -> None:
        """Send a value to the openWB.

        shown_value is the value the entity shows until the next update
        (default: the sent value).
        """
        if shown_value is None:
            shown_value = value
        await self.coordinator.async_send_command(
            self.entity_description, value, shown_value
        )
