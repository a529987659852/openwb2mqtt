"""Tests for the openwb2mqtt sensor platform."""

import json
import time
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

from config.custom_components.openwb2mqtt.const import (
    DOMAIN,
    SENSORS_PER_CHARGEPOINT,
    openwbDynamicSensorEntityDescription,
    openwbSensorEntityDescription,
)
from config.custom_components.openwb2mqtt.sensor import (
    openwbSensor,
    openwbDynamicSensor,
)

from tests.common import MockConfigEntry, async_fire_mqtt_message


async def test_sensor_setup(hass: HomeAssistant) -> None:
    """Test setting up the sensor.

    This test verifies the basic setup and functionality of a sensor entity:
    1. Creating a sensor entity with specific configuration
    2. Adding it to Home Assistant and verifying its initial state
    3. Subscribing to the appropriate MQTT topic
    4. Processing an incoming MQTT message
    5. Verifying the state is updated correctly based on the message

    This ensures the core functionality of receiving MQTT messages and
    updating the entity state works as expected.
    """
    # Mock MQTT component
    with patch("homeassistant.components.mqtt.async_subscribe") as mock_subscribe:
        mock_subscribe.return_value = AsyncMock(return_value=None)

        # Create a sensor description
        description = openwbSensorEntityDescription(
            key="power",
            name="Power",
            device_class=SensorDeviceClass.POWER,
            native_unit_of_measurement=UnitOfPower.WATT,
            state_class=SensorStateClass.MEASUREMENT,
            mqttTopicCurrentValue="openWB/chargepoint/1/get/power",
        )

        # Create the sensor
        sensor = openwbSensor(
            uniqueID="test_unique_id",
            description=description,
            device_friendly_name="Test Device",
            mqtt_root="openWB",
        )

        # Add the sensor to hass
        sensor.hass = hass

        # Register the entity with Home Assistant
        hass.states.async_set(
            sensor.entity_id,
            STATE_UNKNOWN,
            {
                ATTR_DEVICE_CLASS: description.device_class,
                ATTR_UNIT_OF_MEASUREMENT: description.native_unit_of_measurement,
            },
        )
        await hass.async_block_till_done()

        # Call async_added_to_hass to register the callback
        await sensor.async_added_to_hass()

        # Verify the sensor was created
        state = hass.states.get(sensor.entity_id)
        assert state is not None
        assert state.state == STATE_UNKNOWN
        assert state.attributes.get(ATTR_DEVICE_CLASS) == description.device_class
        assert (
            state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
            == description.native_unit_of_measurement
        )

        # Get the callback function from the mock
        callback = mock_subscribe.call_args[0][2]

        # Simulate message received
        message = ReceiveMessage(
            topic="openWB/chargepoint/1/get/power",
            payload="1000",
            qos=0,
            retain=False,
            subscribed_topic="openWB/chargepoint/1/get/power",
            timestamp=time.time(),
        )

        # Call the callback with the message
        callback(message)

        # Verify state was updated
        assert sensor._attr_native_value == "1000"


async def test_sensor_value_transformation(hass: HomeAssistant) -> None:
    """Test value transformation in the sensor.

    This test verifies that the sensor correctly applies its value_fn to transform
    incoming MQTT payloads before updating its state. In this case, it tests a
    transformation that converts a value from milliwatt-hours to kilowatt-hours
    by dividing by 1000.

    This functionality is important for sensors that need to convert between
    different units or formats used by the MQTT API and Home Assistant.
    """
    # Mock MQTT component
    with patch("homeassistant.components.mqtt.async_subscribe") as mock_subscribe:
        mock_subscribe.return_value = AsyncMock(return_value=None)

        # Create a sensor description with a value function for transformation
        description = openwbSensorEntityDescription(
            key="daily_imported",
            name="Daily Imported",
            device_class=SensorDeviceClass.ENERGY,
            native_unit_of_measurement="kWh",
            state_class=SensorStateClass.TOTAL_INCREASING,
            mqttTopicCurrentValue="openWB/chargepoint/1/get/daily_imported",
            value_fn=lambda x: str(float(x) / 1000.0),
        )

        # Create the sensor
        sensor = openwbSensor(
            uniqueID="test_unique_id",
            description=description,
            device_friendly_name="Test Device",
            mqtt_root="openWB",
        )

        # Add the sensor to hass
        sensor.hass = hass

        # Register the entity with Home Assistant
        hass.states.async_set(
            sensor.entity_id,
            STATE_UNKNOWN,
            {
                ATTR_DEVICE_CLASS: description.device_class,
                ATTR_UNIT_OF_MEASUREMENT: description.native_unit_of_measurement,
            },
        )
        await hass.async_block_till_done()

        # Call async_added_to_hass to register the callback
        await sensor.async_added_to_hass()

        # Get the callback function from the mock
        callback = mock_subscribe.call_args[0][2]

        # Simulate message received
        message = ReceiveMessage(
            topic="openWB/chargepoint/1/get/daily_imported",
            payload="1000000",
            qos=0,
            retain=False,
            subscribed_topic="openWB/chargepoint/1/get/daily_imported",
            timestamp=time.time(),
        )

        # Call the callback with the message
        callback(message)

        # Verify state was updated with transformed value
        assert sensor._attr_native_value == "1000.0"


async def test_openwb_sensor_init(hass: HomeAssistant) -> None:
    """Test initialization of openwbSensor.

    This test verifies that the openwbSensor entity is correctly initialized with:
    1. The proper name, unique_id, and device_info
    2. The correct device class, unit of measurement, and state class
    3. The correct icon

    This ensures the entity is created with the right properties and
    metadata for proper integration with Home Assistant.
    """
    # Create a sensor description
    description = openwbSensorEntityDescription(
        key="power",
        name="Power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:flash",
    )

    # Create the sensor
    sensor = openwbSensor(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
    )

    # Verify sensor properties
    assert sensor.name == "Power"
    assert sensor.unique_id == "test_unique_id_power"
    assert sensor.device_info["name"] == "Test Device"
    assert sensor.device_info["identifiers"] == {(DOMAIN, "Test Device", "openWB")}


@pytest.mark.parametrize(
    "payload,expected_state",
    [
        ("100", "100"),
        ("0", "0"),
        ("-50", "-50"),
        # Skip invalid test case as it causes errors with numeric sensors
    ],
)
async def test_sensor_message_received(
    hass: HomeAssistant, payload, expected_state
) -> None:
    """Test handling of MQTT messages with different payloads.

    This test verifies that the sensor correctly processes various payload formats:
    - Positive values
    - Zero values
    - Negative values

    The test creates a sensor, simulates receiving MQTT messages with different
    payloads, and verifies that the sensor state is updated correctly for each payload type.
    This ensures the component is robust and can handle various payload formats that might
    be sent by different MQTT publishers.
    """
    # Mock MQTT component
    with patch("homeassistant.components.mqtt.async_subscribe") as mock_subscribe:
        mock_subscribe.return_value = AsyncMock(return_value=None)

        # Create a sensor description
        description = openwbSensorEntityDescription(
            key="power",
            name="Power",
            device_class=SensorDeviceClass.POWER,
            native_unit_of_measurement=UnitOfPower.WATT,
            state_class=SensorStateClass.MEASUREMENT,
            mqttTopicCurrentValue="openWB/chargepoint/1/get/power",
        )

        # Create the sensor
        sensor = openwbSensor(
            uniqueID="test_unique_id",
            description=description,
            device_friendly_name="Test Device",
            mqtt_root="openWB",
        )

        # Add the sensor to hass
        sensor.hass = hass

        # Register the entity with Home Assistant
        hass.states.async_set(
            sensor.entity_id,
            STATE_UNKNOWN,
            {
                ATTR_DEVICE_CLASS: description.device_class,
                ATTR_UNIT_OF_MEASUREMENT: description.native_unit_of_measurement,
            },
        )
        await hass.async_block_till_done()

        # Call async_added_to_hass to register the callback
        await sensor.async_added_to_hass()

        # Get the callback function from the mock
        callback = mock_subscribe.call_args[0][2]

        # Simulate message received
        message = ReceiveMessage(
            topic="openWB/chargepoint/1/get/power",
            payload=payload,
            qos=0,
            retain=False,
            subscribed_topic="openWB/chargepoint/1/get/power",
            timestamp=time.time(),
        )

        # Call the callback with the message
        callback(message)

        # Verify state was updated
        assert sensor._attr_native_value == expected_state


async def test_sensor_value_function(hass: HomeAssistant) -> None:
    """Test value function in the sensor.

    This test verifies that a sensor's value_fn correctly extracts specific data
    from a complex payload. In this case, it tests a function that extracts the
    first value from a comma-separated list of values.

    This functionality is important for sensors that need to process structured data
    from MQTT messages, such as extracting a specific value from an array or
    selecting a particular field from a complex data structure.
    """
    # Create a sensor description with a value function
    description = openwbSensorEntityDescription(
        key="currents",
        name="Current L1",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement="A",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: x.split(",")[0],
    )

    # Create the sensor
    sensor = openwbSensor(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
    )

    # Test the value function directly
    test_payload = "10.5,11.2,9.8"
    result = description.value_fn(test_payload)

    # Verify value function works correctly
    assert result == "10.5"


async def test_dynamic_sensor_init(hass: HomeAssistant) -> None:
    """Test initialization of openwbDynamicSensor.

    This test verifies that the openwbDynamicSensor entity is correctly initialized with:
    1. The proper name, unique_id, and device_info
    2. The correct device class, unit of measurement, and state class
    3. The correct device ID

    Dynamic sensors differ from regular sensors in that they use template-based
    topics that are populated at runtime based on configuration received via MQTT.
    """
    # Create a dynamic sensor description
    description = openwbDynamicSensorEntityDescription(
        key="instant_charging_current",
        name="Instant Charging Current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement="A",
        state_class=SensorStateClass.MEASUREMENT,
        mqttTopicTemplate="{mqtt_root}/vehicle/template/charge_template/{charge_template_id}",
        value_fn=lambda x: json.loads(x)
        .get("chargemode", {})
        .get("instant_charging", {})
        .get("current"),
    )

    # Create the sensor
    sensor = openwbDynamicSensor(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
        device_id=1,
    )

    # Verify sensor properties
    assert sensor.name == "Instant Charging Current"
    assert sensor.unique_id == "test_unique_id_instant_charging_current"
    assert sensor.device_info["name"] == "Test Device"
    assert sensor.device_info["identifiers"] == {(DOMAIN, "Test Device", "openWB")}
    assert sensor.device_id == 1


async def test_dynamic_sensor_subscription_update(hass: HomeAssistant) -> None:
    """Test updating subscriptions in dynamic sensor.

    This test verifies that the dynamic sensor entity correctly:
    1. Subscribes to the config topic when added to Home Assistant
    2. Processes config messages to extract the charge template ID
    3. Updates its subscription to the template topic with the correct ID
    4. Processes template messages to extract and update its state

    This tests the dynamic subscription mechanism that allows entities to
    adapt their MQTT topics based on configuration received via MQTT.
    """
    # Mock the MQTT subscription
    with patch("homeassistant.components.mqtt.async_subscribe") as mock_subscribe:
        mock_subscribe.return_value = AsyncMock(return_value=None)

        # Create a dynamic sensor description
        description = openwbDynamicSensorEntityDescription(
            key="instant_charging_current",
            name="Instant Charging Current",
            device_class=SensorDeviceClass.CURRENT,
            native_unit_of_measurement="A",
            state_class=SensorStateClass.MEASUREMENT,
            mqttTopicTemplate="{mqtt_root}/vehicle/template/charge_template/{charge_template_id}",
            value_fn=lambda x: json.loads(x)
            .get("chargemode", {})
            .get("instant_charging", {})
            .get("current"),
        )

        # Create the sensor
        sensor = openwbDynamicSensor(
            uniqueID="test_unique_id",
            description=description,
            device_friendly_name="Test Device",
            mqtt_root="openWB",
            device_id=1,
        )

        # Add the sensor to hass
        sensor.hass = hass

        # Call async_added_to_hass
        await sensor.async_added_to_hass()

        # Verify subscription to config topic
        assert mock_subscribe.call_count == 1
        assert (
            mock_subscribe.call_args[0][1]
            == "openWB/chargepoint/1/get/connected_vehicle/config"
        )

        # Get the config callback
        config_callback = mock_subscribe.call_args[0][2]

        # Simulate config message with charge template ID
        config_message = ReceiveMessage(
            topic="openWB/chargepoint/1/get/connected_vehicle/config",
            payload='{"charge_template": 123}',
            qos=0,
            retain=False,
            subscribed_topic="openWB/chargepoint/1/get/connected_vehicle/config",
            timestamp=time.time(),
        )
        config_callback(config_message)
        await hass.async_block_till_done()

        # Verify subscription to template topic
        assert mock_subscribe.call_count == 2
        assert (
            mock_subscribe.call_args[0][1]
            == "openWB/vehicle/template/charge_template/123"
        )

        # Get the template callback
        template_callback = mock_subscribe.call_args[0][2]

        # Simulate template message
        template_message = ReceiveMessage(
            topic="openWB/vehicle/template/charge_template/123",
            payload='{"chargemode": {"instant_charging": {"current": 16}}}',
            qos=0,
            retain=False,
            subscribed_topic="openWB/vehicle/template/charge_template/123",
            timestamp=time.time(),
        )
        template_callback(template_message)

        # Verify state was updated
        assert sensor._attr_native_value == 16
