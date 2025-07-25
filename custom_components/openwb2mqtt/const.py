"""The openwbmqtt component for controlling the openWB wallbox via home assistant / MQTT."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import datetime
import json
from zoneinfo import ZoneInfo

import voluptuous as vol

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntityDescription,
)
from homeassistant.components.number import NumberEntityDescription, NumberDeviceClass
from homeassistant.components.select import SelectEntityDescription
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.const import (
    PERCENTAGE,
    Platform,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfLength,
    UnitOfPower,
)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    # Platform.SWITCH,
]

# Global values
DOMAIN = "openwb2mqtt"
MQTT_ROOT_TOPIC = "mqttroot"
MQTT_ROOT_TOPIC_DEFAULT = "openWB"
DEVICETYPE = "DEVICETYPE"
DEVICEID = "DEVICEID"
MANUFACTURER = "openWB"
MODEL = "openWB"

# Data schema required by configuration flow
DATA_SCHEMA = vol.Schema(
    {
        vol.Required(MQTT_ROOT_TOPIC, default=MQTT_ROOT_TOPIC_DEFAULT): cv.string,
        vol.Required(DEVICETYPE): SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value="controller", label="Controller"),
                    SelectOptionDict(value="counter", label="Counter"),
                    SelectOptionDict(value="chargepoint", label="Chargepoint"),
                    SelectOptionDict(value="pv", label="PV Generator"),
                    SelectOptionDict(value="bat", label="Battery"),
                    SelectOptionDict(value="vehicle", label="Vehicle"),
                ],
                mode=SelectSelectorMode.DROPDOWN,
                translation_key="config_selector_devicetype",  # translation is maintained in translations/<lang>.json via this translation_key
            )
        ),
        vol.Required(DEVICEID): cv.positive_int,
    }
)


def _safeFloat(x: str) -> float | None:
    """Safely convert a string to float, handling None and conversion errors."""
    if x is None:
        return None
    try:
        return float(x)
    except (ValueError, TypeError):
        return None


def _safeJsonGet(x: str, key: str, default=None):
    """Safely extract a value from a JSON string.

    Handles None values and JSON decode errors.
    """
    if x is None:
        return default
    try:
        return json.loads(x).get(key, default)
    except json.JSONDecodeError:
        return default


def _safeNestedGet(x: str, *keys, default=None):
    """Safely extract a nested value from a JSON string.

    Handles None values, JSON decode errors, and missing keys.
    """
    if x is None:
        return default
    try:
        data = json.loads(x)
        for key in keys[:-1]:
            data = data.get(key, {})
        return data.get(keys[-1], default)
    except (json.JSONDecodeError, AttributeError):
        return default


def _safeStringOp(x: str, op_func) -> str:
    """Safely apply a string operation function.

    Handles None values and non-string inputs.
    """
    if x is None:
        return ""
    try:
        return op_func(x)
    except (AttributeError, TypeError):
        return ""


def _splitListToFloat(x: str, desiredValueIndex: int) -> float | None:
    """Extract float value from list at a specified index.

    Use this function if the MQTT topic contains a list of values, and you
    want to extract the i-th value from the string list.
    For example MQTT = [1.0, 2.0, 3.0] --> extract 3rd value --> sensor value = 3.0
    """
    if x is None:
        return None
    try:
        x = x.replace("[", "").replace("]", "")
        return float(x.split(",")[desiredValueIndex])
    except (IndexError, ValueError, AttributeError):
        return None


def _convertDateTime(x: str) -> datetime.datetime | None:
    """Convert string to datetime object.

    Assume that the local time zone is the same as the openWB time zone.
    """
    if x is None:
        return None
    try:
        a = json.loads(x).get("timestamp")
        if a is not None:
            try:
                dateTimeObject = datetime.datetime.strptime(a, "%m/%d/%Y, %H:%M:%S")
                return dateTimeObject.astimezone(tz=None)
            except ValueError:
                return None
    except json.JSONDecodeError:
        return None
    return None


def _umlauteEinfuegen(x: str) -> str:
    if x is None:
        return ""
    else:
        try:
            x = x.strip('"').strip(".")[0:255]
            if "u00fc" in x:
                x = x.replace("\\u00fc", "ü")
            if "u00dc" in x:
                x = x.replace("\\u00dc", "Ü")
            if "u00f6" in x:
                x = x.replace("\\u00f6", "ö")
            if "u00d6" in x:
                x = x.replace("\\u00d6", "Ö")
            if "u00e4" in x:
                x = x.replace("\\u00e4", "ä")
            if "u00c4" in x:
                x = x.replace("\\u00c4", "Ä")
            return x
        except AttributeError:
            return ""


def _splitJsonLastLiveValues(x: str, valueToExtract: str, factor: int) -> float | None:
    if x is None:
        return None
    try:
        x = json.loads(x).get(valueToExtract)
        if x is not None:
            try:
                floatValue = float(x)
                return round(factor * floatValue, 0)
            except ValueError:
                return None
        else:
            return None
    except json.JSONDecodeError:
        return None


def _extractTimestampFromJson(x: str, valueToExtract: str) -> datetime.datetime | None:
    if x is None:
        return None
    try:
        x = json.loads(x).get(valueToExtract)
        if x is not None:
            try:
                return datetime.datetime.fromtimestamp(int(x), tz=ZoneInfo("UTC"))
            except ValueError:
                return None
        else:
            return None
    except json.JSONDecodeError:
        return None


def _extractTimestamp(x: str) -> datetime.datetime | None:
    if x is None:
        return None
    try:
        return datetime.datetime.fromtimestamp(float(x), tz=ZoneInfo("UTC"))
    except (ValueError, TypeError):
        return None


# @dataclass
@dataclass(frozen=False)
class openwbSensorEntityDescription(SensorEntityDescription):
    """Enhance the sensor entity description for openWB."""

    value_fn: Callable | None = None
    valueMap: dict | None = None
    mqttTopicCurrentValue: str | None = None


# @dataclass
@dataclass(frozen=False)
class openwbBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Enhance the sensor entity description for openWB."""

    state: Callable | None = None
    mqttTopicCurrentValue: str | None = None


# @dataclass
@dataclass(frozen=False)
class openwbSelectEntityDescription(SelectEntityDescription):
    """Enhance the select entity description for openWB."""

    valueMapCommand: dict | None = None
    valueMapCurrentValue: dict | None = None
    mqttTopicCommand: str | None = None
    mqttTopicCurrentValue: str | None = None
    mqttTopicOptions: list | None = None
    value_fn: Callable | None = None
    modes: list | None = None


@dataclass
class openwbDynamicSelectEntityDescription(openwbSelectEntityDescription):
    """Enhance the select entity description for openWB with dynamic MQTT topic support."""

    # This will be used to store the base topic pattern that will be formatted with the charge template ID
    mqttTopicCurrentValueTemplate: str | None = None
    mqttTopicCommandTemplate: str | None = None


@dataclass
class openwbSwitchEntityDescription(SwitchEntityDescription):
    """Enhance the select entity description for openWB."""

    mqttTopicCommand: str | None = None
    mqttTopicCurrentValue: str | None = None
    mqttTopicChargeMode: str | None = None


@dataclass
class openWBNumberEntityDescription(NumberEntityDescription):
    """Enhance the number entity description for openWB."""

    mqttTopicCommand: str | None = None
    mqttTopicCurrentValue: str | None = None
    mqttTopicChargeMode: str | None = None
    value_fn: Callable | None = None


@dataclass
class openwbDynamicNumberEntityDescription(openWBNumberEntityDescription):
    """Enhance the number entity description for openWB with dynamic MQTT topic support."""

    # This will be used to store the base topic pattern that will be formatted with the charge template ID
    mqttTopicTemplate: str | None = None
    mqttTopicCommandTemplate: str | None = None
    convert_before_publish_fn: Callable | None = None


# Define a special sensor type for dynamic MQTT topic subscription
@dataclass
class openwbDynamicSensorEntityDescription(openwbSensorEntityDescription):
    """Enhance the sensor entity description for openWB with dynamic MQTT topic support."""

    # This will be used to store the base topic pattern that will be formatted with the charge template ID
    mqttTopicTemplate: str | None = None


SENSORS_PER_CHARGEPOINT = [
    openwbSensorEntityDescription(
        key="get/currents",
        name="Strom (L1)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        value_fn=lambda x: _splitListToFloat(x, 0),
    ),
    openwbSensorEntityDescription(
        key="get/currents",
        name="Strom (L2)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        value_fn=lambda x: _splitListToFloat(x, 1),
    ),
    openwbSensorEntityDescription(
        key="get/currents",
        name="Strom (L3)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        value_fn=lambda x: _splitListToFloat(x, 2),
    ),
    openwbSensorEntityDescription(
        key="get/daily_imported",
        name="Geladene Energie (Heute)",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda x: round(_safeFloat(x) / 1000.0, 3)
        if _safeFloat(x) is not None
        else None,
        icon="mdi:counter",
    ),
    openwbSensorEntityDescription(
        key="get/daily_exported",
        name="Entladene Energie (Heute)",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda x: round(_safeFloat(x) / 1000.0, 3)
        if _safeFloat(x) is not None
        else None,
        icon="mdi:counter",
        entity_registry_enabled_default=False,
    ),
    openwbSensorEntityDescription(
        key="get/evse_current",
        name="Ladestromvorgabe",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value_fn=lambda x: round(_safeFloat(x), 2)
        if _safeFloat(x) is not None
        else None,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        icon="mdi:current-ac",
    ),
    openwbSensorEntityDescription(
        key="get/exported",
        name="Entladene Energie (Gesamt)",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda x: round(_safeFloat(x) / 1000, 3)
        if _safeFloat(x) is not None
        else None,
        suggested_display_precision=0,
        icon="mdi:counter",
        entity_registry_enabled_default=False,
    ),
    openwbSensorEntityDescription(
        key="get/fault_str",
        name="Fehlerbeschreibung",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: _safeStringOp(x, lambda s: s.strip('"').strip(".")[0:255]),
    ),
    openwbSensorEntityDescription(
        key="get/imported",
        name="Geladene Energie (Gesamt)",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda x: round(_safeFloat(x) / 1000, 3)
        if _safeFloat(x) is not None
        else None,
        suggested_display_precision=0,
        icon="mdi:counter",
    ),
    openwbSensorEntityDescription(
        key="get/phases_in_use",
        name="Aktive Phasen",
        device_class=None,
        native_unit_of_measurement=None,
    ),
    openwbSensorEntityDescription(
        key="get/power",
        name="Ladeleistung",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:car-electric-outline",
    ),
    openwbSensorEntityDescription(
        key="get/state_str",
        name="Ladezustand",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        # value_fn=lambda x: _umlauteEinfuegen(x),
        value_fn=_umlauteEinfuegen,  # Already handles None and AttributeError
    ),
    openwbSensorEntityDescription(
        key="get/voltages",
        name="Spannung (L1)",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
        value_fn=lambda x: _splitListToFloat(x, 0),
    ),
    openwbSensorEntityDescription(
        key="get/voltages",
        name="Spannung (L2)",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
        value_fn=lambda x: _splitListToFloat(x, 1),
    ),
    openwbSensorEntityDescription(
        key="get/voltages",
        name="Spannung (L3)",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
        value_fn=lambda x: _splitListToFloat(x, 2),
    ),
    openwbSensorEntityDescription(
        key="get/power_factors",
        name="Leistungsfaktor (L1)",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=None,
        # icon=,
        value_fn=lambda x: _splitListToFloat(x, 0),
        entity_registry_enabled_default=False,
    ),
    openwbSensorEntityDescription(
        key="get/power_factors",
        name="Leistungsfaktor (L2)",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=None,
        # icon=,
        value_fn=lambda x: _splitListToFloat(x, 1),
        entity_registry_enabled_default=False,
    ),
    openwbSensorEntityDescription(
        key="get/power_factors",
        name="Leistungsfaktor (L3)",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=None,
        # icon=,
        value_fn=lambda x: _splitListToFloat(x, 2),
        entity_registry_enabled_default=False,
    ),
    openwbSensorEntityDescription(
        key="get/powers",
        name="Leistung (L1)",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:car-electric-outline",
        value_fn=lambda x: _splitListToFloat(x, 0),
    ),
    openwbSensorEntityDescription(
        key="get/powers",
        name="Leistung (L2)",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:car-electric-outline",
        value_fn=lambda x: _splitListToFloat(x, 1),
    ),
    openwbSensorEntityDescription(
        key="get/powers",
        name="Leistung (L3)",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:car-electric-outline",
        value_fn=lambda x: _splitListToFloat(x, 2),
    ),
    openwbSensorEntityDescription(
        key="get/frequency",
        name="Frequenz",
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        # icon="mdi:current-ac",
    ),
    openwbSensorEntityDescription(
        key="config",
        name="Ladepunkt",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_visible_default=False,
        value_fn=lambda x: _safeStringOp(
            _safeJsonGet(x, "name"), lambda s: s.replace('"', "")
        ),
    ),
    openwbSensorEntityDescription(
        key="get/connected_vehicle/info",
        name="Fahrzeug-ID",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_visible_default=False,
        value_fn=lambda x: _safeJsonGet(x, "id"),
    ),
    openwbSensorEntityDescription(
        key="get/connected_vehicle/info",
        name="Fahrzeug",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_visible_default=False,
        value_fn=lambda x: _safeStringOp(
            _safeJsonGet(x, "name"), lambda s: s.replace('"', "")
        ),
    ),
    openwbSensorEntityDescription(
        key="get/connected_vehicle/config",
        name="Lade-Profil",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_visible_default=False,
        value_fn=lambda x: _safeJsonGet(x, "charge_template"),
    ),
    openwbSensorEntityDescription(
        key="get/connected_vehicle/config",
        name="Lademodus",
        device_class=None,
        native_unit_of_measurement=None,
        value_fn=lambda x: _safeJsonGet(x, "chargemode"),
        valueMap={
            "standby": "Standby",
            "stop": "Stop",
            "scheduled_charging": "Scheduled Charging",
            "time_charging": "Time Charging",
            "instant_charging": "Instant Charging",
            "pv_charging": "PV Charging",
        },
        translation_key="sensor_lademodus",
    ),
    openwbSensorEntityDescription(
        key="get/connected_vehicle/soc",
        name="Ladung",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        suggested_display_precision=0,
        value_fn=lambda x: _safeJsonGet(x, "soc"),
    ),
    openwbSensorEntityDescription(
        key="get/connected_vehicle/soc",
        name="SoC-Datenaktualisierung",
        device_class=SensorDeviceClass.TIMESTAMP,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:clock-time-eight",
        value_fn=lambda x: _extractTimestampFromJson(x, "timestamp"),
        # Example: "01/02/2024, 15:29:12"
    ),
    openwbSensorEntityDescription(
        key="get/rfid",
        name="Zuletzt gescannter RFID-Tag",
        device_class=None,
        native_unit_of_measurement=None,
        icon="mdi:tag-multiple",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    openwbSensorEntityDescription(
        key="get/vehicle_id",
        name="Vehicle ID",
        device_class=None,
        native_unit_of_measurement=None,
        icon="mdi:tag-multiple",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    openwbSensorEntityDescription(
        key="get/connected_vehicle/soc",
        name="Geladene Entfernung",
        device_class=None,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:map-marker-distance",
        entity_registry_enabled_default=False,
        value_fn=lambda x: _safeJsonGet(x, "range_charged"),
        suggested_display_precision=1,
    ),
    # Dynamic sensor for instant charging current
    openwbDynamicSensorEntityDescription(
        key="instant_charging_current",
        name="Soll-Ladestrom (Sofortladen)",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:current-ac",
        suggested_display_precision=1,
        entity_registry_enabled_default=True,
        # This is a template that will be formatted with the charge template ID
        mqttTopicTemplate="{mqtt_root}/vehicle/template/charge_template/{charge_template_id}",
        # Extract the instant charging current from the JSON payload
        value_fn=lambda x: _safeNestedGet(
            x, "chargemode", "instant_charging", "current"
        ),
    ),
    # Dynamic sensor for PV charging minimum current
    openwbDynamicSensorEntityDescription(
        key="pv_charging_min_current",
        name="Min. Dauerstrom (PV-Laden)",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:current-ac",
        suggested_display_precision=1,
        entity_registry_enabled_default=True,
        # This is a template that will be formatted with the charge template ID
        mqttTopicTemplate="{mqtt_root}/vehicle/template/charge_template/{charge_template_id}",
        # Extract the PV charging minimum current from the JSON payload
        value_fn=lambda x: _safeNestedGet(
            x, "chargemode", "pv_charging", "min_current"
        ),
    ),
]

BINARY_SENSORS_PER_CHARGEPOINT = [
    openwbBinarySensorEntityDescription(
        key="plug_state",
        name="Ladekabel",
        device_class=BinarySensorDeviceClass.PLUG,
    ),
    openwbBinarySensorEntityDescription(
        key="charge_state",
        name="Autoladestatus",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
    ),
    openwbBinarySensorEntityDescription(
        key="fault_state",
        name="Fehler",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
]

SELECTS_PER_CHARGEPOINT = [
    # Dynamic select for charge mode limitation
    openwbDynamicSelectEntityDescription(
        key="instant_charging_limitation",
        entity_category=EntityCategory.CONFIG,
        name="Begrenzung (Sofortladen)",
        translation_key="selector_chargepoint_dynamic_chargemode",
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
        options=[
            "Keine",
            "EV-SoC",
            "Energiemenge",
        ],
        value_fn=lambda x: _safeNestedGet(
            x, "chargemode", "instant_charging", "limit", "selected"
        ),
    ),
    # Static select for charge mode
    openwbSelectEntityDescription(
        key="chargemode",
        entity_category=EntityCategory.CONFIG,
        name="Lademodus",
        translation_key="selector_chargepoint_chargemode",  # translation is maintained in translations/<lang>.json via this translation_key
        valueMapCurrentValue={
            "instant_charging": "Instant Charging",
            "scheduled_charging": "Scheduled Charging",
            "pv_charging": "PV Charging",
            "standby": "Standby",
            "stop": "Stop",
            # "time_charging": "Time Charging",
        },
        valueMapCommand={
            "Instant Charging": "instant_charging",
            "Scheduled Charging": "scheduled_charging",
            "PV Charging": "pv_charging",
            "Standby": "standby",
            "Stop": "stop",
            # "Time Charging": "time_charging",
        },
        mqttTopicCommand="set/vehicle/template/charge_template/_chargeTemplateID_/chargemode/selected",
        mqttTopicCurrentValue="get/connected_vehicle/config",
        options=[
            "Instant Charging",
            "Scheduled Charging",
            "PV Charging",
            "Stop",
            "Standby",
        ],
        value_fn=lambda x: _safeJsonGet(x, "chargemode"),
    ),
    openwbSelectEntityDescription(
        key="connected_vehicle",
        entity_category=EntityCategory.CONFIG,
        name="Angeschlossenes Fahrzeug",
        translation_key="selector_connected_vehicle",
        valueMapCurrentValue={
            0: "Vehicle 0",
            1: "Vehicle 1",
            2: "Vehicle 2",
            3: "Vehicle 3",
            4: "Vehicle 4",
            5: "Vehicle 5",
            6: "Vehicle 6",
            7: "Vehicle 7",
            8: "Vehicle 8",
            9: "Vehicle 9",
            10: "Vehicle 10",
        },
        valueMapCommand={
            "Vehicle 0": "0",
            "Vehicle 1": "1",
            "Vehicle 2": "2",
            "Vehicle 3": "3",
            "Vehicle 4": "4",
            "Vehicle 5": "5",
            "Vehicle 6": "6",
            "Vehicle 7": "7",
            "Vehicle 8": "8",
            "Vehicle 9": "9",
            "Vehicle 10": "10",
        },
        options=[
            "Vehicle 0",
            "Vehicle 1",
            "Vehicle 2",
            "Vehicle 3",
            "Vehicle 4",
            "Vehicle 5",
            "Vehicle 6",
            "Vehicle 7",
            "Vehicle 8",
            "Vehicle 9",
            "Vehicle 10",
        ],
        mqttTopicCommand="set/chargepoint/_chargePointID_/config/ev",
        mqttTopicCurrentValue="get/connected_vehicle/info",
        mqttTopicOptions=(
            "vehicle/0/name",
            "vehicle/1/name",
            "vehicle/2/name",
            "vehicle/3/name",
            "vehicle/4/name",
            "vehicle/5/name",
            "vehicle/6/name",
            "vehicle/7/name",
            "vehicle/8/name",
            "vehicle/9/name",
            "vehicle/10/name",
        ),
        value_fn=lambda x: _safeJsonGet(x, "id"),
        entity_registry_enabled_default=False,
    ),
]

NUMBERS_PER_CHARGEPOINT = [
    openWBNumberEntityDescription(
        key="manual_soc",
        name="Aktueller SoC (Manuelles SoC Modul)",
        native_unit_of_measurement=PERCENTAGE,
        device_class=NumberDeviceClass.BATTERY,
        # icon="mdi:battery-unknown",
        native_min_value=0.0,
        native_max_value=100.0,
        native_step=1.0,
        entity_category=EntityCategory.CONFIG,
        mqttTopicCommand="set/vehicle/_vehicleID_/soc_module/calculated_soc_state/manual_soc",
        mqttTopicCurrentValue="get/connected_vehicle/soc",
        mqttTopicChargeMode=None,
        entity_registry_enabled_default=False,
        value_fn=lambda x: _safeJsonGet(x, "soc"),
    ),
    # Dynamic number for instant charging current
    openwbDynamicNumberEntityDescription(
        key="instant_charging_current_control",
        name="Soll-Ladestrom (Sofortladen)",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=NumberDeviceClass.CURRENT,
        icon="mdi:current-ac",
        native_min_value=6.0,
        native_max_value=32.0,
        native_step=1.0,
        entity_category=EntityCategory.CONFIG,
        # This is a template that will be formatted with the charge template ID for reading the current value
        mqttTopicTemplate="{mqtt_root}/vehicle/template/charge_template/{charge_template_id}",
        # This is a template that will be formatted with the charge template ID for setting the current value
        mqttTopicCommandTemplate="{mqtt_root}/set/vehicle/template/charge_template/{charge_template_id}/chargemode/instant_charging/current",
        # Extract the instant charging current from the JSON payload
        value_fn=lambda x: _safeNestedGet(
            x, "chargemode", "instant_charging", "current"
        ),
    ),
    # Dynamic number for PV charging minimum current
    openwbDynamicNumberEntityDescription(
        key="pv_charging_min_current_control",
        name="Min. Dauerstrom (PV-Laden)",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=NumberDeviceClass.CURRENT,
        icon="mdi:current-ac",
        native_min_value=0.0,
        native_max_value=16.0,
        native_step=1.0,
        entity_category=EntityCategory.CONFIG,
        # This is a template that will be formatted with the charge template ID for reading the current value
        mqttTopicTemplate="{mqtt_root}/vehicle/template/charge_template/{charge_template_id}",
        # This is a template that will be formatted with the charge template ID for setting the current value
        mqttTopicCommandTemplate="{mqtt_root}/set/vehicle/template/charge_template/{charge_template_id}/chargemode/pv_charging/min_current",
        # Extract the PV charging minimum current from the JSON payload
        value_fn=lambda x: _safeNestedGet(
            x, "chargemode", "pv_charging", "min_current"
        ),
    ),
    # Dynamic number for instant charging energy limit
    openwbDynamicNumberEntityDescription(
        key="instant_charging_energy_limit_control",
        name="Energie-Limit (Sofortladen)",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=NumberDeviceClass.ENERGY,
        # icon="mdi:current-ac",
        native_min_value=1,
        native_max_value=80,
        native_step=1,
        entity_category=EntityCategory.CONFIG,
        # This is a template that will be formatted with the charge template ID for reading the current value
        mqttTopicTemplate="{mqtt_root}/vehicle/template/charge_template/{charge_template_id}",
        # This is a template that will be formatted with the charge template ID for setting the current value
        mqttTopicCommandTemplate="{mqtt_root}/set/vehicle/template/charge_template/{charge_template_id}/chargemode/instant_charging/limit/amount",
        # Extract the current value from the JSON payload and convert from Wh to kWh
        convert_before_publish_fn=lambda x: x * 1000.0,
        value_fn=lambda x: _safeNestedGet(
            x, "chargemode", "instant_charging", "limit", "amount"
        )
        / 1000
        if _safeNestedGet(x, "chargemode", "instant_charging", "limit", "amount")
        is not None
        else None,
    ),
    # Dynamic number for instant charging soc limit
    openwbDynamicNumberEntityDescription(
        key="instant_charging_soc_limit_control",
        name="SoC-Limit (Sofortladen)",
        native_unit_of_measurement=PERCENTAGE,
        device_class=NumberDeviceClass.BATTERY,
        # icon="mdi:current-ac",
        native_min_value=5,
        native_max_value=100,
        native_step=5,
        entity_category=EntityCategory.CONFIG,
        # This is a template that will be formatted with the charge template ID for reading the current value
        mqttTopicTemplate="{mqtt_root}/vehicle/template/charge_template/{charge_template_id}",
        # This is a template that will be formatted with the charge template ID for setting the current value
        mqttTopicCommandTemplate="{mqtt_root}/set/vehicle/template/charge_template/{charge_template_id}/chargemode/instant_charging/limit/soc",
        ## Extract the current value from the JSON payload and convert from Wh to kWh
        # convert_before_publish_fn=lambda x: x * 1000.0,
        value_fn=lambda x: _safeNestedGet(
            x, "chargemode", "instant_charging", "limit", "soc"
        )
        if _safeNestedGet(x, "chargemode", "instant_charging", "limit", "soc")
        is not None
        else None,
    ),
    # openWBNumberEntityDescription(
    #     key="pv_charging_min_current",
    #     name="Ladestromvorgabe (PV Laden)",
    #     native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
    #     device_class=SensorDeviceClass.CURRENT,
    #     icon="mdi:current-ac",
    #     native_min_value=0,
    #     native_max_value=16,
    #     native_step=1,
    #     entity_category=EntityCategory.CONFIG,
    #     mqttTopicCommand="set/vehicle/template/charge_template/_chargeTemplateID_/chargemode/pv_charging/min_current",
    #     mqttTopicCurrentValue="vehicle/template/charge_template/_ChargeTemplateID_",
    #     mqttTopicChargeMode=None,
    #     # entity_registry_enabled_default=False,
    #     value_fn=lambda x: json.loads(x)
    #     .get("chargemode")
    #     .get("pv_charging")
    #     .get("min_current"),
    # ),
]

SENSORS_PER_COUNTER = [
    openwbSensorEntityDescription(
        key="voltages",
        name="Spannung (L1)",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
        value_fn=lambda x: _splitListToFloat(x, 0),
    ),
    openwbSensorEntityDescription(
        key="voltages",
        name="Spannung (L2)",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
        value_fn=lambda x: _splitListToFloat(x, 1),
    ),
    openwbSensorEntityDescription(
        key="voltages",
        name="Spannung (L3)",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
        value_fn=lambda x: _splitListToFloat(x, 2),
    ),
    openwbSensorEntityDescription(
        key="power_factors",
        name="Leistungsfaktor (L1)",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=None,
        # icon=,
        value_fn=lambda x: _splitListToFloat(x, 0),
        entity_registry_enabled_default=False,
    ),
    openwbSensorEntityDescription(
        key="power_factors",
        name="Leistungsfaktor (L2)",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=None,
        # icon=,
        value_fn=lambda x: _splitListToFloat(x, 1),
        entity_registry_enabled_default=False,
    ),
    openwbSensorEntityDescription(
        key="power_factors",
        name="Leistungsfaktor (L3)",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=None,
        # icon=,
        value_fn=lambda x: _splitListToFloat(x, 2),
        entity_registry_enabled_default=False,
    ),
    openwbSensorEntityDescription(
        key="powers",
        name="Leistung (L1)",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:transmission-tower",
        value_fn=lambda x: _splitListToFloat(x, 0),
    ),
    openwbSensorEntityDescription(
        key="powers",
        name="Leistung (L2)",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:transmission-tower",
        value_fn=lambda x: _splitListToFloat(x, 1),
    ),
    openwbSensorEntityDescription(
        key="powers",
        name="Leistung (L3)",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:transmission-tower",
        value_fn=lambda x: _splitListToFloat(x, 2),
    ),
    openwbSensorEntityDescription(
        key="frequency",
        name="Frequenz",
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        # icon="mdi:current-ac",
    ),
    openwbSensorEntityDescription(
        key="currents",
        name="Strom (L1)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        value_fn=lambda x: _splitListToFloat(x, 0),
    ),
    openwbSensorEntityDescription(
        key="currents",
        name="Strom (L2)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        value_fn=lambda x: _splitListToFloat(x, 1),
    ),
    openwbSensorEntityDescription(
        key="currents",
        name="Strom (L3)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        value_fn=lambda x: _splitListToFloat(x, 2),
    ),
    openwbSensorEntityDescription(
        key="power",
        name="Leistung",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        # state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        icon="mdi:transmission-tower",
    ),
    openwbSensorEntityDescription(
        key="fault_str",
        name="Fehlerbeschreibung",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: _safeStringOp(x, lambda s: s.strip('"').strip(".")[0:255]),
    ),
    openwbSensorEntityDescription(
        key="exported",
        name="Exportierte Energie (Gesamt)",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda x: round(_safeFloat(x) / 1000, 3)
        if _safeFloat(x) is not None
        else None,
        suggested_display_precision=0,
        icon="mdi:transmission-tower-export",
    ),
    openwbSensorEntityDescription(
        key="imported",
        name="Importierte Energie (Gesamt)",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda x: round(_safeFloat(x) / 1000, 3)
        if _safeFloat(x) is not None
        else None,
        suggested_display_precision=0,
        icon="mdi:transmission-tower-import",
    ),
    openwbSensorEntityDescription(
        key="daily_imported",
        name="Importierte Energie (Heute)",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda x: round(_safeFloat(x) / 1000.0, 3)
        if _safeFloat(x) is not None
        else None,
        suggested_display_precision=1,
        icon="mdi:transmission-tower-import",
    ),
    openwbSensorEntityDescription(
        key="daily_exported",
        name="Exportierte Energie (Heute)",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda x: round(_safeFloat(x) / 1000.0, 3)
        if _safeFloat(x) is not None
        else None,
        suggested_display_precision=1,
        icon="mdi:transmission-tower-export",
    ),
]

BINARY_SENSORS_PER_COUNTER = [
    openwbBinarySensorEntityDescription(
        key="fault_state",
        name="Fehler",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
]

SENSORS_PER_BATTERY = [
    openwbSensorEntityDescription(
        key="soc",
        name="Ladung",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        # icon="mdi:transmission-tower",
    ),
    openwbSensorEntityDescription(
        key="power",
        name="Leistung",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        icon="mdi:battery-charging",
    ),
    openwbSensorEntityDescription(
        key="fault_str",
        name="Fehlerbeschreibung",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: _safeStringOp(x, lambda s: s.strip('"').strip(".")[0:255]),
    ),
    openwbSensorEntityDescription(
        key="exported",
        name="Entladene Energie (Gesamt)",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda x: round(_safeFloat(x) / 1000, 3)
        if _safeFloat(x) is not None
        else None,
        suggested_display_precision=0,
        icon="mdi:battery-arrow-up",
    ),
    openwbSensorEntityDescription(
        key="imported",
        name="Geladene Energie (Gesamt)",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda x: round(_safeFloat(x) / 1000, 3)
        if _safeFloat(x) is not None
        else None,
        suggested_display_precision=0,
        icon="mdi:battery-arrow-down",
    ),
    openwbSensorEntityDescription(
        key="daily_imported",
        name="Geladene Energie (Heute)",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda x: round(_safeFloat(x) / 1000.0, 3)
        if _safeFloat(x) is not None
        else None,
        suggested_display_precision=1,
        icon="mdi:battery-arrow-down",
    ),
    openwbSensorEntityDescription(
        key="daily_exported",
        name="Entladene Energie (Heute)",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda x: round(_safeFloat(x) / 1000.0, 3)
        if _safeFloat(x) is not None
        else None,
        suggested_display_precision=1,
        icon="mdi:battery-arrow-up",
    ),
]

BINARY_SENSORS_PER_BATTERY = [
    openwbBinarySensorEntityDescription(
        key="fault_state",
        name="Fehler",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
]

SENSORS_PER_PVGENERATOR = [
    openwbSensorEntityDescription(
        key="daily_exported",
        name="Zählerstand (Heute)",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda x: round(_safeFloat(x) / 1000.0, 3)
        if _safeFloat(x) is not None
        else None,
        suggested_display_precision=1,
        icon="mdi:counter",
    ),
    openwbSensorEntityDescription(
        key="monthly_exported",
        name="Zählerstand (Monat)",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda x: round(_safeFloat(x) / 1000.0, 3)
        if _safeFloat(x) is not None
        else None,
        suggested_display_precision=0,
        icon="mdi:counter",
    ),
    openwbSensorEntityDescription(
        key="yearly_exported",
        name="Zählerstand (Jahr)",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda x: round(_safeFloat(x) / 1000.0, 3)
        if _safeFloat(x) is not None
        else None,
        suggested_display_precision=0,
        icon="mdi:counter",
    ),
    openwbSensorEntityDescription(
        key="exported",
        name="Zählerstand (Gesamt)",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda x: round(_safeFloat(x) / 1000.0, 3)
        if _safeFloat(x) is not None
        else None,
        suggested_display_precision=0,
        icon="mdi:counter",
    ),
    openwbSensorEntityDescription(
        key="power",
        name="Leistung",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        icon="mdi:solar-power",
        suggested_display_precision=0,
        value_fn=lambda x: abs(_safeFloat(x)) if _safeFloat(x) is not None else None,
    ),
    openwbSensorEntityDescription(
        key="currents",
        name="Strom (L1)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        value_fn=lambda x: _splitListToFloat(x, 0),
    ),
    openwbSensorEntityDescription(
        key="currents",
        name="Strom (L2)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        value_fn=lambda x: _splitListToFloat(x, 1),
    ),
    openwbSensorEntityDescription(
        key="currents",
        name="Strom (L3)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        value_fn=lambda x: _splitListToFloat(x, 2),
    ),
    openwbSensorEntityDescription(
        key="fault_str",
        name="Fehlerbeschreibung",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: _safeStringOp(x, lambda s: s.strip('"').strip(".")[0:255]),
    ),
]

BINARY_SENSORS_PER_PVGENERATOR = [
    openwbBinarySensorEntityDescription(
        key="fault_state",
        name="Fehler",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
]

SENSORS_CONTROLLER = [
    # System
    openwbSensorEntityDescription(
        key="system/ip_address",
        name="IP-Adresse",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:earth",
        value_fn=lambda x: _safeStringOp(x, lambda s: s.replace('"', "")),
    ),
    openwbSensorEntityDescription(
        key="system/version",
        name="Version",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:folder-clock",
        value_fn=lambda x: _safeStringOp(x, lambda s: s.replace('"', "")),
    ),
    openwbSensorEntityDescription(
        key="system/lastlivevaluesJson",
        name="Datenaktualisierung",
        device_class=SensorDeviceClass.TIMESTAMP,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:clock-time-eight",
        # value_fn=lambda x: datetime.datetime.fromtimestamp(
        #    int(json.loads(x).get("timestamp")), tz=ZoneInfo("UTC")
        # ),
        value_fn=lambda x: _extractTimestampFromJson(x, "timestamp"),
    ),
    openwbSensorEntityDescription(
        key="system/lastlivevaluesJson",
        name="Netzbezug/-einspeisung",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:transmission-tower",
        value_fn=lambda x: _splitJsonLastLiveValues(
            x, "grid", 1000
        ),  # Already handles None and json.JSONDecodeError
    ),
    openwbSensorEntityDescription(
        key="system/lastlivevaluesJson",
        name="Hausverbrauch",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:home-lightning-bolt",
        value_fn=lambda x: _splitJsonLastLiveValues(
            x, "house-power", 1000
        ),  # Already handles None and json.JSONDecodeError
    ),
    openwbSensorEntityDescription(
        key="system/lastlivevaluesJson",
        name="PV-Leistung (Gesamt)",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:solar-power",
        value_fn=lambda x: _splitJsonLastLiveValues(
            x, "pv-all", 1000
        ),  # Already handles None and json.JSONDecodeError
    ),
    openwbSensorEntityDescription(
        key="system/lastlivevaluesJson",
        name="Ladeleistung (Gesamt)",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:car-electric-outline",
        value_fn=lambda x: _splitJsonLastLiveValues(
            x, "charging-all", 1000
        ),  # Already handles None and json.JSONDecodeError
    ),
    openwbSensorEntityDescription(
        key="system/lastlivevaluesJson",
        name="Batterieleistung (Gesamt)",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:battery-charging",
        value_fn=lambda x: _splitJsonLastLiveValues(
            x, "bat-all-power", 1000
        ),  # Already handles None and json.JSONDecodeError
    ),
    openwbSensorEntityDescription(
        key="system/lastlivevaluesJson",
        name="Batterieladung (Gesamt)",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda x: _splitJsonLastLiveValues(
            x, "bat-all-soc", 1
        ),  # Already handles None and json.JSONDecodeError
    ),
]


SENSORS_PER_VEHICLE = [
    openwbSensorEntityDescription(
        key="name",
        name="Bezeichnung",
        device_class=None,
        native_unit_of_measurement=None,
        # state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        value_fn=lambda x: _safeStringOp(x, lambda s: s.replace('"', "")),
        icon="mdi:car",
    ),
    openwbSensorEntityDescription(
        key="soc",
        name="Ladung",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        suggested_display_precision=0,
    ),
    openwbSensorEntityDescription(
        key="range",
        name="Reichweite",
        device_class=None,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:map-marker-distance",
        entity_registry_enabled_default=True,
        # value_fn=lambda x: json.loads(x).get("range_charged"),
        suggested_display_precision=0,
    ),
    openwbSensorEntityDescription(
        key="soc_timestamp",
        name="Datenaktualisierung",
        device_class=SensorDeviceClass.TIMESTAMP,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:clock-time-eight",
        # value_fn=lambda x: _extractTimestamp(x),
        value_fn=_extractTimestamp,
    ),
    openwbSensorEntityDescription(
        key="fault_str",
        name="Fehlerbeschreibung",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: _safeStringOp(x, lambda s: s.strip('"').strip(".")[0:255]),
    ),
]

BINARY_SENSORS_PER_VEHICLE = [
    openwbBinarySensorEntityDescription(
        key="fault_state",
        name="Fehler",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
]

# get vehicle names
SENSORS_CONTROLLER.extend(
    openwbSensorEntityDescription(
        key=f"vehicle/{vehicle_id}/name",
        name=f"Vehicle Name {vehicle_id}",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:car-electric-outline",
        value_fn=lambda x: _safeStringOp(x, lambda s: s.replace('"', "")),
    )
    for vehicle_id in range(11)
)
