"""OpenWB Number Entity."""

from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .common import OpenWBEntity, is_supported
from .const import (
    CONF_WALLBOX_POWER,
    NUMBERS_BY_DEVICE_TYPE,
    OpenWBNumberEntityDescription,
    _whole_number,
    max_current_for_wallbox_power,
)
from .coordinator import OpenWBConfigEntry

# The coordinator does all updates, so entities never update in parallel
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenWBConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up number entities for openWB."""
    coordinator = entry.runtime_data
    descriptions = NUMBERS_BY_DEVICE_TYPE.get(coordinator.device_type, [])
    async_add_entities(
        OpenWBNumber(coordinator, description, Platform.NUMBER)
        for description in descriptions
        if is_supported(description, coordinator.transport)
    )


class OpenWBNumber(OpenWBEntity, NumberEntity):
    """Number of a simpleAPI device."""

    entity_description: OpenWBNumberEntityDescription
    # The openWB does not report every set value back (e.g. some limits),
    # so the entity keeps the last sent value as a fallback.
    _last_sent_value: float | None = None

    @property
    def native_max_value(self) -> float:
        """Return the maximum value (depends on the wallbox power for currents)."""
        if self.entity_description.max_from_wallbox_power:
            entry = self.coordinator.config_entry
            power = entry.options.get(
                CONF_WALLBOX_POWER, entry.data.get(CONF_WALLBOX_POWER)
            )
            return max_current_for_wallbox_power(power)
        return super().native_max_value

    @property
    def native_value(self) -> Any:
        """Return the current value."""
        if self.has_value():
            value = self.get_value()
        else:
            value = self._last_sent_value
        if self.unit_of_measurement != self.native_unit_of_measurement:
            # The user chose another unit: keep the float, so the unit
            # conversion of Home Assistant keeps the decimals
            return value
        return _whole_number(value, self.native_step)

    async def async_set_native_value(self, value: float) -> None:
        """Send a new value to the openWB."""
        await self.async_send_value(value)
        self._last_sent_value = value
        self.async_write_ha_state()
