"""Common fixtures for the openwb2mqtt tests."""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.components.mqtt.sensor import MQTT_SENSOR_ATTRIBUTES_BLOCKED
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
import homeassistant.components.mqtt as mqtt

from tests.common import MockConfigEntry, async_fire_mqtt_message
from tests.components.mqtt.test_sensor import (
    help_test_setting_attribute_via_mqtt_json_message,
)


@pytest.fixture
def mqtt_mock_entry_no_yaml_config(hass):
    """Fixture to set up a mqtt config entry.

    This fixture creates a mock MQTT config entry and adds it to Home Assistant.
    It mocks the MQTT client's connect and disconnect methods to return success,
    and sets up the necessary data structures in the hass object.

    This is a fundamental fixture for testing MQTT-based components, as it
    provides the base MQTT infrastructure without requiring a real MQTT broker.
    """
    # Mock the MQTT component setup
    with patch("homeassistant.components.mqtt.MQTT") as mock_mqtt:
        mock_mqtt.return_value.async_connect = AsyncMock(return_value=True)
        mock_mqtt.return_value.async_disconnect = AsyncMock(return_value=True)

        # Create a mock MQTT data structure
        mqtt_data = mqtt.MqttData(hass, {})
        mqtt_data.client = mock_mqtt.return_value
        hass.data["mqtt"] = mqtt_data

        # Create and add the config entry
        entry = MockConfigEntry(
            domain=mqtt.DOMAIN,
            data={"broker": "test-broker", "port": 1234},
        )
        entry.add_to_hass(hass)

        yield entry


@pytest.fixture
def mock_mqtt_component(hass):
    """Fixture to mock the MQTT component.

    This fixture mocks the async_subscribe method of the MQTT component,
    allowing tests to capture subscription calls and simulate message
    reception without connecting to a real MQTT broker.

    This is useful for testing components that subscribe to MQTT topics
    and process incoming messages.
    """
    with patch("homeassistant.components.mqtt.async_subscribe") as mock_sub:
        mock_sub.return_value = AsyncMock(return_value=None)
        yield mock_sub


@pytest.fixture
def mock_setup_entry(hass):
    """Fixture to mock setting up a config entry.

    This fixture mocks the async_setup_entry method of the MQTT component
    to always return True, simulating successful setup of the component.

    This is useful for testing the config flow and integration setup without
    actually initializing the real MQTT component.
    """
    with patch(
        "homeassistant.components.mqtt.async_setup_entry", return_value=True
    ) as mock_setup:
        yield mock_setup


@pytest.fixture
def mock_mqtt_client(hass):
    """Fixture to mock the MQTT client.

    This fixture mocks the MQTT client class, specifically its async_connect
    and async_disconnect methods to return True, simulating successful
    connection and disconnection operations.

    This allows tests to simulate MQTT client behavior without requiring
    a real MQTT broker connection.
    """
    with patch("homeassistant.components.mqtt.MQTT") as mock_mqtt:
        mock_mqtt.return_value.async_connect = AsyncMock(return_value=True)
        mock_mqtt.return_value.async_disconnect = AsyncMock(return_value=True)
        yield mock_mqtt


@pytest.fixture
def mock_mqtt_subscribe(hass):
    """Fixture to mock MQTT subscription.

    This fixture mocks the async_subscribe method of the MQTT component,
    allowing tests to capture subscription calls and verify that the
    component is subscribing to the correct topics.

    Tests can also access the callback function passed to async_subscribe
    to simulate message reception.
    """
    with patch("homeassistant.components.mqtt.async_subscribe") as mock_sub:
        yield mock_sub


@pytest.fixture
def mock_mqtt_publish(hass):
    """Fixture to mock MQTT publish.

    This fixture mocks the async_publish method of the MQTT component,
    allowing tests to verify that the component is publishing messages
    to the correct topics with the correct payloads.

    This is essential for testing components that send commands or
    state updates via MQTT.
    """
    with patch("homeassistant.components.mqtt.async_publish") as mock_pub:
        yield mock_pub


@pytest.fixture
def mock_device_registry(hass):
    """Fixture to mock the device registry.

    This fixture mocks the device registry's async_get method,
    allowing tests to verify device registration operations without
    modifying the actual device registry.

    This is useful for testing that components correctly register
    their devices with Home Assistant.
    """
    with patch("homeassistant.helpers.device_registry.async_get") as mock_registry:
        yield mock_registry


@pytest.fixture
def mock_entity_registry(hass):
    """Fixture to mock the entity registry.

    This fixture mocks the entity registry's async_get method,
    allowing tests to verify entity registration operations without
    modifying the actual entity registry.

    This is useful for testing that components correctly register
    their entities with Home Assistant.
    """
    with patch("homeassistant.helpers.entity_registry.async_get") as mock_registry:
        yield mock_registry


@pytest.fixture
def mock_openwb_device():
    """Fixture to create a mock openWB device.

    This fixture returns a dictionary with basic properties for an openWB device,
    including name, state topic, and unique ID.

    This provides a consistent base configuration for testing device-related
    functionality across different test cases.
    """
    return {
        "name": "test",
        "state_topic": "test-topic",
        "unique_id": "test-unique-id",
    }


@pytest.fixture
def mock_openwb_sensor_device():
    """Fixture to create a mock openWB sensor device.

    This fixture returns a dictionary with properties specific to an openWB sensor,
    including name, state topic, unique ID, device class, and unit of measurement.

    This provides a consistent sensor configuration for testing sensor-specific
    functionality across different test cases.
    """
    return {
        "name": "test",
        "state_topic": "test-topic",
        "unique_id": "test-unique-id",
        "device_class": "power",
        "unit_of_measurement": "W",
    }


@pytest.fixture
def mock_openwb_binary_sensor_device():
    """Fixture to create a mock openWB binary sensor device.

    This fixture returns a dictionary with properties specific to an openWB binary sensor,
    including name, state topic, unique ID, and device class.

    This provides a consistent binary sensor configuration for testing binary
    sensor-specific functionality across different test cases.
    """
    return {
        "name": "test",
        "state_topic": "test-topic",
        "unique_id": "test-unique-id",
        "device_class": "plug",
    }


@pytest.fixture
def mock_openwb_select_device():
    """Fixture to create a mock openWB select device.

    This fixture returns a dictionary with properties specific to an openWB select entity,
    including name, state topic, command topic, unique ID, and available options.

    This provides a consistent select configuration for testing select-specific
    functionality across different test cases.
    """
    return {
        "name": "test",
        "state_topic": "test-topic",
        "command_topic": "test-command-topic",
        "unique_id": "test-unique-id",
        "options": ["option1", "option2", "option3"],
    }


@pytest.fixture
def mock_openwb_number_device():
    """Fixture to create a mock openWB number device.

    This fixture returns a dictionary with properties specific to an openWB number entity,
    including name, state topic, command topic, unique ID, and min/max/step values.

    This provides a consistent number configuration for testing number-specific
    functionality across different test cases.
    """
    return {
        "name": "test",
        "state_topic": "test-topic",
        "command_topic": "test-command-topic",
        "unique_id": "test-unique-id",
        "min": 0,
        "max": 100,
        "step": 1,
    }


async def help_test_setup_manual_entity_from_yaml(
    hass, mqtt_mock_entry, config, platform
):
    """Test setup manual configured MQTT entity.

    This helper function tests that a manually configured MQTT entity
    (from YAML configuration) is properly set up in Home Assistant.

    It verifies that the entity state is created in Home Assistant,
    which confirms that the entity was properly initialized and registered.
    """
    assert hass.states.get(f"{platform}.test")


async def help_test_entity_device_info_with_identifier(
    hass, mqtt_mock_entry, platform, config
):
    """Test device registry integration.

    This helper function tests that an MQTT entity correctly registers
    its device information in the Home Assistant device registry.

    It verifies that:
    1. The device is created in the registry with the correct identifier
    2. The device has the correct manufacturer, model, and name

    This ensures proper device representation in the Home Assistant UI.
    """
    entry = MockConfigEntry(domain=mqtt.DOMAIN)
    entry.add_to_hass(hass)

    device_registry = hass.helpers.device_registry.async_get(hass)

    data = {
        "platform": platform,
        "name": "test",
        "state_topic": "test-topic",
        "device": {
            "identifiers": ["helloworld"],
            "manufacturer": "Test",
            "model": "Test",
            "name": "Test",
        },
        "unique_id": "veryunique",
    }

    async_fire_mqtt_message(hass, f"homeassistant/{platform}/bla/config", data)
    await hass.async_block_till_done()

    device = device_registry.async_get_device(identifiers={("mqtt", "helloworld")})
    assert device is not None
    assert device.identifiers == {("mqtt", "helloworld")}
    assert device.manufacturer == "Test"
    assert device.model == "Test"
    assert device.name == "Test"
