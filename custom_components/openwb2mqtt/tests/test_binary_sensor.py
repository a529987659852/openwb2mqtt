"""Tests for the openwb2mqtt binary_sensor platform."""

import json
from unittest.mock import AsyncMock, MagicMock, call, patch
import time

import pytest

from homeassistant.components import mqtt
from homeassistant.components.binary_sensor import (
    DOMAIN as BINARY_SENSOR_DOMAIN,
    BinarySensorDeviceClass,
)
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

from config.custom_components.openwb2mqtt.const import (
    DOMAIN,
    BINARY_SENSORS_PER_CHARGEPOINT,
    openwbBinarySensorEntityDescription,
)
from config.custom_components.openwb2mqtt.binary_sensor import openwbBinarySensor

from tests.common import MockConfigEntry, async_fire_mqtt_message


async def test_binary_sensor_setup(hass: HomeAssistant, mock_mqtt_subscribe) -> None:
    """Test setting up the binary sensor."""
    # Create a binary sensor description
    description = openwbBinarySensorEntityDescription(
        key="plug_state",
        name="Test Sensor",
        device_class=BinarySensorDeviceClass.PLUG,
        mqttTopicCurrentValue="openWB/chargepoint/1/get/plug_state",
    )

    # Create the binary sensor
    sensor = openwbBinarySensor(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
    )

    # Add the sensor to hass
    sensor.hass = hass

    # Fix the entity_id to use slugify (spaces to underscores)
    sensor.entity_id = f"{BINARY_SENSOR_DOMAIN}.test_sensor"

    # Store the callback function
    callback = None

    # Mock the async_added_to_hass method to capture the callback
    original_async_added = sensor.async_added_to_hass

    async def mock_async_added_to_hass():
        nonlocal callback
        await original_async_added()
        # Get the callback function from the mock
        callback = mock_mqtt_subscribe.call_args[0][2]

    with patch.object(sensor, "async_added_to_hass", mock_async_added_to_hass):
        # Call async_added_to_hass to register the callback
        await sensor.async_added_to_hass()

        # Register the entity with Home Assistant
        hass.states.async_set(
            sensor.entity_id,
            STATE_UNKNOWN,
            {ATTR_DEVICE_CLASS: description.device_class},
        )
        await hass.async_block_till_done()

        # Verify the binary sensor was created
        state = hass.states.get(sensor.entity_id)
        assert state is not None
        assert state.state == STATE_UNKNOWN
        assert state.attributes.get(ATTR_DEVICE_CLASS) == description.device_class

        # Verify the callback was captured
        assert callback is not None

        # Simulate message received - ON state
        message = ReceiveMessage(
            topic="openWB/chargepoint/1/get/plug_state",
            payload="1",
            qos=0,
            retain=False,
            subscribed_topic="openWB/chargepoint/1/get/plug_state",
            timestamp=time.time(),
        )

        # Call the callback with the message
        callback(message)
        await hass.async_block_till_done()

        # Verify state was updated to ON
        state = hass.states.get(sensor.entity_id)
        assert state.state == STATE_ON

        # Simulate message received - OFF state
        message = ReceiveMessage(
            topic="openWB/chargepoint/1/get/plug_state",
            payload="0",
            qos=0,
            retain=False,
            subscribed_topic="openWB/chargepoint/1/get/plug_state",
            timestamp=time.time(),
        )

        # Call the callback with the message
        callback(message)
        await hass.async_block_till_done()

        # Verify state was updated to OFF
        state = hass.states.get(sensor.entity_id)
        assert state.state == STATE_OFF


async def test_openwb_binary_sensor_init(hass: HomeAssistant) -> None:
    """Test initialization of openwbBinarySensor."""
    # Create a binary sensor description
    description = openwbBinarySensorEntityDescription(
        key="plug_state",
        name="Plug State",
        device_class=BinarySensorDeviceClass.PLUG,
    )

    # Create the binary sensor
    sensor = openwbBinarySensor(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
    )

    # Verify sensor properties
    assert sensor.name == "Plug State"
    assert (
        sensor.unique_id == "test_unique_id_plug_state"
    )  # Using slugify which converts hyphens to underscores
    assert sensor.device_info["name"] == "Test Device"
    assert sensor.device_info["identifiers"] == {(DOMAIN, "Test Device", "openWB")}


@pytest.mark.parametrize(
    "payload,expected_state",
    [
        ("1", STATE_ON),
        ("0", STATE_OFF),
        ("ON", STATE_ON),
        ("OFF", STATE_OFF),
        ("true", STATE_ON),
        ("false", STATE_OFF),
        ("invalid", STATE_UNKNOWN),
    ],
)
async def test_binary_sensor_message_received(
    hass: HomeAssistant, mock_mqtt_subscribe, payload, expected_state
) -> None:
    """Test handling of MQTT messages with different payloads.

    This test verifies that the binary sensor correctly processes various payload formats:
    - Numeric values: "1" (ON) and "0" (OFF)
    - String values: "ON"/"OFF" and "true"/"false"
    - Invalid values: Should result in STATE_UNKNOWN

    The test creates a binary sensor, simulates receiving MQTT messages with different
    payloads, and verifies that the sensor state is updated correctly for each payload type.
    This ensures the component is robust and can handle various payload formats that might
    be sent by different MQTT publishers.
    """
    # Create a binary sensor description
    description = openwbBinarySensorEntityDescription(
        key="plug_state",
        name="Test Sensor",
        device_class=BinarySensorDeviceClass.PLUG,
        mqttTopicCurrentValue="openWB/chargepoint/1/get/plug_state",
    )

    # Create the binary sensor
    sensor = openwbBinarySensor(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
    )

    # Add the sensor to hass
    sensor.hass = hass

    # Fix the entity_id to use slugify (spaces to underscores)
    sensor.entity_id = f"{BINARY_SENSOR_DOMAIN}.test_sensor"

    # Store the callback function
    callback = None

    # Mock the async_added_to_hass method to capture the callback
    original_async_added = sensor.async_added_to_hass

    async def mock_async_added_to_hass():
        nonlocal callback
        await original_async_added()
        # Get the callback function from the mock
        callback = mock_mqtt_subscribe.call_args[0][2]

    with patch.object(sensor, "async_added_to_hass", mock_async_added_to_hass):
        # Call async_added_to_hass to register the callback
        await sensor.async_added_to_hass()

        # Register the entity with Home Assistant
        hass.states.async_set(
            sensor.entity_id,
            STATE_UNKNOWN,
            {ATTR_DEVICE_CLASS: description.device_class},
        )
        await hass.async_block_till_done()

        # Verify the callback was captured
        assert callback is not None

        # Simulate message received
        message = ReceiveMessage(
            topic="openWB/chargepoint/1/get/plug_state",
            payload=payload,
            qos=0,
            retain=False,
            subscribed_topic="openWB/chargepoint/1/get/plug_state",
            timestamp=time.time(),
        )

        # Call the callback with the message
        callback(message)
        await hass.async_block_till_done()

        # Verify state was updated
        state = hass.states.get(sensor.entity_id)
        assert state is not None
        assert state.state == expected_state


async def test_binary_sensor_custom_state_function(
    hass: HomeAssistant, mock_mqtt_subscribe
) -> None:
    """Test custom state function in the binary sensor.

    This test verifies that a binary sensor can use a custom state function to determine
    its state based on the received payload. The custom state function allows for more
    complex logic than the default boolean conversion.

    In this test, a binary sensor is created with a custom state function that:
    - Returns True (problem detected) for any value except "0" or empty string
    - Returns False (no problem) for "0" or empty string

    The test simulates receiving different payloads and verifies that the sensor state
    is correctly determined by the custom state function in each case. This demonstrates
    the flexibility of the binary sensor implementation to handle various payload formats
    and custom state determination logic.
    """
    # Create a binary sensor description with a custom state function
    description = openwbBinarySensorEntityDescription(
        key="fault_state",
        name="Fault State",
        device_class=BinarySensorDeviceClass.PROBLEM,
        state=lambda x: x.strip() != "0" and x.strip() != "",
        mqttTopicCurrentValue="openWB/chargepoint/1/get/fault_state",
    )

    # Create the binary sensor
    sensor = openwbBinarySensor(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
    )

    # Add the sensor to hass
    sensor.hass = hass

    # Fix the entity_id to use slugify (spaces to underscores)
    sensor.entity_id = f"{BINARY_SENSOR_DOMAIN}.test_unique_id_fault_state"

    # Store the callback function
    callback = None

    # Mock the async_added_to_hass method to capture the callback
    original_async_added = sensor.async_added_to_hass

    async def mock_async_added_to_hass():
        nonlocal callback
        await original_async_added()
        # Get the callback function from the mock
        callback = mock_mqtt_subscribe.call_args[0][2]

    with patch.object(sensor, "async_added_to_hass", mock_async_added_to_hass):
        # Call async_added_to_hass to register the callback
        await sensor.async_added_to_hass()

        # Verify the callback was captured
        assert callback is not None

        # Simulate message received - fault state
        message = ReceiveMessage(
            topic="openWB/chargepoint/1/get/fault_state",
            payload="1",
            qos=0,
            retain=False,
            subscribed_topic="openWB/chargepoint/1/get/fault_state",
            timestamp=time.time(),
        )

        # Call the callback with the message
        callback(message)

        # Verify state was updated with transformed value
        assert sensor._attr_is_on is True

        # Simulate message received - no fault state
        message = ReceiveMessage(
            topic="openWB/chargepoint/1/get/fault_state",
            payload="0",
            qos=0,
            retain=False,
            subscribed_topic="openWB/chargepoint/1/get/fault_state",
            timestamp=time.time(),
        )
        callback(message)

        # Verify state was updated with transformed value
        assert sensor._attr_is_on is False

        # Simulate message received - empty string
        message = ReceiveMessage(
            topic="openWB/chargepoint/1/get/fault_state",
            payload="",
            qos=0,
            retain=False,
            subscribed_topic="openWB/chargepoint/1/get/fault_state",
            timestamp=time.time(),
        )
        callback(message)

        # Verify state was updated with transformed value
        assert sensor._attr_is_on is False
