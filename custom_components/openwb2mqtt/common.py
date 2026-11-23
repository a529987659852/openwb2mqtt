"""The openwbmqtt component for controlling the openWB wallbox via home assistant / MQTT."""

from __future__ import annotations

from collections.abc import Callable
import copy
import logging
from typing import Any, TypeVar

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
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
    MQTT_ROOT_TOPIC,
    OpenWBEntityDescription,
    get_id_prefix,
)
from .coordinator import OpenWBCoordinator

_LOGGER = logging.getLogger(__name__)

# Type variable for entity classes
T = TypeVar("T", bound=Entity)


class OpenWBBaseEntity:
    """Openwallbox entity base class."""

    deviceID: int | None = None

    def __init__(
        self,
        device_friendly_name: str,
        mqtt_root: str,
    ) -> None:
        """Init device info class."""
        self.device_friendly_name = device_friendly_name
        self.mqtt_root = mqtt_root

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        return DeviceInfo(
            name=self.device_friendly_name,
            identifiers={(DOMAIN, self.device_friendly_name, self.mqtt_root)},
            manufacturer=MANUFACTURER,
            model=MODEL,
        )


async def async_setup_entities(
    hass: HomeAssistant,
    config: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    entity_descriptions: list[Any],
    entity_class: type[T],
    topic_template: str,
    device_type_name: str = None,
    additional_processing: Callable[[Any, str, int, str], None] = None,
) -> None:
    """Set up entities for a specific platform and device type.

    Args:
        hass: The Home Assistant instance
        config: The config entry
        async_add_entities: Callback to add entities
        entity_descriptions: List of entity descriptions
        entity_class: The entity class to instantiate
        topic_template: Template for MQTT topic with placeholders
        device_type_name: Optional friendly name for the device type (defaults to devicetype)
        additional_processing: Optional callback for additional entity description processing
    """
    integration_unique_id = config.unique_id
    mqtt_root = config.data[MQTT_ROOT_TOPIC]
    device_type = config.data[DEVICETYPE]
    device_id = config.data[DEVICEID]

    # Use provided device type name or capitalize the device type
    if device_type_name is None:
        device_type_name = device_type.capitalize()

    entities = []
    descriptions_copy = copy.deepcopy(entity_descriptions)

    for description in descriptions_copy:
        # Format the MQTT topic using the template
        description.mqttTopicCurrentValue = topic_template.format(
            mqtt_root=mqtt_root,
            device_type=device_type,
            device_id=device_id,
            key=description.key,
        )

        # Call additional processing if provided
        if additional_processing:
            additional_processing(description, device_type, device_id, mqtt_root)

        # Create the entity
        entities.append(
            entity_class(
                uniqueID=integration_unique_id,
                description=description,
                device_friendly_name=f"{device_type_name} {device_id}",
                mqtt_root=mqtt_root,
            )
        )

    async_add_entities(entities)


async def async_setup_sensors(
    hass: HomeAssistant,
    config: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    sensor_descriptions: list[Any],
    topic_template: str,
    device_type_name: str = None,
    additional_processing: Callable[[Any, str, int, str], None] = None,
) -> None:
    """Set up sensor entities."""
    from .sensor import openwbSensor  # noqa: PLC0415

    await async_setup_entities(
        hass,
        config,
        async_add_entities,
        sensor_descriptions,
        openwbSensor,
        topic_template,
        device_type_name,
        additional_processing,
    )


async def async_setup_binary_sensors(
    hass: HomeAssistant,
    config: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    binary_sensor_descriptions: list[Any],
    topic_template: str,
    device_type_name: str = None,
) -> None:
    """Set up binary sensor entities."""
    from .binary_sensor import openwbBinarySensor  # noqa: PLC0415

    await async_setup_entities(
        hass,
        config,
        async_add_entities,
        binary_sensor_descriptions,
        openwbBinarySensor,
        topic_template,
        device_type_name,
    )


async def async_setup_selects(
    hass: HomeAssistant,
    config: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    select_descriptions: list[Any],
    topic_template: str,
    device_type_name: str = None,
    additional_processing: Callable[[Any, str, int, str], None] = None,
) -> None:
    """Set up select entities."""
    from .select import openwbSelect  # noqa: PLC0415

    integration_unique_id = config.unique_id
    mqtt_root = config.data[MQTT_ROOT_TOPIC]
    device_type = config.data[DEVICETYPE]
    device_id = config.data[DEVICEID]

    # Use provided device type name or capitalize the device type
    if device_type_name is None:
        device_type_name = device_type.capitalize()

    entities = []
    descriptions_copy = copy.deepcopy(select_descriptions)

    for description in descriptions_copy:
        # Call additional processing if provided
        if additional_processing:
            additional_processing(description, device_type, device_id, mqtt_root)

        # Create the entity
        entities.append(
            openwbSelect(
                uniqueID=integration_unique_id,
                description=description,
                device_friendly_name=f"{device_type_name} {device_id}",
                mqtt_root=mqtt_root,
                deviceID=device_id,
            )
        )

    async_add_entities(entities)


async def async_setup_numbers(
    hass: HomeAssistant,
    config: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    number_descriptions: list[Any],
    topic_template: str,
    device_type_name: str = None,
    additional_processing: Callable[[Any, str, int, str], None] = None,
) -> None:
    """Set up number entities."""
    from .number import openWBNumber  # noqa: PLC0415

    integration_unique_id = config.unique_id
    mqtt_root = config.data[MQTT_ROOT_TOPIC]
    device_type = config.data[DEVICETYPE]
    device_id = config.data[DEVICEID]

    # Use provided device type name or capitalize the device type
    if device_type_name is None:
        device_type_name = device_type.capitalize()

    entities = []
    descriptions_copy = copy.deepcopy(number_descriptions)

    for description in descriptions_copy:
        # Call additional processing if provided
        if additional_processing:
            additional_processing(description, device_type, device_id, mqtt_root)

        # Create the entity
        entities.append(
            openWBNumber(
                uniqueID=integration_unique_id,
                description=description,
                device_friendly_name=f"{device_type_name} {device_id}",
                mqtt_root=mqtt_root,
                deviceID=device_id,
            )
        )

    async_add_entities(entities)


# ---------------------------------------------------------------------------
# simpleAPI entity base (one config entry = one openWB device).
# The legacy code above will be removed later.


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
