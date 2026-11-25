"""Check that the entity IDs stay the same as on the legacy main branch.

Users upgrade from main to this version. Their dashboards and automations use
the entity IDs, so a renamed description would break them. This test is plain
Python: it needs no running Home Assistant.

legacy_entity_ids.json holds the entity IDs that main created for four config
entries (one per device type), once over HTTP and once over MQTT. In main the
unique_id was always the part of the entity ID after the dot.
"""

import json
from pathlib import Path

from custom_components.openwb2mqtt.common import is_supported
from custom_components.openwb2mqtt.const import (
    BINARY_SENSORS_BY_DEVICE_TYPE,
    COMM_METHOD_HTTP,
    COMM_METHOD_MQTT,
    LOCKS_BY_DEVICE_TYPE,
    NUMBERS_BY_DEVICE_TYPE,
    SELECTS_BY_DEVICE_TYPE,
    SENSORS_BY_DEVICE_TYPE,
    SUPPORTED_DEVICE_TYPES,
    OpenWBEntityDescription,
)
import pytest

from homeassistant.util import slugify

LEGACY_FILE = Path(__file__).parent / "legacy_entity_ids.json"

# Transport name in legacy_entity_ids.json -> communication method of the entry
TRANSPORTS = {
    "HTTP": COMM_METHOD_HTTP,
    "MQTT": COMM_METHOD_MQTT,
}

# Title of the legacy config entry -> device type
LEGACY_TITLES = {
    "openWB-chargepoint-6": "chargepoint",
    "openWB-counter-0": "counter",
    "openWB-bat-1": "bat",
    "openWB-pv-5": "pv",
}

# Platform -> descriptions per device type
DESCRIPTIONS_BY_PLATFORM: dict[str, dict[str, list[OpenWBEntityDescription]]] = {
    "sensor": SENSORS_BY_DEVICE_TYPE,
    "binary_sensor": BINARY_SENSORS_BY_DEVICE_TYPE,
    "number": NUMBERS_BY_DEVICE_TYPE,
    "select": SELECTS_BY_DEVICE_TYPE,
    "lock": LOCKS_BY_DEVICE_TYPE,
}

# Legacy entities that are removed on purpose. They are not created any more
# and show as unavailable after the upgrade (REFACTOR_PLAN.md §0.1 no. 3).
REMOVED_IDS: dict[str, list[str]] = {
    "HTTP": [
        # Only "Fahrzeug-ID" is kept (REFACTOR_PLAN.md §0.1 no. 8)
        "sensor.openwb_chargepoint_6_vehicle_id",
        # HTTP has no vehicle SoC timestamp; it shows the openWB Pro SoC values instead
        "sensor.openwb_chargepoint_6_soc_datenaktualisierung",
    ],
    "MQTT": [
        # The simpleAPI MQTT has no manual SoC set topic
        "number.openwb_chargepoint_6_aktueller_soc_manuelles_soc_modul",
        # The simpleAPI MQTT has no set topic for the connected vehicle
        "select.openwb_chargepoint_6_angeschlossenes_fahrzeug",
        # The simpleAPI MQTT has no charge template name (HTTP keeps it)
        "sensor.openwb_chargepoint_6_lade_profil",
        # The simpleAPI MQTT has no read topic for it; the number with the same
        # name shows the last sent value instead
        "sensor.openwb_chargepoint_6_soll_ladestrom_sofortladen",
        # Only "Fahrzeug-ID" is kept (REFACTOR_PLAN.md §0.1 no. 8)
        "sensor.openwb_chargepoint_6_vehicle_id",
    ],
}


def make_entity_id(platform: str, id_prefix: str, name: str) -> str:
    """Return the entity ID the way common.OpenWBEntity builds it."""
    return f"{platform}.{slugify(f'{id_prefix}_{name}')}"


def created_entity_ids(device_type: str, transport: str, id_prefix: str) -> list[str]:
    """Return the entity IDs of all entities that one config entry creates."""
    entity_ids: list[str] = []
    for platform, descriptions_by_type in DESCRIPTIONS_BY_PLATFORM.items():
        for description in descriptions_by_type[device_type]:
            if not is_supported(description, transport):
                continue
            name = str(description.name)
            entity_ids.append(make_entity_id(platform, id_prefix, name))
    return entity_ids


def load_legacy_ids() -> dict[str, dict[str, list[str]]]:
    """Return transport -> title -> legacy entity IDs."""
    with LEGACY_FILE.open(encoding="utf-8") as file:
        return json.load(file)


LEGACY_CASES = [
    (transport, title) for transport in TRANSPORTS for title in LEGACY_TITLES
]


def test_legacy_file_has_expected_size() -> None:
    """The frozen list has the number of entities main created."""
    legacy = load_legacy_ids()
    http_count = sum(len(ids) for ids in legacy["HTTP"].values())
    mqtt_count = sum(len(ids) for ids in legacy["MQTT"].values())
    assert http_count == 84
    assert mqtt_count == 86


@pytest.mark.parametrize(("transport", "title"), LEGACY_CASES)
def test_legacy_entity_ids_are_kept(transport: str, title: str) -> None:
    """Every legacy entity ID is still created, except the removed ones."""
    legacy_ids = load_legacy_ids()[transport][title]
    device_type = LEGACY_TITLES[title]
    created = created_entity_ids(device_type, TRANSPORTS[transport], title)

    missing = [
        entity_id
        for entity_id in legacy_ids
        if entity_id not in created and entity_id not in REMOVED_IDS[transport]
    ]
    assert missing == []


@pytest.mark.parametrize("transport", list(TRANSPORTS))
def test_removed_ids_are_really_gone(transport: str) -> None:
    """The removed IDs exist in the legacy list and are no longer created."""
    legacy = load_legacy_ids()[transport]
    created = created_entity_ids(
        "chargepoint", TRANSPORTS[transport], "openWB-chargepoint-6"
    )
    for entity_id in REMOVED_IDS[transport]:
        assert entity_id in legacy["openWB-chargepoint-6"]
        assert entity_id not in created


@pytest.mark.parametrize("transport", list(TRANSPORTS))
@pytest.mark.parametrize("device_type", SUPPORTED_DEVICE_TYPES)
@pytest.mark.parametrize("platform", list(DESCRIPTIONS_BY_PLATFORM))
def test_no_duplicate_entity_ids(
    transport: str, device_type: str, platform: str
) -> None:
    """Two descriptions of one platform never produce the same entity ID."""
    seen: list[str] = []
    duplicates: list[str] = []
    for description in DESCRIPTIONS_BY_PLATFORM[platform][device_type]:
        if not is_supported(description, TRANSPORTS[transport]):
            continue
        entity_id = make_entity_id(
            platform, f"openWB-{device_type}-1", str(description.name)
        )
        if entity_id in seen:
            duplicates.append(entity_id)
        seen.append(entity_id)
    assert duplicates == []
