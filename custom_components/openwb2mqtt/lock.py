"""OpenWB Lock Entity."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .common import OpenWBEntity, is_supported
from .const import (
    LOCKS_BY_DEVICE_TYPE,
    OpenWBLockEntityDescription,
    _to_bool,
)
from .coordinator import OpenWBConfigEntry

_LOGGER = logging.getLogger(__name__)

# The coordinator does all updates, so entities never update in parallel
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenWBConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up lock entities for openWB."""
    coordinator = entry.runtime_data
    descriptions = LOCKS_BY_DEVICE_TYPE.get(coordinator.device_type, [])
    async_add_entities(
        OpenWBLock(coordinator, description, Platform.LOCK)
        for description in descriptions
        if is_supported(description, coordinator.transport)
    )


class OpenWBLock(OpenWBEntity, LockEntity):
    """Lock of a simpleAPI device."""

    entity_description: OpenWBLockEntityDescription

    @property
    def is_locked(self) -> bool | None:
        """Return True if the lock is locked."""
        return _to_bool(self.get_value())

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the device."""
        await self.async_send_value(True)

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the device."""
        await self.async_send_value(False)
