"""OpenWB Selector."""

from homeassistant.components.select import SelectEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .common import OpenWBEntity, get_vehicles, is_supported
from .const import DOMAIN, SELECTS_BY_DEVICE_TYPE, OpenWBSelectEntityDescription
from .coordinator import OpenWBConfigEntry

# The coordinator does all updates, so entities never update in parallel
PARALLEL_UPDATES = 0

# Key of the select that chooses the connected vehicle
CONNECTED_VEHICLE_KEY = "connected_vehicle"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenWBConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Initialize the select and the openWB device."""
    coordinator = entry.runtime_data
    descriptions = SELECTS_BY_DEVICE_TYPE.get(coordinator.device_type, [])
    async_add_entities(
        OpenWBSelect(coordinator, description, Platform.SELECT)
        for description in descriptions
        if is_supported(description, coordinator.transport)
    )


class OpenWBSelect(OpenWBEntity, SelectEntity):
    """Select of a simpleAPI device."""

    entity_description: OpenWBSelectEntityDescription
    # Some values are never reported back by the openWB (e.g. bat_mode),
    # so the entity keeps the last sent option as a fallback.
    _last_sent_option: str | None = None

    def _is_vehicle_select(self) -> bool:
        """Return True if this select chooses the connected vehicle."""
        return self.entity_description.key == CONNECTED_VEHICLE_KEY

    @property
    def options(self) -> list[str]:
        """Return the selectable options."""
        if self._is_vehicle_select():
            vehicles = get_vehicles(self.coordinator.config_entry)
            return list(vehicles.values())
        return list(self.entity_description.options or [])

    @property
    def current_option(self) -> str | None:
        """Return the selected option."""
        if not self.has_value():
            return self._last_sent_option
        value = self.get_value()
        if self._is_vehicle_select():
            vehicles = get_vehicles(self.coordinator.config_entry)
            # The value is normally the vehicle name; an id is turned into its name
            if str(value) in vehicles:
                return vehicles[str(value)]
            return str(value)
        value_map = self.entity_description.value_map or {}
        return value_map.get(value)

    async def async_select_option(self, option: str) -> None:
        """Send the chosen option to the openWB."""
        if self._is_vehicle_select():
            vehicles = get_vehicles(self.coordinator.config_entry)
            vehicle_id = None
            for key, name in vehicles.items():
                if name == option:
                    vehicle_id = key
                    break
            if vehicle_id is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="option_not_settable"
                )
            await self.async_send_value(vehicle_id, shown_value=option)
        else:
            command_map = self.entity_description.command_map or {}
            command = command_map.get(option)
            if command is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="option_not_settable"
                )
            # Show the API value that belongs to the option until the next update
            shown_value = command
            value_map = self.entity_description.value_map or {}
            for api_value, mapped_option in value_map.items():
                if mapped_option == option:
                    shown_value = api_value
                    break
            await self.async_send_value(command, shown_value=shown_value)
        self._last_sent_option = option
        self.async_write_ha_state()
