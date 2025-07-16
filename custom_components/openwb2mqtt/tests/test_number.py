"""Tests for the openwb2mqtt number platform."""

import json
import time
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.components.number import (
    DOMAIN as NUMBER_DOMAIN,
    NumberMode,
)
from homeassistant.const import (
    ATTR_MODE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

from config.custom_components.openwb2mqtt.const import (
    DOMAIN,
    NUMBERS_PER_CHARGEPOINT,
    openWBNumberEntityDescription,
    openwbDynamicNumberEntityDescription,
)
from config.custom_components.openwb2mqtt.number import (
    openWBNumber,
    openwbDynamicNumber,
)

from tests.common import MockConfigEntry, async_fire_mqtt_message


async def test_number_setup(hass: HomeAssistant, mock_mqtt_subscribe) -> None:
    """Test setting up the number.

    This test verifies the basic setup and functionality of a number entity:
    1. Creating a number entity with specific configuration
    2. Adding it to Home Assistant and verifying its initial state
    3. Subscribing to the appropriate MQTT topic
    4. Processing an incoming MQTT message
    5. Verifying the state is updated correctly based on the message

    This ensures the core functionality of receiving MQTT messages and
    updating the entity state works as expected.
    """
    # Create a number description
    description = openWBNumberEntityDescription(
        key="max_current",
        name="Test Number",
        mqttTopicCommand="set/chargepoint/1/max_current",
        mqttTopicCurrentValue="openWB/chargepoint/1/get/max_current",
        native_min_value=6,
        native_max_value=32,
        native_step=1,
    )

    # Create the number
    number = openWBNumber(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
        deviceID=1,
    )

    # Add the number to hass
    number.hass = hass

    # Fix the entity_id to use slugify (spaces to underscores)
    number.entity_id = f"{NUMBER_DOMAIN}.test_number"

    # Store the callback function
    callback = None

    # Mock the async_added_to_hass method to capture the callback
    original_async_added = number.async_added_to_hass

    async def mock_async_added_to_hass():
        nonlocal callback
        await original_async_added()
        # Get the callback function from the mock
        callback = mock_mqtt_subscribe.call_args[0][2]

    with patch.object(number, "async_added_to_hass", mock_async_added_to_hass):
        # Call async_added_to_hass to register the callback
        await number.async_added_to_hass()

        # Register the entity with Home Assistant
        hass.states.async_set(number.entity_id, STATE_UNKNOWN)
        await hass.async_block_till_done()

        # Verify the number was created
        state = hass.states.get(number.entity_id)
        assert state is not None
        assert state.state == STATE_UNKNOWN

        # Verify the callback was captured
        assert callback is not None

        # Simulate message received
        message = ReceiveMessage(
            topic="openWB/chargepoint/1/get/max_current",
            payload="16",
            qos=0,
            retain=False,
            subscribed_topic="openWB/chargepoint/1/get/max_current",
            timestamp=time.time(),
        )

        # Call the callback with the message
        callback(message)
        await hass.async_block_till_done()

        # Verify state was updated
        state = hass.states.get(number.entity_id)
        assert state.state == "16"


async def test_number_set_value(hass: HomeAssistant) -> None:
    """Test setting values for the number.

    This test verifies that when a value is set on the number entity:
    1. The correct MQTT message is published
    2. The message is sent to the configured command topic
    3. The value is correctly formatted in the message

    This ensures the component can properly send commands to control
    the associated device through MQTT.
    """
    # Create a number description
    description = openWBNumberEntityDescription(
        key="max_current",
        name="Test Number",
        mqttTopicCommand="openWB/set/chargepoint/1/max_current",
        mqttTopicCurrentValue="openWB/chargepoint/1/get/max_current",
        native_min_value=6,
        native_max_value=32,
        native_step=1,
    )

    # Create the number
    number = openWBNumber(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
        deviceID=1,
    )

    # Add the number to hass
    number.hass = hass

    # Fix the entity_id to use slugify (spaces to underscores)
    number.entity_id = f"{NUMBER_DOMAIN}.test_number"

    # Mock MQTT publish
    with patch("homeassistant.components.mqtt.publish") as mock_publish:
        # Call async_set_native_value method
        await number.async_set_native_value(20)

        # Verify MQTT message was published
        mock_publish.assert_called_once_with(
            hass, "openWB/set/chargepoint/1/max_current", "20"
        )


async def test_openwb_number_init(hass: HomeAssistant) -> None:
    """Test initialization of openWBNumber.

    This test verifies that the openWBNumber entity is correctly initialized with:
    1. The proper name, unique_id, and device_info
    2. The correct min, max, and step values
    3. The correct device ID

    This ensures the entity is created with the right properties and
    metadata for proper integration with Home Assistant.
    """
    # Create a number description
    description = openWBNumberEntityDescription(
        key="max_current",
        name="Max Current",
        mqttTopicCommand="set/chargepoint/_chargePointID_/max_current",
        mqttTopicCurrentValue="get/max_current",
        native_min_value=6,
        native_max_value=32,
        native_step=1,
    )

    # Create the number
    number = openWBNumber(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
        deviceID=1,
    )

    # Verify number properties
    assert number.name == "Max Current"
    assert (
        number.unique_id == "test_unique_id_max_current"
    )  # slugify converts spaces to underscores
    assert number.device_info["name"] == "Test Device"
    assert number.device_info["identifiers"] == {(DOMAIN, "Test Device", "openWB")}
    assert number.native_min_value == 6
    assert number.native_max_value == 32
    assert number.native_step == 1
    assert number.deviceID == 1


async def test_number_value_function(hass: HomeAssistant, mock_mqtt_subscribe) -> None:
    """Test value function in the number.

    This test verifies that a number entity correctly applies its value_fn to transform
    incoming MQTT payloads before updating its state. In this case, it tests a
    transformation that divides the incoming value by 10.

    The value_fn allows for converting between different formats or units used in
    the MQTT messages and what should be displayed in Home Assistant.
    """
    # Create a number description with a value function
    description = openWBNumberEntityDescription(
        key="max_current",
        name="Max Current",
        mqttTopicCommand="set/chargepoint/_chargePointID_/max_current",
        mqttTopicCurrentValue="openWB/chargepoint/1/get/max_current",
        native_min_value=6,
        native_max_value=32,
        native_step=1,
        value_fn=lambda x: float(x) / 10,
    )

    # Create the number
    number = openWBNumber(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
        deviceID=1,
    )

    # Add the number to hass
    number.hass = hass

    # Fix the entity_id to use slugify (spaces to underscores)
    number.entity_id = f"{NUMBER_DOMAIN}.test_unique_id_max_current"

    # Store the callback function
    callback = None

    # Mock the async_added_to_hass method to capture the callback
    original_async_added = number.async_added_to_hass

    async def mock_async_added_to_hass():
        nonlocal callback
        await original_async_added()
        # Get the callback function from the mock
        callback = mock_mqtt_subscribe.call_args[0][2]

    with patch.object(number, "async_added_to_hass", mock_async_added_to_hass):
        # Call async_added_to_hass to register the callback
        await number.async_added_to_hass()

        # Verify the callback was captured
        assert callback is not None

        # Simulate message received
        message = ReceiveMessage(
            topic="openWB/chargepoint/1/get/max_current",
            payload="160",
            qos=0,
            retain=False,
            subscribed_topic="openWB/chargepoint/1/get/max_current",
            timestamp=time.time(),
        )

        # Call the callback with the message
        callback(message)

        # Verify state was updated with transformed value
        assert number._attr_native_value == 16.0


async def test_number_publish_to_mqtt(hass: HomeAssistant) -> None:
    """Test publishing to MQTT from the number.

    This test verifies that the publishToMQTT method:
    1. Correctly formats the MQTT message with the provided value
    2. Publishes to the configured command topic
    3. Returns True on successful publishing

    This method is used internally by the entity to send commands
    to the MQTT broker when the user changes the number value.
    """
    # Mock the MQTT publish
    with patch("homeassistant.components.mqtt.publish") as mock_publish:
        # Create a number description
        description = openWBNumberEntityDescription(
            key="max_current",
            name="Max Current",
            mqttTopicCommand="set/chargepoint/_chargePointID_/max_current",
            mqttTopicCurrentValue="get/max_current",
            native_min_value=6,
            native_max_value=32,
            native_step=1,
        )

        # Create the number
        number = openWBNumber(
            uniqueID="test_unique_id",
            description=description,
            device_friendly_name="Test Device",
            mqtt_root="openWB",
            deviceID=1,
        )

        # Add the number to hass
        number.hass = hass

        # Call publishToMQTT method
        result = number.publishToMQTT(20)

        # Verify MQTT message was published
        assert result is True
        mock_publish.assert_called_once_with(
            hass, "set/chargepoint/_chargePointID_/max_current", "20"
        )


async def test_dynamic_number_init(hass: HomeAssistant) -> None:
    """Test initialization of openwbDynamicNumber.

    This test verifies that the openwbDynamicNumber entity is correctly initialized with:
    1. The proper name, unique_id, and device_info
    2. The correct min, max, and step values
    3. The correct device ID

    Dynamic numbers differ from regular numbers in that they use template-based
    topics that are populated at runtime based on configuration received via MQTT.
    """
    # Create a dynamic number description
    description = openwbDynamicNumberEntityDescription(
        key="pv_charging_current",
        name="PV Charging Current",
        mqttTopicTemplate="{mqtt_root}/vehicle/template/charge_template/{charge_template_id}",
        mqttTopicCommandTemplate="{mqtt_root}/set/vehicle/template/charge_template/{charge_template_id}/chargemode/pv_charging/current",
        native_min_value=6,
        native_max_value=32,
        native_step=1,
        value_fn=lambda x: json.loads(x)
        .get("chargemode", {})
        .get("pv_charging", {})
        .get("current"),
    )

    # Create the number
    number = openwbDynamicNumber(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
        device_id=1,
    )

    # Verify number properties
    assert number.name == "PV Charging Current"
    assert (
        number.unique_id == "test_unique_id_pv_charging_current"
    )  # slugify converts spaces to underscores
    assert number.device_info["name"] == "Test Device"
    assert number.device_info["identifiers"] == {(DOMAIN, "Test Device", "openWB")}
    assert number.native_min_value == 6
    assert number.native_max_value == 32
    assert number.native_step == 1
    assert number.device_id == 1


async def test_dynamic_number_subscription_update(hass: HomeAssistant) -> None:
    """Test updating subscriptions in dynamic number.

    This test verifies that the dynamic number entity correctly:
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

        # Create a dynamic number description
        description = openwbDynamicNumberEntityDescription(
            key="pv_charging_current",
            name="PV Charging Current",
            mqttTopicTemplate="{mqtt_root}/vehicle/template/charge_template/{charge_template_id}",
            mqttTopicCommandTemplate="{mqtt_root}/set/vehicle/template/charge_template/{charge_template_id}/chargemode/pv_charging/current",
            native_min_value=6,
            native_max_value=32,
            native_step=1,
            value_fn=lambda x: json.loads(x)
            .get("chargemode", {})
            .get("pv_charging", {})
            .get("current"),
        )

        # Create the number
        number = openwbDynamicNumber(
            uniqueID="test_unique_id",
            description=description,
            device_friendly_name="Test Device",
            mqtt_root="openWB",
            device_id=1,
        )

        # Add the number to hass
        number.hass = hass

        # Call async_added_to_hass
        await number.async_added_to_hass()

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
            payload='{"chargemode": {"pv_charging": {"current": 16}}}',
            qos=0,
            retain=False,
            subscribed_topic="openWB/vehicle/template/charge_template/123",
            timestamp=time.time(),
        )
        template_callback(template_message)

        # Verify state was updated
        assert number._attr_native_value == 16


async def test_dynamic_number_set_value(hass: HomeAssistant) -> None:
    """Test setting values for dynamic number.

    This test verifies that when a value is set on a dynamic number entity:
    1. The correct MQTT message is published
    2. The message is sent to the dynamically constructed command topic
       using the charge template ID
    3. The value is correctly formatted in the message (converted to integer)

    This ensures the component can properly send commands to control
    the associated device through MQTT using dynamically constructed topics.
    """
    # Mock the MQTT publish
    with patch("homeassistant.components.mqtt.publish") as mock_publish:
        # Create a dynamic number description
        description = openwbDynamicNumberEntityDescription(
            key="pv_charging_current",
            name="PV Charging Current",
            mqttTopicTemplate="{mqtt_root}/vehicle/template/charge_template/{charge_template_id}",
            mqttTopicCommandTemplate="{mqtt_root}/set/vehicle/template/charge_template/{charge_template_id}/chargemode/pv_charging/current",
            native_min_value=6,
            native_max_value=32,
            native_step=1,
            value_fn=lambda x: json.loads(x)
            .get("chargemode", {})
            .get("pv_charging", {})
            .get("current"),
        )

        # Create the number
        number = openwbDynamicNumber(
            uniqueID="test_unique_id",
            description=description,
            device_friendly_name="Test Device",
            mqtt_root="openWB",
            device_id=1,
        )

        # Add the number to hass
        number.hass = hass

        # Set charge template ID
        number._charge_template_id = 123

        # Call async_set_native_value method
        await number.async_set_native_value(20.5)

        # Verify MQTT message was published with integer value
        mock_publish.assert_called_once_with(
            hass,
            "openWB/set/vehicle/template/charge_template/123/chargemode/pv_charging/current",
            "20",
        )


async def test_dynamic_number_no_template_id(hass: HomeAssistant) -> None:
    """Test setting values for dynamic number without template ID.

    This test verifies that when attempting to set a value on a dynamic number
    entity that doesn't have a charge template ID set:
    1. No MQTT message is published
    2. The operation fails gracefully

    This is an important edge case to handle, as the dynamic number requires
    configuration data from MQTT before it can properly function, and this
    test ensures it behaves correctly before that data is received.
    """
    # Mock the MQTT publish
    with patch("homeassistant.components.mqtt.publish") as mock_publish:
        # Create a dynamic number description
        description = openwbDynamicNumberEntityDescription(
            key="pv_charging_current",
            name="PV Charging Current",
            mqttTopicTemplate="{mqtt_root}/vehicle/template/charge_template/{charge_template_id}",
            mqttTopicCommandTemplate="{mqtt_root}/set/vehicle/template/charge_template/{charge_template_id}/chargemode/pv_charging/current",
            native_min_value=6,
            native_max_value=32,
            native_step=1,
        )

        # Create the number
        number = openwbDynamicNumber(
            uniqueID="test_unique_id",
            description=description,
            device_friendly_name="Test Device",
            mqtt_root="openWB",
            device_id=1,
        )

        # Add the number to hass
        number.hass = hass

        # Call async_set_native_value method without setting charge template ID
        await number.async_set_native_value(20)

        # Verify MQTT message was not published
        mock_publish.assert_not_called()


async def test_number_with_special_soc_topic(hass: HomeAssistant) -> None:
    """Test number with special SoC topic handling.

    This test verifies that when a number entity is configured with a special SoC topic
    that includes a _vehicleID_ placeholder, the component correctly:
    1. Calls the get_assigned_vehicle method to retrieve the associated vehicle ID
    2. Replaces the placeholder in the topic with the actual vehicle ID
    3. Publishes the MQTT message to the correctly formatted topic

    The test mocks the get_assigned_vehicle method to return a specific vehicle ID (2)
    and then verifies that the MQTT message is published with the correct topic
    that includes this vehicle ID.
    """
    # Create a number description with a special SoC topic
    description = openWBNumberEntityDescription(
        key="aktueller_soc_manuelles_soc_modul",
        name="Aktueller SoC (Manuelles SoC Modul)",
        mqttTopicCommand="set/vehicle/_vehicleID_/soc_target",
        mqttTopicCurrentValue="get/soc_target",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
    )

    # Create the number
    number = openWBNumber(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
        deviceID=1,  # This is the chargepoint ID
    )

    # Add the number to hass
    number.hass = hass

    # Mock MQTT publish
    with patch("homeassistant.components.mqtt.publish") as mock_publish:
        # Mock the get_assigned_vehicle method to return a specific vehicle ID
        with patch.object(
            number, "get_assigned_vehicle", return_value="2"
        ) as mock_get_assigned_vehicle:
            # Call publishToMQTT method
            result = number.publishToMQTT(80)

            # Verify MQTT message was published with the correct vehicle ID
            assert result is True
            mock_publish.assert_called_once_with(hass, "set/vehicle/2/soc_target", "80")

            # Verify get_assigned_vehicle was called
            mock_get_assigned_vehicle.assert_called_once_with(hass, DOMAIN)
