"""Check the commands that the integration sends to the openWB.

One row per writable entity (number, select, lock) of chargepoint 6 and
battery 1. The expected values are the ones the live write tests sent to a
real openWB on 2026-11-25 (HTTP and MQTT).

The test calls the real async_send_command of the coordinators. It uses a
fake HTTP client and a fake MQTT publish, so it needs no running Home
Assistant and no wallbox.
"""

import asyncio
from typing import Any
from unittest.mock import patch

from custom_components.openwb2mqtt.common import is_supported
from custom_components.openwb2mqtt.const import (
    COMM_METHOD_HTTP,
    COMM_METHOD_MQTT,
    LOCKS_BY_DEVICE_TYPE,
    NUMBERS_BY_DEVICE_TYPE,
    SELECTS_BY_DEVICE_TYPE,
    OpenWBEntityDescription,
    OpenWBSelectEntityDescription,
)
from custom_components.openwb2mqtt.coordinator import (
    OpenWBHttpCoordinator,
    OpenWBMqttCoordinator,
)
import pytest

# Device ID of each device type in the tables below
DEVICE_IDS = {"chargepoint": 6, "bat": 1}
MQTT_ROOT = "openWB"

# (device type, description key, value set in HA, expected HTTP form data)
# For a select the value is the option, for a lock True (lock) or False (unlock).
HTTP_CASES: list[tuple[str, str, Any, dict[str, str]]] = [
    ("chargepoint", "manual_soc", 43.0, {"manual_soc": "43", "chargepoint_nr": "6"}),
    (
        "chargepoint",
        "instant_charging_current_control",
        10.0,
        {"chargecurrent": "10", "chargepoint_nr": "6"},
    ),
    (
        "chargepoint",
        "pv_charging_min_current_control",
        6.0,
        {"minimal_permanent_current": "6", "chargepoint_nr": "6"},
    ),
    (
        "chargepoint",
        "instant_charging_energy_limit_control",
        16.0,
        {"instant_charging_amount": "16", "chargepoint_nr": "6"},
    ),
    (
        "chargepoint",
        "instant_charging_soc_limit_control",
        55.0,
        {"instant_charging_soc": "55", "chargepoint_nr": "6"},
    ),
    # EUR/kWh in HA, ct/kWh in the command
    (
        "chargepoint",
        "price_based_charging_max_price",
        0.36,
        {"max_price_eco": "36", "chargepoint_nr": "6"},
    ),
    (
        "chargepoint",
        "minimal_pv_soc",
        5.0,
        {"minimal_pv_soc": "5", "chargepoint_nr": "6"},
    ),
    (
        "chargepoint",
        "pv_charging_limit_soc",
        55.0,
        {"pv_charging_soc": "55", "chargepoint_nr": "6"},
    ),
    (
        "chargepoint",
        "pv_charging_limit_amount",
        26.0,
        {"pv_charging_amount": "26", "chargepoint_nr": "6"},
    ),
    (
        "chargepoint",
        "instant_charging_limitation",
        "SoC",
        {"instant_charging_limit": "soc", "chargepoint_nr": "6"},
    ),
    (
        "chargepoint",
        "chargemode",
        "Instant Charging",
        {"set_chargemode": "instant", "chargepoint_nr": "6"},
    ),
    # The vehicle select sends the id of the chosen vehicle (from the options)
    (
        "chargepoint",
        "connected_vehicle",
        "0",
        {"vehicle": "0", "chargepoint_nr": "6"},
    ),
    (
        "chargepoint",
        "pv_charging_limit",
        "Energiemenge",
        {"pv_charging_limit": "amount", "chargepoint_nr": "6"},
    ),
    (
        "chargepoint",
        "manual_lock",
        True,
        {"chargepoint_lock": "1", "chargepoint_nr": "6"},
    ),
    # Battery commands have no chargepoint_nr
    ("bat", "bat_power_reserve", 1600.0, {"bat_power_reserve": "1600"}),
    ("bat", "bat_mode", "Speicher", {"bat_mode": "bat_mode"}),
]

# (device type, description key, value set in HA, expected topic, expected payload)
MQTT_CASES: list[tuple[str, str, Any, str, str]] = [
    (
        "chargepoint",
        "instant_charging_current_control",
        10.0,
        "openWB/simpleAPI/set/chargepoint/6/chargecurrent",
        "10",
    ),
    (
        "chargepoint",
        "pv_charging_min_current_control",
        6.0,
        "openWB/simpleAPI/set/chargepoint/6/minimal_permanent_current",
        "6",
    ),
    # The 6 limit setters have no chargepoint ID (they act on the lowest ID)
    (
        "chargepoint",
        "instant_charging_energy_limit_control",
        16.0,
        "openWB/simpleAPI/set/instant_charging_limit_amount",
        "16",
    ),
    (
        "chargepoint",
        "instant_charging_soc_limit_control",
        55.0,
        "openWB/simpleAPI/set/instant_charging_limit_soc",
        "55",
    ),
    (
        "chargepoint",
        "price_based_charging_max_price",
        0.36,
        "openWB/simpleAPI/set/chargepoint/6/max_price_eco",
        "36",
    ),
    (
        "chargepoint",
        "minimal_pv_soc",
        5.0,
        "openWB/simpleAPI/set/chargepoint/6/minimal_pv_soc",
        "5",
    ),
    (
        "chargepoint",
        "pv_charging_limit_soc",
        55.0,
        "openWB/simpleAPI/set/pv_charging_limit_soc",
        "55",
    ),
    (
        "chargepoint",
        "pv_charging_limit_amount",
        26.0,
        "openWB/simpleAPI/set/pv_charging_limit_amount",
        "26",
    ),
    (
        "chargepoint",
        "instant_charging_limitation",
        "SoC",
        "openWB/simpleAPI/set/instant_charging_limit",
        "soc",
    ),
    (
        "chargepoint",
        "chargemode",
        "Instant Charging",
        "openWB/simpleAPI/set/chargepoint/6/chargemode",
        "instant",
    ),
    (
        "chargepoint",
        "pv_charging_limit",
        "Energiemenge",
        "openWB/simpleAPI/set/pv_charging_limit",
        "amount",
    ),
    (
        "chargepoint",
        "manual_lock",
        True,
        "openWB/simpleAPI/set/chargepoint/6/chargepoint_lock",
        "true",
    ),
    (
        "bat",
        "bat_power_reserve",
        1600.0,
        "openWB/simpleAPI/set/bat_power_reserve",
        "1600",
    ),
    ("bat", "bat_mode", "Speicher", "openWB/simpleAPI/set/bat_mode", "bat_mode"),
]

# (price in EUR/kWh, expected payload in ct/kWh); same conversion on both transports
PRICE_CASES: list[tuple[float, str]] = [
    (0.36, "36"),
    (0.29, "29"),  # 0.29 * 100 = 28.999999999999996 must still send 29
    (-0.05, "-5"),
    (0.0, "0"),
]


class FakeHttpClient:
    """Stands in for the HTTP API client and stores the sent form data."""

    def __init__(self) -> None:
        """Start with nothing sent."""
        self.sent: list[dict[str, str]] = []

    async def async_set_data(self, data: dict[str, str]) -> dict[str, Any]:
        """Store the form data and answer like a successful openWB."""
        self.sent.append(data)
        return {"success": True}


class FakeMqttPublish:
    """Stands in for mqtt.async_publish and stores the published messages."""

    def __init__(self) -> None:
        """Start with nothing published."""
        self.sent: list[tuple[str, str]] = []

    async def __call__(
        self, hass: Any, topic: str, payload: str, **kwargs: Any
    ) -> None:
        """Store topic and payload."""
        self.sent.append((topic, payload))


def make_http_coordinator(device_type: str) -> OpenWBHttpCoordinator:
    """Return an HTTP coordinator without Home Assistant behind it.

    __new__ skips the Home Assistant setup in __init__; the test sets only
    the attributes that async_send_command uses.
    """
    coordinator = OpenWBHttpCoordinator.__new__(OpenWBHttpCoordinator)
    coordinator.device_type = device_type
    coordinator.device_id = DEVICE_IDS[device_type]
    coordinator.client = FakeHttpClient()
    coordinator.data = {}
    # The optimistic update after a command is not part of this test
    coordinator.async_set_updated_data = lambda data: None
    return coordinator


def make_mqtt_coordinator(device_type: str) -> OpenWBMqttCoordinator:
    """Return an MQTT coordinator without Home Assistant behind it."""
    coordinator = OpenWBMqttCoordinator.__new__(OpenWBMqttCoordinator)
    coordinator.device_type = device_type
    coordinator.device_id = DEVICE_IDS[device_type]
    coordinator.mqtt_root = MQTT_ROOT
    coordinator.hass = None
    coordinator.data = {}
    return coordinator


def writable_descriptions(device_type: str) -> list[OpenWBEntityDescription]:
    """Return the number, select and lock descriptions of a device type."""
    descriptions: list[OpenWBEntityDescription] = []
    descriptions.extend(NUMBERS_BY_DEVICE_TYPE[device_type])
    descriptions.extend(SELECTS_BY_DEVICE_TYPE[device_type])
    descriptions.extend(LOCKS_BY_DEVICE_TYPE[device_type])
    return descriptions


def find_description(device_type: str, key: str) -> OpenWBEntityDescription:
    """Return the writable description with this key."""
    for description in writable_descriptions(device_type):
        if description.key == key:
            return description
    raise AssertionError(f"No writable description {key} for {device_type}")


def value_to_send(description: OpenWBEntityDescription, value: Any) -> Any:
    """Return the value the entity hands to the coordinator.

    A select sends the API value of the chosen option (command_map), except
    the vehicle select, which already gets the vehicle id here. Numbers and
    locks send their value as it is.
    """
    if (
        isinstance(description, OpenWBSelectEntityDescription)
        and description.command_map is not None
    ):
        return description.command_map[value]
    return value


def send_http(device_type: str, key: str, value: Any) -> list[dict[str, str]]:
    """Send one command over HTTP and return what the client got."""
    coordinator = make_http_coordinator(device_type)
    description = find_description(device_type, key)
    command_value = value_to_send(description, value)
    asyncio.run(coordinator.async_send_command(description, command_value, value))
    return coordinator.client.sent


def send_mqtt(device_type: str, key: str, value: Any) -> list[tuple[str, str]]:
    """Send one command over MQTT and return what was published."""
    coordinator = make_mqtt_coordinator(device_type)
    description = find_description(device_type, key)
    command_value = value_to_send(description, value)
    publish = FakeMqttPublish()
    with patch(
        "custom_components.openwb2mqtt.coordinator.mqtt.async_publish", new=publish
    ):
        asyncio.run(coordinator.async_send_command(description, command_value, value))
    return publish.sent


@pytest.mark.parametrize(("device_type", "key", "value", "expected"), HTTP_CASES)
def test_http_command(
    device_type: str, key: str, value: Any, expected: dict[str, str]
) -> None:
    """The HTTP form data matches what the openWB accepted live."""
    assert send_http(device_type, key, value) == [expected]


@pytest.mark.parametrize(
    ("device_type", "key", "value", "topic", "payload"), MQTT_CASES
)
def test_mqtt_command(
    device_type: str, key: str, value: Any, topic: str, payload: str
) -> None:
    """The MQTT topic and payload match what the openWB accepted live."""
    assert send_mqtt(device_type, key, value) == [(topic, payload)]


@pytest.mark.parametrize(("price", "payload"), PRICE_CASES)
def test_max_price_in_cent(price: float, payload: str) -> None:
    """The max price is sent in whole ct/kWh, without float noise."""
    key = "price_based_charging_max_price"
    http_sent = send_http("chargepoint", key, price)
    mqtt_sent = send_mqtt("chargepoint", key, price)
    assert http_sent[0]["max_price_eco"] == payload
    assert mqtt_sent[0][1] == payload


def test_lock_and_unlock_payloads() -> None:
    """Unlock sends 0 over HTTP and false over MQTT."""
    assert send_http("chargepoint", "manual_lock", False)[0]["chargepoint_lock"] == "0"
    assert send_mqtt("chargepoint", "manual_lock", False)[0][1] == "false"


@pytest.mark.parametrize(
    ("transport", "cases"),
    [(COMM_METHOD_HTTP, HTTP_CASES), (COMM_METHOD_MQTT, MQTT_CASES)],
)
def test_every_writable_entity_has_a_row(transport: str, cases: list[tuple]) -> None:
    """A new number, select or lock must get a row in the table above."""
    expected_rows: list[tuple[str, str]] = []
    for device_type in DEVICE_IDS:
        for description in writable_descriptions(device_type):
            if not is_supported(description, transport):
                continue
            expected_rows.append((device_type, description.key))
    rows = [(case[0], case[1]) for case in cases]
    assert sorted(rows) == sorted(expected_rows)
