"""Tests for the openwb2mqtt integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from config.custom_components.openwb2mqtt import (
    async_setup_entry,
    async_unload_entry,
)
from config.custom_components.openwb2mqtt.const import PLATFORMS


async def test_setup_entry(hass: HomeAssistant) -> None:
    """Test setting up the integration.

    This test verifies that the async_setup_entry function correctly:
    1. Forwards the config entry to all supported platforms
    2. Returns True on successful setup

    The async_setup_entry function is the main entry point for setting up
    the integration when a config entry is loaded, so it's critical that
    it properly initializes all platforms.
    """
    # Create a mock config entry
    entry = MagicMock(spec=ConfigEntry)

    # Mock the async_forward_entry_setups method
    with patch.object(
        hass.config_entries, "async_forward_entry_setups", return_value=True
    ) as mock_forward:
        # Call the setup function
        result = await async_setup_entry(hass, entry)

        # Verify the result
        assert result is True

        # Verify the platforms were set up
        mock_forward.assert_called_once_with(entry, PLATFORMS)


async def test_unload_entry(hass: HomeAssistant) -> None:
    """Test unloading the integration.

    This test verifies that the async_unload_entry function correctly:
    1. Unloads all platforms that were set up with the config entry
    2. Returns True on successful unloading

    Proper unloading is important for clean removal of the integration
    and to prevent memory leaks or lingering subscriptions.
    """
    # Create a mock config entry
    entry = MagicMock(spec=ConfigEntry)

    # Mock the async_unload_platforms method
    with patch.object(
        hass.config_entries, "async_unload_platforms", return_value=True
    ) as mock_unload:
        # Call the unload function
        result = await async_unload_entry(hass, entry)

        # Verify the result
        assert result is True

        # Verify the platforms were unloaded
        mock_unload.assert_called_once_with(entry, PLATFORMS)
