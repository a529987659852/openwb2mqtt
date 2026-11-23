"""Helpers for the entity snapshot tests."""

import json
from pathlib import Path
from typing import Any

from pytest_homeassistant.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Fixed point in time for all snapshot tests, so no state depends on "now".
FROZEN_TIME = "2026-11-20 12:00:00+00:00"


def load_fixture_json(file_name: str) -> Any:
    """Load a JSON file from the fixtures folder."""
    with (FIXTURES_DIR / file_name).open(encoding="utf-8") as file:
        return json.load(file)


async def async_enable_all_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    config_entry: MockConfigEntry,
) -> dict[str, er.RegistryEntryDisabler | None]:
    """Enable all entities that are disabled by default and reload the entry.

    Disabled entities have no state. Enabling them lets the snapshot show a
    state for every entity. The returned dict remembers which entities were
    disabled by default, so this information is still part of the snapshot.
    """
    disabled_by_default: dict[str, er.RegistryEntryDisabler | None] = {}
    entries = er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
    for entry in entries:
        disabled_by_default[entry.entity_id] = entry.disabled_by
        if entry.disabled_by is not None:
            entity_registry.async_update_entity(entry.entity_id, disabled_by=None)

    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    return disabled_by_default


def collect_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    config_entry: MockConfigEntry,
    disabled_by_default: dict[str, er.RegistryEntryDisabler | None],
) -> list[dict[str, Any]]:
    """Return the important facts of every entity of a config entry.

    The list is sorted by entity_id, so the snapshot does not depend on the
    order in which the platforms were set up.
    """
    entries = er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
    result: list[dict[str, Any]] = []
    for entry in sorted(entries, key=lambda item: item.entity_id):
        state = hass.states.get(entry.entity_id)
        result.append(
            {
                "entity_id": entry.entity_id,
                "unique_id": entry.unique_id,
                "original_name": entry.original_name,
                "unit_of_measurement": entry.unit_of_measurement,
                "device_class": entry.device_class or entry.original_device_class,
                "disabled_by_default": disabled_by_default.get(entry.entity_id),
                "state": state.state if state is not None else None,
            }
        )
    return result
