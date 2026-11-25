"""Snapshot tests for all entities created via MQTT.

These tests record unique_id, entity_id, name, unit, device class and state
of every entity. Later refactorings must keep these snapshots unchanged.
"""

from typing import Any

from custom_components.openwb2mqtt.const import (
    COMM_METHOD_MQTT,
    COMMUNICATION_METHOD,
    CONF_WALLBOX_POWER,
    DEVICEID,
    DEVICETYPE,
    DOMAIN,
    MQTT_ROOT_TOPIC,
)
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_mqtt_message
from pytest_homeassistant.typing import MqttMockHAClient
from syrupy.assertion import SnapshotAssertion

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .snapshot_helpers import (
    FROZEN_TIME,
    async_enable_all_entities,
    collect_entities,
    load_fixture_json,
)

# device type -> device id
DEVICES: dict[str, int] = {
    "chargepoint": 6,
    "counter": 0,
    "bat": 1,
    "pv": 5,
    "consumer": 0,
}


def build_mqtt_entry(device_type: str, device_id: int) -> MockConfigEntry:
    """Build a config entry like the config flow does for MQTT."""
    data: dict[str, Any] = {
        COMMUNICATION_METHOD: COMM_METHOD_MQTT,
        MQTT_ROOT_TOPIC: "openWB",
        DEVICETYPE: device_type,
        DEVICEID: device_id,
    }
    if device_type == "chargepoint":
        data[CONF_WALLBOX_POWER] = "11"
    title = f"openWB-{device_type}-{device_id}"
    return MockConfigEntry(domain=DOMAIN, title=title, unique_id=title, data=data)


@pytest.fixture
def expected_lingering_timers() -> bool:
    """Allow the periodic timer that the MQTT mock starts.

    The test plugin only allows it for tests below tests/components/.
    """
    return True


@pytest.mark.parametrize("device_type", list(DEVICES))
async def test_mqtt_entities_snapshot(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    entity_registry: er.EntityRegistry,
    freezer: FrozenDateTimeFactory,
    snapshot: SnapshotAssertion,
    device_type: str,
) -> None:
    """Set up one MQTT device, send its messages and compare the snapshot."""
    freezer.move_to(FROZEN_TIME)
    entry = build_mqtt_entry(device_type, DEVICES[device_type])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    disabled_by_default = await async_enable_all_entities(hass, entity_registry, entry)

    # Messages are sent one by one, in the order of the fixture file.
    # The first chargepoint message tells which charge template is used,
    # so the entities can subscribe to the template topic. The vehicle name
    # is sent before the connected vehicle. Otherwise the vehicle select
    # shows "unknown", because its option is renamed after it was chosen.
    for topic, payload in load_fixture_json(f"mqtt_{device_type}.json"):
        async_fire_mqtt_message(hass, topic, payload)
        await hass.async_block_till_done()

    entities = collect_entities(hass, entity_registry, entry, disabled_by_default)
    assert entities == snapshot
