"""Snapshot tests for all entities created via the HTTP API.

These tests record unique_id, entity_id, name, unit, device class and state
of every entity. Later refactorings must keep these snapshots unchanged.
"""

from typing import Any

from custom_components.openwb2mqtt.const import (
    API_PREFIX,
    API_URL,
    COMM_METHOD_HTTP,
    COMMUNICATION_METHOD,
    CONF_VEHICLES,
    CONF_WALLBOX_POWER,
    DEVICEID,
    DEVICETYPE,
    DOMAIN,
)
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker
from syrupy.assertion import SnapshotAssertion

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .snapshot_helpers import (
    FROZEN_TIME,
    async_enable_all_entities,
    collect_entities,
    load_fixture_json,
)

API_BASE_URL = "http://192.168.0.68/openWB/simpleAPI/simpleapi.php"

# device type -> (device id, query string the API client requests)
DEVICES: dict[str, tuple[int, str]] = {
    "chargepoint": (6, "?get_chargepoint_all=6"),
    "counter": (0, "?get_counter=0"),
    "bat": (1, "?get_battery=1"),
    "pv": (5, "?get_pv=5"),
    "consumer": (0, "?get_consumer=0"),
}


def build_http_entry(device_type: str, device_id: int) -> MockConfigEntry:
    """Build a config entry like the config flow does for the HTTP API."""
    data: dict[str, Any] = {
        COMMUNICATION_METHOD: COMM_METHOD_HTTP,
        API_PREFIX: "openWB",
        API_URL: API_BASE_URL,
        DEVICETYPE: device_type,
        DEVICEID: device_id,
    }
    if device_type == "chargepoint":
        data[CONF_WALLBOX_POWER] = "11"
        data[CONF_VEHICLES] = {"0": "Standard-Fahrzeug"}
    title = f"openWB-{device_type}-{device_id}"
    return MockConfigEntry(domain=DOMAIN, title=title, unique_id=title, data=data)


@pytest.mark.parametrize("device_type", list(DEVICES))
async def test_http_entities_snapshot(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    snapshot: SnapshotAssertion,
    device_type: str,
) -> None:
    """Set up one HTTP device and compare all its entities with the snapshot."""
    freezer.move_to(FROZEN_TIME)
    device_id, endpoint = DEVICES[device_type]
    aioclient_mock.get(
        f"{API_BASE_URL}{endpoint}",
        json=load_fixture_json(f"http_{device_type}.json"),
    )

    entry = build_http_entry(device_type, device_id)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    disabled_by_default = await async_enable_all_entities(hass, entity_registry, entry)

    assert aioclient_mock.call_count >= 1
    entities = collect_entities(hass, entity_registry, entry, disabled_by_default)
    assert entities == snapshot
