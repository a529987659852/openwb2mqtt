"""Tests for the openwb2mqtt common module."""

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from config.custom_components.openwb2mqtt.common import (
    OpenWBBaseEntity,
    async_setup_binary_sensors,
    async_setup_entities,
    async_setup_numbers,
    async_setup_selects,
    async_setup_sensors,
)
from config.custom_components.openwb2mqtt.const import (
    DEVICEID,
    DEVICETYPE,
    DOMAIN,
    MANUFACTURER,
    MODEL,
    MQTT_ROOT_TOPIC,
)


def test_openwb_base_entity() -> None:
    """Test the OpenWBBaseEntity class.

    This test verifies that the OpenWBBaseEntity base class correctly:
    1. Initializes with the provided device_friendly_name and mqtt_root
    2. Creates a proper device_info dictionary with the correct:
       - Name
       - Identifiers (using DOMAIN, device name, and MQTT root)
       - Manufacturer and model information

    The OpenWBBaseEntity is the foundation for all entity types in the integration,
    providing common properties and methods used by sensors, binary sensors, etc.
    """
    # Create an instance of the base entity
    entity = OpenWBBaseEntity(
        device_friendly_name="Test Device",
        mqtt_root="openWB",
    )

    # Verify the properties
    assert entity.device_friendly_name == "Test Device"
    assert entity.mqtt_root == "openWB"

    # Verify the device_info property
    device_info = entity.device_info
    # DeviceInfo is a TypedDict, so we can't use isinstance
    assert device_info["name"] == "Test Device"
    assert device_info["identifiers"] == {(DOMAIN, "Test Device", "openWB")}
    assert device_info["manufacturer"] == MANUFACTURER
    assert device_info["model"] == MODEL


async def test_async_setup_entities(hass: HomeAssistant) -> None:
    """Test the async_setup_entities function.

    This test verifies that the async_setup_entities function correctly:
    1. Creates entities from the provided entity descriptions
    2. Configures each entity with the correct parameters from the config entry
    3. Adds the created entities to Home Assistant

    The async_setup_entities function is a core utility that handles the creation
    and registration of entities for all platforms in the integration, making it
    a critical component for proper integration setup.
    """
    # Create a mock config entry
    config = MagicMock()
    config.unique_id = "test_unique_id"
    config.data = {
        MQTT_ROOT_TOPIC: "openWB",
        DEVICETYPE: "chargepoint",
        DEVICEID: 1,
    }

    # Create mock entity descriptions
    entity_descriptions = [
        MagicMock(key="test_key"),
        MagicMock(key="test_key2"),
    ]

    # Create a mock entity class
    entity_class = MagicMock()

    # Create a mock async_add_entities function
    async_add_entities = MagicMock()

    # Define a topic template
    topic_template = "{mqtt_root}/{device_type}/{device_id}/{key}"

    # Mock the copy.deepcopy function to return the same objects
    with patch(
        "config.custom_components.openwb2mqtt.common.copy.deepcopy",
        side_effect=lambda x: x,
    ):
        # Call the function
        await async_setup_entities(
            hass,
            config,
            async_add_entities,
            entity_descriptions,
            entity_class,
            topic_template,
            "Test Device",
        )

    # Verify the entity class was called with the correct arguments
    assert entity_class.call_count == 2
    entity_class.assert_any_call(
        uniqueID="test_unique_id",
        description=entity_descriptions[0],
        device_friendly_name="Test Device 1",
        mqtt_root="openWB",
    )
    entity_class.assert_any_call(
        uniqueID="test_unique_id",
        description=entity_descriptions[1],
        device_friendly_name="Test Device 1",
        mqtt_root="openWB",
    )

    # Verify async_add_entities was called with the correct arguments
    async_add_entities.assert_called_once()
    assert len(async_add_entities.call_args[0][0]) == 2


async def test_async_setup_entities_with_additional_processing(
    hass: HomeAssistant,
) -> None:
    """Test the async_setup_entities function with additional processing.

    This test verifies that when setting up entities with an additional processing
    function:
    1. The additional_processing function is called with the correct arguments
    2. The entity class is instantiated with the processed description
    3. The entities are correctly added to Home Assistant

    The additional processing function allows for dynamic modification of entity
    descriptions before entity creation, which is used for template substitution
    and other customizations.
    """
    # Create a mock config entry
    config = MagicMock()
    config.unique_id = "test_unique_id"
    config.data = {
        MQTT_ROOT_TOPIC: "openWB",
        DEVICETYPE: "chargepoint",
        DEVICEID: 1,
    }

    # Create mock entity descriptions
    entity_descriptions = [
        MagicMock(key="test_key"),
    ]

    # Create a mock entity class
    entity_class = MagicMock()

    # Create a mock async_add_entities function
    async_add_entities = MagicMock()

    # Define a topic template
    topic_template = "{mqtt_root}/{device_type}/{device_id}/{key}"

    # Define an additional processing function
    additional_processing = MagicMock()

    # Mock the copy.deepcopy function to return the same objects
    with patch(
        "config.custom_components.openwb2mqtt.common.copy.deepcopy",
        side_effect=lambda x: x,
    ):
        # Call the function
        await async_setup_entities(
            hass,
            config,
            async_add_entities,
            entity_descriptions,
            entity_class,
            topic_template,
            "Test Device",
            additional_processing,
        )

    # Verify the additional processing function was called with the correct arguments
    additional_processing.assert_called_once_with(
        entity_descriptions[0], "chargepoint", 1, "openWB"
    )

    # Verify the entity class was called with the correct arguments
    entity_class.assert_called_once_with(
        uniqueID="test_unique_id",
        description=entity_descriptions[0],
        device_friendly_name="Test Device 1",
        mqtt_root="openWB",
    )

    # Verify async_add_entities was called with the correct arguments
    async_add_entities.assert_called_once()
    assert len(async_add_entities.call_args[0][0]) == 1


@pytest.mark.parametrize(
    "setup_function,entity_class_import_path",
    [
        (
            async_setup_sensors,
            "config.custom_components.openwb2mqtt.sensor.openwbSensor",
        ),
        (
            async_setup_binary_sensors,
            "config.custom_components.openwb2mqtt.binary_sensor.openwbBinarySensor",
        ),
    ],
)
async def test_async_setup_specific_entities(
    hass: HomeAssistant, setup_function, entity_class_import_path
) -> None:
    """Test the specific entity setup functions.

    This parameterized test verifies that each specialized entity setup function:
    1. Correctly imports the appropriate entity class
    2. Creates entities with the proper configuration
    3. Passes the correct parameters to the entity constructor

    The test covers multiple entity types (sensors and binary sensors) to ensure
    consistent behavior across different platforms. Each platform has its own
    setup function that follows the same pattern but uses platform-specific
    entity classes.
    """
    # Create a mock config entry
    config = MagicMock()
    config.unique_id = "test_unique_id"
    config.data = {
        MQTT_ROOT_TOPIC: "openWB",
        DEVICETYPE: "chargepoint",
        DEVICEID: 1,
    }

    # Create mock entity descriptions
    entity_descriptions = [
        MagicMock(key="test_key"),
    ]

    # Create a mock async_add_entities function
    async_add_entities = MagicMock()

    # Define a topic template
    topic_template = "{mqtt_root}/{device_type}/{device_id}/{key}"

    # Mock the entity class import
    with patch(entity_class_import_path) as mock_entity_class:
        # Call the function
        await setup_function(
            hass,
            config,
            async_add_entities,
            entity_descriptions,
            topic_template,
            "Test Device",
        )

        # Verify the entity class was called with the correct arguments
        mock_entity_class.assert_called_once_with(
            uniqueID="test_unique_id",
            description=entity_descriptions[0],
            device_friendly_name="Test Device 1",
            mqtt_root="openWB",
        )


async def test_async_setup_selects(hass: HomeAssistant) -> None:
    """Test the async_setup_selects function.

    This test verifies that the async_setup_selects function correctly:
    1. Imports the openwbSelect class
    2. Processes entity descriptions with the additional_processing function
    3. Creates select entities with the correct parameters
    4. Passes the deviceID parameter to the entity constructor

    Select entities require the deviceID parameter for dynamic topic construction,
    so this test ensures that parameter is correctly passed through the setup process.
    """
    # Create a mock config entry
    config = MagicMock()
    config.unique_id = "test_unique_id"
    config.data = {
        MQTT_ROOT_TOPIC: "openWB",
        DEVICETYPE: "chargepoint",
        DEVICEID: 1,
    }

    # Create mock entity descriptions
    select_descriptions = [
        MagicMock(key="test_key"),
    ]

    # Create a mock async_add_entities function
    async_add_entities = MagicMock()

    # Define a topic template
    topic_template = "{mqtt_root}/{device_type}/{device_id}/{key}"

    # Define an additional processing function
    additional_processing = MagicMock()

    # Mock the entity class import and copy.deepcopy
    with (
        patch(
            "config.custom_components.openwb2mqtt.select.openwbSelect"
        ) as mock_entity_class,
        patch(
            "config.custom_components.openwb2mqtt.common.copy.deepcopy",
            side_effect=lambda x: x,
        ),
    ):
        # Call the function
        await async_setup_selects(
            hass,
            config,
            async_add_entities,
            select_descriptions,
            topic_template,
            "Test Device",
            additional_processing,
        )

        # Verify the additional processing function was called with the correct arguments
        additional_processing.assert_called_once_with(
            select_descriptions[0], "chargepoint", 1, "openWB"
        )

        # Verify the entity class was called with the correct arguments
        mock_entity_class.assert_called_once_with(
            uniqueID="test_unique_id",
            description=select_descriptions[0],
            device_friendly_name="Test Device 1",
            mqtt_root="openWB",
            deviceID=1,
        )


async def test_async_setup_numbers(hass: HomeAssistant) -> None:
    """Test the async_setup_numbers function.

    This test verifies that the async_setup_numbers function correctly:
    1. Imports the openWBNumber class
    2. Processes entity descriptions with the additional_processing function
    3. Creates number entities with the correct parameters
    4. Passes the deviceID parameter to the entity constructor

    Number entities require the deviceID parameter for dynamic topic construction,
    so this test ensures that parameter is correctly passed through the setup process.
    """
    # Create a mock config entry
    config = MagicMock()
    config.unique_id = "test_unique_id"
    config.data = {
        MQTT_ROOT_TOPIC: "openWB",
        DEVICETYPE: "chargepoint",
        DEVICEID: 1,
    }

    # Create mock entity descriptions
    number_descriptions = [
        MagicMock(key="test_key"),
    ]

    # Create a mock async_add_entities function
    async_add_entities = MagicMock()

    # Define a topic template
    topic_template = "{mqtt_root}/{device_type}/{device_id}/{key}"

    # Define an additional processing function
    additional_processing = MagicMock()

    # Mock the entity class import and copy.deepcopy
    with (
        patch(
            "config.custom_components.openwb2mqtt.number.openWBNumber"
        ) as mock_entity_class,
        patch(
            "config.custom_components.openwb2mqtt.common.copy.deepcopy",
            side_effect=lambda x: x,
        ),
    ):
        # Call the function
        await async_setup_numbers(
            hass,
            config,
            async_add_entities,
            number_descriptions,
            topic_template,
            "Test Device",
            additional_processing,
        )

        # Verify the additional processing function was called with the correct arguments
        additional_processing.assert_called_once_with(
            number_descriptions[0], "chargepoint", 1, "openWB"
        )

        # Verify the entity class was called with the correct arguments
        mock_entity_class.assert_called_once_with(
            uniqueID="test_unique_id",
            description=number_descriptions[0],
            device_friendly_name="Test Device 1",
            mqtt_root="openWB",
            deviceID=1,
        )
