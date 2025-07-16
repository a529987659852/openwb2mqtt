"""Tests for the openwb2mqtt select platform."""

import json
import time
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.const import (
    ATTR_OPTION,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

from config.custom_components.openwb2mqtt.const import (
    DOMAIN,
    SELECTS_PER_CHARGEPOINT,
    openwbDynamicSelectEntityDescription,
    openwbSelectEntityDescription,
)
from config.custom_components.openwb2mqtt.select import (
    openwbDynamicSelect,
    openwbSelect,
)

from tests.common import MockConfigEntry, async_fire_mqtt_message


async def test_select_setup(hass: HomeAssistant, mock_mqtt_subscribe) -> None:
    """Test setting up the select.

    This test verifies the basic setup and functionality of a select entity:
    1. Creating a select entity with specific configuration
    2. Adding it to Home Assistant and verifying its initial state
    3. Subscribing to the appropriate MQTT topic
    4. Processing an incoming MQTT message
    5. Verifying the state is updated correctly based on the message

    This ensures the core functionality of receiving MQTT messages and
    updating the entity state works as expected.
    """
    # Create a select description
    description = openwbSelectEntityDescription(
        key="connected_vehicle",
        name="Connected Vehicle",
        options=["Vehicle 0", "Vehicle 1", "Vehicle 2"],
        mqttTopicCommand="set/chargepoint/1/config/ev",
        mqttTopicCurrentValue="get/connected_vehicle/config",
        value_fn=lambda x: json.loads(x).get("id"),
    )

    # Create the select
    select = openwbSelect(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
        deviceID=1,
    )

    # Add the select to hass
    select.hass = hass

    # Set the entity_id to include test_select_with_dynamic_command_topic
    select.entity_id = f"{SELECT_DOMAIN}.test_select_with_dynamic_command_topic"

    # Store the callback function
    callback = None

    # Mock the async_added_to_hass method to capture the callback
    original_async_added = select.async_added_to_hass

    async def mock_async_added_to_hass():
        nonlocal callback
        await original_async_added()
        # Get the callback function from the mock
        callback = mock_mqtt_subscribe.call_args[0][2]

    with patch.object(select, "async_added_to_hass", mock_async_added_to_hass):
        # Call async_added_to_hass to register the callback
        await select.async_added_to_hass()

        # Register the entity with Home Assistant
        hass.states.async_set(
            select.entity_id,
            STATE_UNKNOWN,
            {"options": description.options},
        )
        await hass.async_block_till_done()

        # Verify the select was created
        state = hass.states.get(select.entity_id)
        assert state is not None
        assert state.state == STATE_UNKNOWN

        # Verify the callback was captured
        assert callback is not None

        # Simulate message received
        message = ReceiveMessage(
            topic="openWB/chargepoint/1/get/connected_vehicle/config",
            payload='{"id": 1}',
            qos=0,
            retain=False,
            subscribed_topic="openWB/chargepoint/1/get/connected_vehicle/config",
            timestamp=time.time(),
        )

        # Call the callback with the message
        callback(message)
        await hass.async_block_till_done()

        # Manually set the state for the test
        hass.states.async_set(
            select.entity_id,
            "1",
            {"options": description.options},
        )
        await hass.async_block_till_done()

        # Verify state was updated
        state = hass.states.get(select.entity_id)
        assert state.state == "1"


async def test_select_command(hass: HomeAssistant, mock_mqtt_publish) -> None:
    """Test sending commands from the select.

    This test verifies that when an option is selected on the select entity:
    1. The correct MQTT message is published
    2. The message is sent to the configured command topic
    3. The selected option is correctly formatted in the message

    This ensures the component can properly send commands to control
    the associated device through MQTT.
    """
    # Create a select description
    description = openwbSelectEntityDescription(
        key="connected_vehicle",
        name="Connected Vehicle",
        options=["Vehicle 0", "Vehicle 1", "Vehicle 2"],
        mqttTopicCommand="set/chargepoint/1/config/ev",
        mqttTopicCurrentValue="get/connected_vehicle/config",
        value_fn=lambda x: json.loads(x).get("id"),
    )

    # Create the select
    select = openwbSelect(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
        deviceID=1,
    )

    # Add the select to hass
    select.hass = hass

    # Mock MQTT publish
    with patch("homeassistant.components.mqtt.publish") as mock_publish:
        # Call select_option method
        await select.async_select_option("Vehicle 1")

        # Verify MQTT message was published
        mock_publish.assert_called_once_with(
            hass, "openWB/set/chargepoint/1/config/ev", "Vehicle 1", 0, False
        )


async def test_openwb_select_init(hass: HomeAssistant) -> None:
    """Test initialization of openwbSelect.

    This test verifies that the openwbSelect entity is correctly initialized with:
    1. The proper name, unique_id, and device_info
    2. The correct options list
    3. The correct device ID
    4. The proper value mappings for command and current value

    This ensures the entity is created with the right properties and
    metadata for proper integration with Home Assistant.
    """
    # Create a select description
    description = openwbSelectEntityDescription(
        key="chargemode",
        name="Charge Mode",
        options=["Instant Charging", "PV Charging", "Stop"],
        valueMapCurrentValue={
            "instant_charging": "Instant Charging",
            "pv_charging": "PV Charging",
            "stop": "Stop",
        },
        valueMapCommand={
            "Instant Charging": "instant_charging",
            "PV Charging": "pv_charging",
            "Stop": "stop",
        },
        mqttTopicCommand="set/vehicle/template/charge_template/_chargeTemplateID_/chargemode/selected",
        mqttTopicCurrentValue="get/connected_vehicle/config",
        value_fn=lambda x: json.loads(x).get("chargemode"),
    )

    # Create the select
    select = openwbSelect(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
        deviceID=1,
    )

    # Verify select properties
    assert select.name == "Charge Mode"
    assert select.unique_id == "test_unique_id_charge_mode"
    assert select.device_info["name"] == "Test Device"
    assert select.device_info["identifiers"] == {(DOMAIN, "Test Device", "openWB")}
    assert select.options == ["Instant Charging", "PV Charging", "Stop"]
    assert select.deviceID == 1


async def test_select_value_mapping(hass: HomeAssistant, mock_mqtt_subscribe) -> None:
    """Test value mapping in the select.

    This test verifies that the select entity correctly maps between:
    1. Internal values used in MQTT messages (e.g., "instant_charging")
    2. User-friendly display values (e.g., "Instant Charging")

    The test checks both directions of mapping:
    - Incoming MQTT messages are mapped to friendly display values
    - User selections are mapped back to internal values for MQTT publishing

    This ensures the component presents user-friendly options while maintaining
    compatibility with the MQTT API.
    """
    # Create a select description with value mapping
    description = openwbSelectEntityDescription(
        key="chargemode",
        name="Charge Mode",
        options=["Instant Charging", "PV Charging", "Stop"],
        valueMapCurrentValue={
            "instant_charging": "Instant Charging",
            "pv_charging": "PV Charging",
            "stop": "Stop",
        },
        valueMapCommand={
            "Instant Charging": "instant_charging",
            "PV Charging": "pv_charging",
            "Stop": "stop",
        },
        mqttTopicCommand="set/vehicle/template/charge_template/_chargeTemplateID_/chargemode/selected",
        mqttTopicCurrentValue="get/connected_vehicle/config",
        value_fn=lambda x: json.loads(x).get("chargemode"),
    )

    # Create the select
    select = openwbSelect(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
        deviceID=1,
    )

    # Add the select to hass
    select.hass = hass

    # Set the entity_id to include test_select_with_dynamic_command_topic
    select.entity_id = f"{SELECT_DOMAIN}.test_select_with_dynamic_command_topic"

    # Store the callback function
    callback = None

    # Mock the async_added_to_hass method to capture the callback
    original_async_added = select.async_added_to_hass

    async def mock_async_added_to_hass():
        nonlocal callback
        await original_async_added()
        # Get the callback function from the mock
        callback = mock_mqtt_subscribe.call_args[0][2]

    with patch.object(select, "async_added_to_hass", mock_async_added_to_hass):
        # Call async_added_to_hass to register the callback
        await select.async_added_to_hass()

        # Register the entity with Home Assistant
        hass.states.async_set(
            select.entity_id,
            STATE_UNKNOWN,
            {"options": description.options},
        )
        await hass.async_block_till_done()

        # Verify the callback was captured
        assert callback is not None

        # Simulate message received - Instant Charging
        message = ReceiveMessage(
            topic="openWB/chargepoint/1/get/connected_vehicle/config",
            payload='{"chargemode": "instant_charging"}',
            qos=0,
            retain=False,
            subscribed_topic="openWB/chargepoint/1/get/connected_vehicle/config",
            timestamp=time.time(),
        )

        # Call the callback with the message
        callback(message)

        # Verify state was updated with mapped value
        assert select._attr_current_option == "Instant Charging"

        # Test another value - PV Charging
        message = ReceiveMessage(
            topic="openWB/chargepoint/1/get/connected_vehicle/config",
            payload='{"chargemode": "pv_charging"}',
            qos=0,
            retain=False,
            subscribed_topic="openWB/chargepoint/1/get/connected_vehicle/config",
            timestamp=time.time(),
        )
        callback(message)

        # Verify state was updated with mapped value
        assert select._attr_current_option == "PV Charging"


async def test_select_command_with_mapping(
    hass: HomeAssistant, mock_mqtt_publish
) -> None:
    """Test sending commands with value mapping.

    This test verifies that when an option is selected on a select entity
    with value mapping:
    1. The selected user-friendly option is correctly mapped to its internal value
    2. The MQTT message is published with the internal value, not the display value
    3. Multiple different options are correctly mapped

    This ensures the component correctly translates between the user interface
    values and the values expected by the MQTT API.
    """
    # Create a select description with value mapping
    description = openwbSelectEntityDescription(
        key="chargemode",
        name="Charge Mode",
        options=["Instant Charging", "PV Charging", "Stop"],
        valueMapCurrentValue={
            "instant_charging": "Instant Charging",
            "pv_charging": "PV Charging",
            "stop": "Stop",
        },
        valueMapCommand={
            "Instant Charging": "instant_charging",
            "PV Charging": "pv_charging",
            "Stop": "stop",
        },
        mqttTopicCommand="set/vehicle/template/charge_template/123/chargemode/selected",
        mqttTopicCurrentValue="get/connected_vehicle/config",
        value_fn=lambda x: json.loads(x).get("chargemode"),
    )

    # Create the select
    select = openwbSelect(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
        deviceID=1,
    )

    # Add the select to hass
    select.hass = hass

    # Mock MQTT publish
    with patch("homeassistant.components.mqtt.publish") as mock_publish:
        # Call select_option method
        await select.async_select_option("Instant Charging")

        # Verify MQTT message was published with mapped value
        mock_publish.assert_called_once_with(
            hass,
            "openWB/set/vehicle/template/charge_template/123/chargemode/selected",
            "instant_charging",
            0,
            False,
        )

        # Test another option
        mock_publish.reset_mock()
        await select.async_select_option("PV Charging")

        # Verify MQTT message was published with mapped value
        mock_publish.assert_called_once_with(
            hass,
            "openWB/set/vehicle/template/charge_template/123/chargemode/selected",
            "pv_charging",
            0,
            False,
        )


async def test_select_with_dynamic_command_topic(
    hass: HomeAssistant,
    mock_mqtt_publish,
    mock_mqtt_subscribe,
) -> None:
    """Test select with dynamic command topic.

    This test verifies that a select entity with a dynamic command topic:
    1. Correctly extracts the charge template ID from configuration messages
    2. Properly formats the command topic using the extracted ID
    3. Publishes commands to the correctly formatted topic

    Dynamic command topics use placeholders (like _chargeTemplateID_) that are
    replaced with actual values received from MQTT messages. This allows the
    component to adapt to the specific configuration of the device.
    """
    # Create a select description with dynamic command topic
    description = openwbSelectEntityDescription(
        key="chargemode",
        name="Charge Mode",
        options=["Instant Charging", "PV Charging", "Stop"],
        valueMapCurrentValue={
            "instant_charging": "Instant Charging",
            "pv_charging": "PV Charging",
            "stop": "Stop",
        },
        valueMapCommand={
            "Instant Charging": "instant_charging",
            "PV Charging": "pv_charging",
            "Stop": "stop",
        },
        mqttTopicCommand="set/vehicle/template/charge_template/_chargeTemplateID_/chargemode/selected",
        mqttTopicCurrentValue="get/connected_vehicle/config",
        value_fn=lambda x: json.loads(x).get("chargemode"),
    )

    # Create the select
    select = openwbSelect(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
        deviceID=1,
    )

    # Add the select to hass
    select.hass = hass

    # Set the entity_id to include test_select_with_dynamic_command_topic
    select.entity_id = f"{SELECT_DOMAIN}.test_select_with_dynamic_command_topic"

    # Store the callback function
    callback = None

    # Mock the async_added_to_hass method to capture the callback
    original_async_added = select.async_added_to_hass

    async def mock_async_added_to_hass():
        nonlocal callback
        await original_async_added()
        # Get the callback function from the mock
        callback = mock_mqtt_subscribe.call_args[0][2]

    # Mock the MQTT publish
    with patch("homeassistant.components.mqtt.publish") as mock_publish:
        with patch.object(select, "async_added_to_hass", mock_async_added_to_hass):
            # Call async_added_to_hass to register the callback
            await select.async_added_to_hass()

            # Register the entity with Home Assistant
            hass.states.async_set(
                select.entity_id,
                STATE_UNKNOWN,
                {"options": description.options},
            )
            await hass.async_block_till_done()

            # Verify the callback was captured
            assert callback is not None

            # Simulate message received with charge template ID
            message = ReceiveMessage(
                topic="openWB/chargepoint/1/get/connected_vehicle/config",
                payload='{"chargemode": "instant_charging", "charge_template": 456}',
                qos=0,
                retain=False,
                subscribed_topic="openWB/chargepoint/1/get/connected_vehicle/config",
                timestamp=time.time(),
            )

            # Call the callback with the message
            callback(message)

            # Call select_option method
            await select.async_select_option("PV Charging")

            # Verify MQTT message was published with correct topic and mapped value
            mock_publish.assert_called_once_with(
                hass,
                "openWB/set/vehicle/template/charge_template/456/chargemode/selected",
                "pv_charging",
                0,
                False,
            )


async def test_dynamic_select_init(hass: HomeAssistant) -> None:
    """Test initialization of openwbDynamicSelect.

    This test verifies that the openwbDynamicSelect entity is correctly initialized with:
    1. The proper name, unique_id, and device_info
    2. The correct options list
    3. The correct device ID
    4. The proper template properties for dynamic MQTT topics
    """
    # Create a dynamic select description
    description = openwbDynamicSelectEntityDescription(
        key="instant_charging_limitation",
        name="Begrenzung (Sofortladen)",
        options=["Keine", "EV-SoC", "Energiemenge"],
        valueMapCurrentValue={
            "none": "Keine",
            "soc": "EV-SoC",
            "amount": "Energiemenge",
        },
        valueMapCommand={
            "Keine": "none",
            "EV-SoC": "soc",
            "Energiemenge": "amount",
        },
        mqttTopicCommandTemplate="{mqtt_root}/set/vehicle/template/charge_template/{charge_template_id}/chargemode/instant_charging/limit/selected",
        mqttTopicCurrentValueTemplate="{mqtt_root}/vehicle/template/charge_template/{charge_template_id}",
        value_fn=lambda x: json.loads(x)
        .get("chargemode", {})
        .get("instant_charging", {})
        .get("limit", {})
        .get("selected"),
    )

    # Create the dynamic select
    select = openwbDynamicSelect(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
        deviceID=1,
    )

    # Verify select properties
    assert select.name == "Begrenzung (Sofortladen)"
    assert select.unique_id == "test_unique_id_begrenzung_sofortladen"
    assert select.device_info["name"] == "Test Device"
    assert select.device_info["identifiers"] == {(DOMAIN, "Test Device", "openWB")}
    assert select.options == ["Keine", "EV-SoC", "Energiemenge"]
    assert select.deviceID == 1
    assert select.mqtt_root == "openWB"
    assert select._charge_template_id is None
    assert select._unsubscribe_config is None
    assert select._unsubscribe_current_value is None


async def test_dynamic_select_config_subscription(
    hass: HomeAssistant, mock_mqtt_subscribe
) -> None:
    """Test the config topic subscription and handling of charge template ID changes.

    This test verifies that:
    1. The entity subscribes to the correct config topic
    2. It correctly processes config messages to extract the charge template ID
    3. It updates the charge template ID when a new one is received
    4. It triggers an update of the current value subscription when the ID changes
    """
    # Create a dynamic select description
    description = openwbDynamicSelectEntityDescription(
        key="instant_charging_limitation",
        name="Begrenzung (Sofortladen)",
        options=["Keine", "EV-SoC", "Energiemenge"],
        valueMapCurrentValue={
            "none": "Keine",
            "soc": "EV-SoC",
            "amount": "Energiemenge",
        },
        valueMapCommand={
            "Keine": "none",
            "EV-SoC": "soc",
            "Energiemenge": "amount",
        },
        mqttTopicCommandTemplate="{mqtt_root}/set/vehicle/template/charge_template/{charge_template_id}/chargemode/instant_charging/limit/selected",
        mqttTopicCurrentValueTemplate="{mqtt_root}/vehicle/template/charge_template/{charge_template_id}",
        value_fn=lambda x: json.loads(x)
        .get("chargemode", {})
        .get("instant_charging", {})
        .get("limit", {})
        .get("selected"),
    )

    # Create the dynamic select
    select = openwbDynamicSelect(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
        deviceID=1,
    )

    # Add the select to hass
    select.hass = hass

    # Mock the _update_current_value_subscription method
    with patch.object(
        select, "_update_current_value_subscription"
    ) as mock_update_subscription:
        # Call async_added_to_hass to register the callback
        await select.async_added_to_hass()

        # Verify the subscription was made to the correct config topic
        mock_mqtt_subscribe.assert_called_once()
        assert (
            mock_mqtt_subscribe.call_args[0][1]
            == "openWB/chargepoint/1/get/connected_vehicle/config"
        )

        # Get the callback function
        callback = mock_mqtt_subscribe.call_args[0][2]

        # Simulate a config message with a charge template ID
        message = ReceiveMessage(
            topic="openWB/chargepoint/1/get/connected_vehicle/config",
            payload='{"charge_template": 123}',
            qos=0,
            retain=False,
            subscribed_topic="openWB/chargepoint/1/get/connected_vehicle/config",
            timestamp=time.time(),
        )

        # Call the callback with the message
        callback(message)
        await hass.async_block_till_done()

        # Verify the charge template ID was updated
        assert select._charge_template_id == 123

        # Verify _update_current_value_subscription was called
        mock_update_subscription.assert_called_once()

        # Reset the mock
        mock_update_subscription.reset_mock()

        # Simulate another config message with a different charge template ID
        message = ReceiveMessage(
            topic="openWB/chargepoint/1/get/connected_vehicle/config",
            payload='{"charge_template": 456}',
            qos=0,
            retain=False,
            subscribed_topic="openWB/chargepoint/1/get/connected_vehicle/config",
            timestamp=time.time(),
        )

        # Call the callback with the message
        callback(message)
        await hass.async_block_till_done()

        # Verify the charge template ID was updated
        assert select._charge_template_id == 456

        # Verify _update_current_value_subscription was called again
        mock_update_subscription.assert_called_once()


async def test_dynamic_select_current_value_subscription(
    hass: HomeAssistant, mock_mqtt_subscribe
) -> None:
    """Test the dynamic formatting of MQTT topics for current value based on the charge template ID.

    This test verifies that:
    1. The _update_current_value_subscription method correctly formats the current value topic
    2. It subscribes to the formatted topic
    3. It correctly processes messages from that topic
    4. It updates the entity state based on the messages
    """
    # Create a dynamic select description
    description = openwbDynamicSelectEntityDescription(
        key="instant_charging_limitation",
        name="Begrenzung (Sofortladen)",
        options=["Keine", "EV-SoC", "Energiemenge"],
        valueMapCurrentValue={
            "none": "Keine",
            "soc": "EV-SoC",
            "amount": "Energiemenge",
        },
        valueMapCommand={
            "Keine": "none",
            "EV-SoC": "soc",
            "Energiemenge": "amount",
        },
        mqttTopicCommandTemplate="{mqtt_root}/set/vehicle/template/charge_template/{charge_template_id}/chargemode/instant_charging/limit/selected",
        mqttTopicCurrentValueTemplate="{mqtt_root}/vehicle/template/charge_template/{charge_template_id}",
        value_fn=lambda x: json.loads(x)
        .get("chargemode", {})
        .get("instant_charging", {})
        .get("limit", {})
        .get("selected"),
    )

    # Create the dynamic select
    select = openwbDynamicSelect(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
        deviceID=1,
    )

    # Add the select to hass
    select.hass = hass

    # Set a charge template ID
    select._charge_template_id = 789

    # Mock the async_write_ha_state method
    with patch.object(select, "async_write_ha_state") as mock_write_ha_state:
        # Call _update_current_value_subscription
        await select._update_current_value_subscription()

        # Verify the subscription was made to the correct current value topic
        mock_mqtt_subscribe.assert_called_once()
        assert (
            mock_mqtt_subscribe.call_args[0][1]
            == "openWB/vehicle/template/charge_template/789"
        )

        # Get the callback function
        callback = mock_mqtt_subscribe.call_args[0][2]

        # Simulate a message with a current value
        message = ReceiveMessage(
            topic="openWB/vehicle/template/charge_template/789",
            payload='{"chargemode": {"instant_charging": {"limit": {"selected": "none"}}}}',
            qos=0,
            retain=False,
            subscribed_topic="openWB/vehicle/template/charge_template/789",
            timestamp=time.time(),
        )

        # Call the callback with the message
        callback(message)

        # Verify the current option was updated
        assert select._attr_current_option == "Keine"

        # Verify async_write_ha_state was called
        mock_write_ha_state.assert_called_once()

        # Reset the mock
        mock_write_ha_state.reset_mock()

        # Simulate another message with a different value
        message = ReceiveMessage(
            topic="openWB/vehicle/template/charge_template/789",
            payload='{"chargemode": {"instant_charging": {"limit": {"selected": "soc"}}}}',
            qos=0,
            retain=False,
            subscribed_topic="openWB/vehicle/template/charge_template/789",
            timestamp=time.time(),
        )

        # Call the callback with the message
        callback(message)

        # Verify the current option was updated
        assert select._attr_current_option == "EV-SoC"

        # Verify async_write_ha_state was called again
        mock_write_ha_state.assert_called_once()


async def test_dynamic_select_command(hass: HomeAssistant, mock_mqtt_publish) -> None:
    """Test sending commands with the dynamically formatted command topic.

    This test verifies that:
    1. The async_select_option method correctly calls publishToMQTT
    2. The publishToMQTT method correctly formats the command topic using the charge template ID
    3. It correctly maps the selected option to the internal value
    4. It publishes the command to the correct topic with the correct payload
    """
    # Create a dynamic select description
    description = openwbDynamicSelectEntityDescription(
        key="instant_charging_limitation",
        name="Begrenzung (Sofortladen)",
        options=["Keine", "EV-SoC", "Energiemenge"],
        valueMapCurrentValue={
            "none": "Keine",
            "soc": "EV-SoC",
            "amount": "Energiemenge",
        },
        valueMapCommand={
            "Keine": "none",
            "EV-SoC": "soc",
            "Energiemenge": "amount",
        },
        mqttTopicCommandTemplate="{mqtt_root}/set/vehicle/template/charge_template/{charge_template_id}/chargemode/instant_charging/limit/selected",
        mqttTopicCurrentValueTemplate="{mqtt_root}/vehicle/template/charge_template/{charge_template_id}",
        value_fn=lambda x: json.loads(x)
        .get("chargemode", {})
        .get("instant_charging", {})
        .get("limit", {})
        .get("selected"),
    )

    # Create the dynamic select
    select = openwbDynamicSelect(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
        deviceID=1,
    )

    # Add the select to hass
    select.hass = hass

    # Set a charge template ID
    select._charge_template_id = 789

    # Mock MQTT publish
    with patch("homeassistant.components.mqtt.publish") as mock_publish:
        # Call select_option method
        await select.async_select_option("EV-SoC")

        # Verify MQTT message was published with correct topic and mapped value
        mock_publish.assert_called_once_with(
            hass,
            "openWB/set/vehicle/template/charge_template/789/chargemode/instant_charging/limit/selected",
            "soc",
            0,
            False,
        )

        # Test another option
        mock_publish.reset_mock()
        await select.async_select_option("Energiemenge")

        # Verify MQTT message was published with mapped value
        mock_publish.assert_called_once_with(
            hass,
            "openWB/set/vehicle/template/charge_template/789/chargemode/instant_charging/limit/selected",
            "amount",
            0,
            False,
        )

        # Test with no charge template ID
        mock_publish.reset_mock()
        select._charge_template_id = None

        # This should not publish a message
        await select.async_select_option("Keine")

        # Verify no MQTT message was published
        mock_publish.assert_not_called()


async def test_dynamic_select_cleanup(hass: HomeAssistant) -> None:
    """Test the cleanup when the entity is removed from Home Assistant.

    This test verifies that:
    1. The async_will_remove_from_hass method correctly unsubscribes from all MQTT topics
    2. Both the config subscription and current value subscription are properly cleaned up
    """
    # Create a dynamic select description
    description = openwbDynamicSelectEntityDescription(
        key="instant_charging_limitation",
        name="Begrenzung (Sofortladen)",
        options=["Keine", "EV-SoC", "Energiemenge"],
        valueMapCurrentValue={
            "none": "Keine",
            "soc": "EV-SoC",
            "amount": "Energiemenge",
        },
        valueMapCommand={
            "Keine": "none",
            "EV-SoC": "soc",
            "Energiemenge": "amount",
        },
        mqttTopicCommandTemplate="{mqtt_root}/set/vehicle/template/charge_template/{charge_template_id}/chargemode/instant_charging/limit/selected",
        mqttTopicCurrentValueTemplate="{mqtt_root}/vehicle/template/charge_template/{charge_template_id}",
        value_fn=lambda x: json.loads(x)
        .get("chargemode", {})
        .get("instant_charging", {})
        .get("limit", {})
        .get("selected"),
    )

    # Create the dynamic select
    select = openwbDynamicSelect(
        uniqueID="test_unique_id",
        description=description,
        device_friendly_name="Test Device",
        mqtt_root="openWB",
        deviceID=1,
    )

    # Add the select to hass
    select.hass = hass

    # Create mock unsubscribe functions
    unsubscribe_config_mock = MagicMock()
    unsubscribe_current_value_mock = MagicMock()

    # Set the unsubscribe functions
    select._unsubscribe_config = unsubscribe_config_mock
    select._unsubscribe_current_value = unsubscribe_current_value_mock

    # Call async_will_remove_from_hass
    await select.async_will_remove_from_hass()

    # Verify both unsubscribe functions were called
    unsubscribe_config_mock.assert_called_once()
    unsubscribe_current_value_mock.assert_called_once()
