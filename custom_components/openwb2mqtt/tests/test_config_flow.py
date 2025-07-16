"""Tests for the openwb2mqtt config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from config.custom_components.openwb2mqtt.config_flow import openwbmqttConfigFlow
from config.custom_components.openwb2mqtt.const import (
    DEVICEID,
    DEVICETYPE,
    DOMAIN,
    MQTT_ROOT_TOPIC,
)


async def test_config_flow_user_step_first_time(hass: HomeAssistant) -> None:
    """Test the user step of the config flow for first time setup.

    This test verifies that:
    1. The initial form is displayed correctly with no input
    2. When user input is provided for a chargepoint:
       - The unique ID is set correctly based on MQTT root, device type, and ID
       - The abort check is called with the correct error
       - A config entry is created with the correct title and data

    This ensures the config flow correctly handles user input and creates
    appropriate config entries for the integration.
    """
    # Create the flow
    flow = openwbmqttConfigFlow()
    flow.hass = hass

    # Test the user step with no input (should show form)
    result = await flow.async_step_user()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert "data_schema" in result

    # Test the user step with input for a chargepoint
    user_input = {
        MQTT_ROOT_TOPIC: "openWB",
        DEVICETYPE: "chargepoint",
        DEVICEID: 1,
    }

    # Mock the async_set_unique_id method
    with (
        patch.object(flow, "async_set_unique_id") as mock_set_unique_id,
        patch.object(flow, "_abort_if_unique_id_configured") as mock_abort,
    ):
        # Call the user step with input
        result = await flow.async_step_user(user_input)

        # Verify the unique ID was set
        mock_set_unique_id.assert_called_once_with("openWB-chargepoint-1")

        # Verify abort was called with the correct error
        mock_abort.assert_called_once_with(error="chargepoint_already_configured")

        # Verify the result is a create entry
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "openWB-chargepoint-1"
        assert result["data"] == user_input


async def test_config_flow_user_step_controller(hass: HomeAssistant) -> None:
    """Test the user step of the config flow for controller setup.

    This test verifies that when setting up a controller device:
    1. The unique ID is set correctly using only the MQTT root and "controller"
       (without a device ID)
    2. The abort check is called with the correct controller-specific error
    3. A config entry is created with the correct title and data

    Controllers are special devices that don't have an ID, so this test ensures
    they are handled differently from other device types.
    """
    # Create the flow
    flow = openwbmqttConfigFlow()
    flow.hass = hass

    # Test the user step with input for a controller
    user_input = {
        MQTT_ROOT_TOPIC: "openWB",
        DEVICETYPE: "controller",
        DEVICEID: 1,
    }

    # Mock the async_set_unique_id method
    with (
        patch.object(flow, "async_set_unique_id") as mock_set_unique_id,
        patch.object(flow, "_abort_if_unique_id_configured") as mock_abort,
    ):
        # Call the user step with input
        result = await flow.async_step_user(user_input)

        # Verify the unique ID was set
        mock_set_unique_id.assert_called_once_with("openWB-controller")

        # Verify abort was called with the correct error
        mock_abort.assert_called_once_with(error="controller_already_configured")

        # Verify the result is a create entry
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "openWB-controller"
        assert result["data"] == user_input


async def test_config_flow_user_step_battery(hass: HomeAssistant) -> None:
    """Test the user step of the config flow for battery setup.

    This test verifies that when setting up a battery device:
    1. The unique ID is set correctly using the MQTT root, "bat", and device ID
    2. The abort check is called with the correct battery-specific error
    3. A config entry is created with the correct title and data

    This ensures battery devices are properly configured with the correct
    identifiers and error handling.
    """
    # Create the flow
    flow = openwbmqttConfigFlow()
    flow.hass = hass

    # Test the user step with input for a battery
    user_input = {
        MQTT_ROOT_TOPIC: "openWB",
        DEVICETYPE: "bat",
        DEVICEID: 1,
    }

    # Mock the async_set_unique_id method
    with (
        patch.object(flow, "async_set_unique_id") as mock_set_unique_id,
        patch.object(flow, "_abort_if_unique_id_configured") as mock_abort,
    ):
        # Call the user step with input
        result = await flow.async_step_user(user_input)

        # Verify the unique ID was set
        mock_set_unique_id.assert_called_once_with("openWB-bat-1")

        # Verify abort was called with the correct error
        mock_abort.assert_called_once_with(error="batterie_already_configured")

        # Verify the result is a create entry
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "openWB-bat-1"
        assert result["data"] == user_input


async def test_config_flow_user_step_counter(hass: HomeAssistant) -> None:
    """Test the user step of the config flow for counter setup.

    This test verifies that when setting up a counter device:
    1. The unique ID is set correctly using the MQTT root, "counter", and device ID
    2. The abort check is called with the correct counter-specific error
    3. A config entry is created with the correct title and data

    This ensures counter devices are properly configured with the correct
    identifiers and error handling.
    """
    # Create the flow
    flow = openwbmqttConfigFlow()
    flow.hass = hass

    # Test the user step with input for a counter
    user_input = {
        MQTT_ROOT_TOPIC: "openWB",
        DEVICETYPE: "counter",
        DEVICEID: 1,
    }

    # Mock the async_set_unique_id method
    with (
        patch.object(flow, "async_set_unique_id") as mock_set_unique_id,
        patch.object(flow, "_abort_if_unique_id_configured") as mock_abort,
    ):
        # Call the user step with input
        result = await flow.async_step_user(user_input)

        # Verify the unique ID was set
        mock_set_unique_id.assert_called_once_with("openWB-counter-1")

        # Verify abort was called with the correct error
        mock_abort.assert_called_once_with(error="counter_already_configured")

        # Verify the result is a create entry
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "openWB-counter-1"
        assert result["data"] == user_input


async def test_config_flow_user_step_pv(hass: HomeAssistant) -> None:
    """Test the user step of the config flow for PV setup.

    This test verifies that when setting up a PV (photovoltaic) device:
    1. The unique ID is set correctly using the MQTT root, "pv", and device ID
    2. The abort check is called with the correct PV-specific error
    3. A config entry is created with the correct title and data

    This ensures PV devices are properly configured with the correct
    identifiers and error handling.
    """
    # Create the flow
    flow = openwbmqttConfigFlow()
    flow.hass = hass

    # Test the user step with input for a PV generator
    user_input = {
        MQTT_ROOT_TOPIC: "openWB",
        DEVICETYPE: "pv",
        DEVICEID: 1,
    }

    # Mock the async_set_unique_id method
    with (
        patch.object(flow, "async_set_unique_id") as mock_set_unique_id,
        patch.object(flow, "_abort_if_unique_id_configured") as mock_abort,
    ):
        # Call the user step with input
        result = await flow.async_step_user(user_input)

        # Verify the unique ID was set
        mock_set_unique_id.assert_called_once_with("openWB-pv-1")

        # Verify abort was called with the correct error
        mock_abort.assert_called_once_with(error="pv_already_configured")

        # Verify the result is a create entry
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "openWB-pv-1"
        assert result["data"] == user_input


async def test_config_flow_user_step_vehicle(hass: HomeAssistant) -> None:
    """Test the user step of the config flow for vehicle setup.

    This test verifies that when setting up a vehicle device:
    1. The unique ID is set correctly using the MQTT root, "vehicle", and device ID
    2. The abort check is called with the correct vehicle-specific error
    3. A config entry is created with the correct title and data

    This ensures vehicle devices are properly configured with the correct
    identifiers and error handling.
    """
    # Create the flow
    flow = openwbmqttConfigFlow()
    flow.hass = hass

    # Test the user step with input for a vehicle
    user_input = {
        MQTT_ROOT_TOPIC: "openWB",
        DEVICETYPE: "vehicle",
        DEVICEID: 1,
    }

    # Mock the async_set_unique_id method
    with (
        patch.object(flow, "async_set_unique_id") as mock_set_unique_id,
        patch.object(flow, "_abort_if_unique_id_configured") as mock_abort,
    ):
        # Call the user step with input
        result = await flow.async_step_user(user_input)

        # Verify the unique ID was set
        mock_set_unique_id.assert_called_once_with("openWB-vehicle-1")

        # Verify abort was called with the correct error
        mock_abort.assert_called_once_with(error="vehicle_already_configured")

        # Verify the result is a create entry
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "openWB-vehicle-1"
        assert result["data"] == user_input


async def test_config_flow_user_step_unknown_type(hass: HomeAssistant) -> None:
    """Test the user step of the config flow for unknown device type.

    This test verifies that when setting up a device with an unknown type:
    1. The unique ID is still set correctly using the MQTT root, device type, and ID
    2. The abort check is called without a specific error
    3. A config entry is created with the correct title and data

    This ensures the config flow is robust and can handle unexpected device types
    gracefully, allowing for future expansion of supported device types.
    """
    # Create the flow
    flow = openwbmqttConfigFlow()
    flow.hass = hass

    # Test the user step with input for an unknown device type
    user_input = {
        MQTT_ROOT_TOPIC: "openWB",
        DEVICETYPE: "unknown",
        DEVICEID: 1,
    }

    # Mock the async_set_unique_id method
    with (
        patch.object(flow, "async_set_unique_id") as mock_set_unique_id,
        patch.object(flow, "_abort_if_unique_id_configured") as mock_abort,
    ):
        # Call the user step with input
        result = await flow.async_step_user(user_input)

        # Verify the unique ID was set
        mock_set_unique_id.assert_called_once_with("openWB-unknown-1")

        # Verify abort was called with no specific error
        mock_abort.assert_called_once_with()

        # Verify the result is a create entry
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "openWB-unknown-1"
        assert result["data"] == user_input
