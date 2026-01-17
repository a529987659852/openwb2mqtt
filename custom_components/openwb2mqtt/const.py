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
from homeassistant.components.lock import LockEntityDescription
from homeassistant.components.number import NumberDeviceClass, NumberEntityDescription
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

# Platform.SWITCH,
PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.LOCK,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]

# Global values
DOMAIN = "openwb2mqtt"
COMMUNICATION_METHOD = "communication_method"
COMM_METHOD_MQTT = "MQTT"
COMM_METHOD_HTTP = "HTTP API"
API_URL = "api_url"
API_TOKEN = "api_token - leave empty for now"
CONF_WALLBOX_POWER = "wallbox_power"
MQTT_ROOT_TOPIC = "mqttroot"
MQTT_ROOT_TOPIC_DEFAULT = "openWB"
API_PREFIX = "api_prefix"
DEVICETYPE = "DEVICETYPE"
DEVICEID = "DEVICEID"
CONF_VEHICLES = "vehicles"
CONF_VEHICLE_NAME = "vehicle_name"
CONF_VEHICLE_ID = "vehicle_id"
MANUFACTURER = "openWB"
MODEL = "openWB"

# Data schema required by configuration flow
DATA_SCHEMA = vol.Schema(
    {
        vol.Required(COMMUNICATION_METHOD, default=COMM_METHOD_HTTP): SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value=COMM_METHOD_MQTT, label="MQTT"),
                    SelectOptionDict(value=COMM_METHOD_HTTP, label="HTTP API"),
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
    }
)

DATA_SCHEMA_MQTT = vol.Schema(
    {
        vol.Required(MQTT_ROOT_TOPIC, default=MQTT_ROOT_TOPIC_DEFAULT): cv.string,
        vol.Required(DEVICETYPE, default="chargepoint"): SelectSelector(
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
        vol.Required(DEVICEID, default=4): cv.positive_int,
    }
)

DATA_SCHEMA_API = vol.Schema(
    {
        vol.Required(API_PREFIX, default=MQTT_ROOT_TOPIC_DEFAULT): cv.string,
        vol.Required(API_URL): cv.string,
        # vol.Optional(API_TOKEN): cv.string,
        vol.Required(DEVICETYPE, default="chargepoint"): SelectSelector(
            SelectSelectorConfig(
                options=[
                    # Some device types are not available via api
                    SelectOptionDict(value="controller", label="Controller"),
                    SelectOptionDict(value="counter", label="Counter"),
                    SelectOptionDict(value="chargepoint", label="Chargepoint"),
                    SelectOptionDict(value="pv", label="PV Generator"),
                    SelectOptionDict(value="bat", label="Battery"),
                    # SelectOptionDict(value="vehicle", label="Vehicle"),
                ],
                mode=SelectSelectorMode.DROPDOWN,
                translation_key="config_selector_devicetype",  # translation is maintained in translations/<lang>.json via this translation_key
            )
        ),
        vol.Required(DEVICEID, default=4): cv.positive_int,
    }
)

DATA_SCHEMA_OPTIONS_CP_MQTT = vol.Schema(
    {
        vol.Required(CONF_WALLBOX_POWER, default="11"): SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value="11", label="11 kW"),
                    SelectOptionDict(value="22", label="22 kW"),
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
    }
)

DATA_SCHEMA_OPTIONS_CP = vol.Schema(
    {
        vol.Required(CONF_WALLBOX_POWER, default="11"): SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value="11", label="11 kW"),
                    SelectOptionDict(value="22", label="22 kW"),
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(
            CONF_VEHICLES,
            description={"suggested_value": "0=Standard-Fahrzeug, 1=Fahrzeug (1)"},
        ): cv.string,
    }
)


def _safeFloat(x: str, c=1.0, op="div") -> float | None:
    """Safely convert a string to float, handling None and conversion errors."""
    if x is None:
        return None
    try:
        if op == "div":
            return float(x) / c
        elif op == "mult":
            return float(x) * c
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
        if isinstance(x, str):
            x = x.replace("[", "").replace("]", "")
            return float(x.split(",")[desiredValueIndex])
        else:
            return float(x[desiredValueIndex])
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
    api_value_fn: Callable | None = None
    valueMap: dict | None = None
    mqttTopicCurrentValue: str | None = None
    api_key: str | None = None


# @dataclass
@dataclass(frozen=False)
class openwbBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Enhance the sensor entity description for openWB."""

    state: Callable | None = None
    mqttTopicCurrentValue: str | None = None
    api_key: str | None = None


# @dataclass
@dataclass(frozen=False)
class openwbSelectEntityDescription(SelectEntityDescription):
    """Enhance the select entity description for openWB."""

    valueMapCommand: dict | None = None
    api_key: str | None = None
    api_key_command: str | None = None
    api_value_map_command: dict | None = None
    valueMapCurrentValue: dict | None = None
    mqttTopicCommand: str | None = None
    mqttTopicCurrentValue: str | None = None
    mqttTopicOptions: list | None = None
    value_fn: Callable | None = None
    api_value_fn: Callable | None = None
    modes: list | None = None
    api_key: str | None = None


@dataclass(frozen=False)
class openwbDynamicSelectEntityDescription(openwbSelectEntityDescription):
    """Enhance the select entity description for openWB with dynamic MQTT topic support."""

    # This will be used to store the base topic pattern that will be formatted with the charge template ID
    mqttTopicCurrentValueTemplate: str | None = None
    mqttTopicCommandTemplate: str | None = None


@dataclass(frozen=False)
class openwbSwitchEntityDescription(SwitchEntityDescription):
    """Enhance the select entity description for openWB."""

    mqttTopicCommand: str | None = None
    mqttTopicCurrentValue: str | None = None
    mqttTopicChargeMode: str | None = None


@dataclass(frozen=False)
class openWBNumberEntityDescription(NumberEntityDescription):
    """Enhance the number entity description for openWB."""

    mqttTopicCommand: str | None = None
    mqttTopicCurrentValue: str | None = None
    mqttTopicChargeMode: str | None = None
    value_fn: Callable | None = None
    api_value_fn: Callable | None = None
    api_key: str | None = None
    api_key_command: str | None = None


@dataclass(frozen=False)
class openwbDynamicNumberEntityDescription(openWBNumberEntityDescription):
    """Enhance the number entity description for openWB with dynamic MQTT topic support."""

    # This will be used to store the base topic pattern that will be formatted with the charge template ID
    mqttTopicTemplate: str | None = None
    mqttTopicCommandTemplate: str | None = None
    convert_before_publish_fn: Callable | None = None


# Define a special sensor type for dynamic MQTT topic subscription
@dataclass(frozen=False)
class openwbDynamicSensorEntityDescription(openwbSensorEntityDescription):
    """Enhance the sensor entity description for openWB with dynamic MQTT topic support."""

    # This will be used to store the base topic pattern that will be formatted with the charge template ID
    mqttTopicTemplate: str | None = None


@dataclass(frozen=False)
class openwbLockEntityDescription(LockEntityDescription):
    """A class that describes lock entities."""

    mqttTopicCommand: str | None = None
    mqttTopicCurrentValue: str | None = None
    payload_lock: str = "true"
    payload_unlock: str = "false"
    state_locked: str = "true"
    state_unlocked: str = "false"
    api_key: str | None = None
    api_key_command: str | None = None
    api_value_map_command: dict | None = None


SENSORS_PER_CHARGEPOINT = [
    openwbSensorEntityDescription(
        key="get/currents",
        api_key="currents",
        name="Strom (L1)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        value_fn=lambda x: _splitListToFloat(x, 0),
    ),
    openwbSensorEntityDescription(
        key="get/currents",
        api_key="currents",
        name="Strom (L2)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        value_fn=lambda x: _splitListToFloat(x, 1),
    ),
    openwbSensorEntityDescription(
        key="get/currents",
        api_key="currents",
        name="Strom (L3)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        value_fn=lambda x: _splitListToFloat(x, 2),
    ),
    openwbSensorEntityDescription(
        key="get/daily_imported",
        api_key="daily_imported",
        name="Geladene Energie (Heute)",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda x: round(float(_safeFloat(x) or 0) / 1000.0, 3),
        icon="mdi:counter",
    ),
    openwbSensorEntityDescription(
        key="get/daily_exported",
        api_key="daily_exported",
        name="Entladene Energie (Heute)",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda x: round(float(_safeFloat(x) or 0) / 1000.0, 3)
        if _safeFloat(x) is not None
        else None,
        icon="mdi:counter",
        entity_registry_enabled_default=False,
    ),
    openwbSensorEntityDescription(
        key="get/evse_current",
        api_key="evse_current",
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
        api_key="exported",
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
        api_key="fault_str",
        name="Fehlerbeschreibung",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: _safeStringOp(x, lambda s: s.strip('"').strip(".")[0:255]),
    ),
    openwbSensorEntityDescription(
        key="get/imported",
        api_key="imported",
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
        api_key="phases_in_use",
        name="Aktive Phasen",
        device_class=None,
        native_unit_of_measurement=None,
    ),
    openwbSensorEntityDescription(
        key="get/power",
        api_key="power",
        name="Ladeleistung",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:car-electric-outline",
    ),
    openwbSensorEntityDescription(
        key="get/state_str",
        api_key="state_str",
        name="Ladezustand",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_umlauteEinfuegen,
    ),
    openwbSensorEntityDescription(
        key="get/voltages",
        api_key="voltages",
        name="Spannung (L1)",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
        value_fn=lambda x: _splitListToFloat(x, 0),
    ),
    openwbSensorEntityDescription(
        key="get/voltages",
        api_key="voltages",
        name="Spannung (L2)",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
        value_fn=lambda x: _splitListToFloat(x, 1),
    ),
    openwbSensorEntityDescription(
        key="get/voltages",
        api_key="voltages",
        name="Spannung (L3)",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
        value_fn=lambda x: _splitListToFloat(x, 2),
    ),
    openwbSensorEntityDescription(
        key="get/power_factors",
        api_key="power_factors",
        name="Leistungsfaktor (L1)",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=None,
        value_fn=lambda x: _splitListToFloat(x, 0),
        entity_registry_enabled_default=False,
    ),
    openwbSensorEntityDescription(
        key="get/power_factors",
        api_key="power_factors",
        name="Leistungsfaktor (L2)",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=None,
        value_fn=lambda x: _splitListToFloat(x, 1),
        entity_registry_enabled_default=False,
    ),
    openwbSensorEntityDescription(
        key="get/power_factors",
        api_key="power_factors",
        name="Leistungsfaktor (L3)",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=None,
        value_fn=lambda x: _splitListToFloat(x, 2),
        entity_registry_enabled_default=False,
    ),
    openwbSensorEntityDescription(
        key="get/powers",
        api_key="powers",
        name="Leistung (L1)",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:car-electric-outline",
        value_fn=lambda x: _splitListToFloat(x, 0),
    ),
    openwbSensorEntityDescription(
        key="get/powers",
        api_key="powers",
        name="Leistung (L2)",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:car-electric-outline",
        value_fn=lambda x: _splitListToFloat(x, 1),
    ),
    openwbSensorEntityDescription(
        key="get/powers",
        api_key="powers",
        name="Leistung (L3)",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:car-electric-outline",
        value_fn=lambda x: _splitListToFloat(x, 2),
    ),
    openwbSensorEntityDescription(
        key="get/frequency",
        api_key=None,
        name="Frequenz",
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
    ),
    openwbSensorEntityDescription(
        key="config",
        api_key="config_name",
        name="Ladepunkt",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_visible_default=False,
        # value_fn=lambda x: _safeStringOp(x, lambda s: s.replace('"', "")),
        value_fn=lambda x: _safeJsonGet(x, "name"),
        api_value_fn=lambda x: x,
    ),
    openwbSensorEntityDescription(
        key="get/connected_vehicle/info",
        api_key="vehicle_id",
        name="Fahrzeug-ID",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_visible_default=False,
        value_fn=lambda x: _safeJsonGet(x, "id"),
        api_value_fn=lambda x: x,
    ),
    openwbSensorEntityDescription(
        key="get/connected_vehicle/info",
        api_key="connected_vehicle_name",
        name="Fahrzeug",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_visible_default=False,
        value_fn=lambda x: _safeStringOp(
            str(_safeJsonGet(x, "name")), lambda s: s.replace('"', "")
        ),
        api_value_fn=lambda x: _safeStringOp(x, lambda s: s.replace('"', "")),
    ),
    openwbSensorEntityDescription(
        key="get/connected_vehicle/config",
        api_key="charge_template_name",
        name="Lade-Profil",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_visible_default=False,
        value_fn=lambda x: _safeJsonGet(x, "charge_template"),
        api_value_fn=lambda x: x,
    ),
    openwbSensorEntityDescription(
        key="get/connected_vehicle/config",
        api_key="chargemode",
        name="Lademodus",
        device_class=None,
        native_unit_of_measurement=None,
        value_fn=lambda x: _safeJsonGet(x, "chargemode"),
        api_value_fn=lambda x: x,
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
        api_key="soc",
        name="Ladung",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        suggested_display_precision=0,
        value_fn=lambda x: _safeJsonGet(x, "soc"),
        api_value_fn=lambda x: x,
    ),
    openwbSensorEntityDescription(
        key="get/connected_vehicle/soc",
        api_key="soc_timestamp",
        name="SoC-Datenaktualisierung",
        device_class=SensorDeviceClass.TIMESTAMP,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:clock-time-eight",
        value_fn=lambda x: _extractTimestampFromJson(x, "timestamp"),
        api_value_fn=lambda x: _extractTimestamp(x) if x not in {"null"} else None,
    ),
    openwbSensorEntityDescription(
        key="get/rfid",
        api_key="rfid",
        name="Zuletzt gescannter RFID-Tag",
        device_class=None,
        native_unit_of_measurement=None,
        icon="mdi:tag-multiple",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    openwbSensorEntityDescription(
        key="get/vehicle_id",
        api_key="vehicle_id",
        name="Vehicle ID",
        device_class=None,
        native_unit_of_measurement=None,
        icon="mdi:tag-multiple",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    openwbSensorEntityDescription(
        key="get/connected_vehicle/soc",
        api_key="range_charged",
        name="Geladene Entfernung",
        device_class=None,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:map-marker-distance",
        entity_registry_enabled_default=False,
        value_fn=lambda x: _safeJsonGet(x, "range_charged"),
        suggested_display_precision=1,
        api_value_fn=lambda x: x,
    ),
    openwbDynamicSensorEntityDescription(
        key="instant_charging_current",
        api_key="instant_charging_current",
        name="Soll-Ladestrom (Sofortladen)",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:current-ac",
        suggested_display_precision=1,
        entity_registry_enabled_default=True,
        mqttTopicTemplate="{mqtt_root}/vehicle/template/charge_template/{charge_template_id}",
        value_fn=lambda x: _safeNestedGet(
            x, "chargemode", "instant_charging", "current"
        ),
        api_value_fn=lambda x: _safeFloat(x),
    ),
    openwbDynamicSensorEntityDescription(
        key="pv_charging_min_current",
        api_key="pv_charging_min_current",
        name="Min. Dauerstrom (PV-Laden)",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:current-ac",
        suggested_display_precision=1,
        entity_registry_enabled_default=True,
        mqttTopicTemplate="{mqtt_root}/vehicle/template/charge_template/{charge_template_id}",
        value_fn=lambda x: _safeNestedGet(
            x, "chargemode", "pv_charging", "min_current"
        ),
        api_value_fn=lambda x: _safeFloat(x),
    ),
    # Dynamic number for price-based charging maximum price
    openwbDynamicSensorEntityDescription(
        key="price_based_charging_max_price",
        name="Max. Preis (Strompreisbasiertes Laden)",
        native_unit_of_measurement="ct/kWh",
        device_class=None,
        icon="mdi:currency-eur",
        entity_category=EntityCategory.DIAGNOSTIC,
        # This is a template that will be formatted with the charge template ID for reading the current value
        mqttTopicTemplate="{mqtt_root}/vehicle/template/charge_template/{charge_template_id}",
        # This is a template that will be formatted with the charge template ID for setting the current value
        # Extract the current value from the JSON payload
        value_fn=lambda x: _safeFloat(
            _safeNestedGet(x, "chargemode", "eco_charging", "max_price"),
            c=100000,
            op="mult",
        )
        if _safeNestedGet(x, "chargemode", "eco_charging", "max_price") is not None
        else None,
    ),
]

BINARY_SENSORS_PER_CHARGEPOINT = [
    openwbBinarySensorEntityDescription(
        key="plug_state",
        api_key="plug_state",
        name="Ladekabel",
        device_class=BinarySensorDeviceClass.PLUG,
    ),
    openwbBinarySensorEntityDescription(
        key="charge_state",
        api_key="charge_state",
        name="Autoladestatus",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
    ),
    openwbBinarySensorEntityDescription(
        key="fault_state",
        api_key="fault_state",
        name="Fehler",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
]

SELECTS_PER_CHARGEPOINT = [
    openwbDynamicSelectEntityDescription(
        key="instant_charging_limitation",
        api_key="instant_charging_limit",
        api_key_command="instant_charging_limit",
        api_value_map_command={
            "Keine": "none",
            "SoC": "soc",
            "Energiemenge": "amount",
        },
        entity_category=EntityCategory.CONFIG,
        name="Begrenzung (Sofortladen)",
        translation_key="selector_chargepoint_dynamic_chargemode",
        valueMapCurrentValue={
            "none": "Keine",
            "soc": "SoC",
            "amount": "Energiemenge",
        },
        valueMapCommand={"Keine": "none", "SoC": "soc", "Energiemenge": "amount"},
        mqttTopicCommandTemplate="{mqtt_root}/set/vehicle/template/charge_template/{charge_template_id}/chargemode/instant_charging/limit/selected",
        mqttTopicCurrentValueTemplate="{mqtt_root}/vehicle/template/charge_template/{charge_template_id}",
        options=["Keine", "SoC", "Energiemenge"],
        value_fn=lambda x: _safeNestedGet(
            x, "chargemode", "instant_charging", "limit", "selected"
        ),
        api_value_fn=lambda x: x,
    ),
    openwbSelectEntityDescription(
        key="chargemode",
        api_key="chargemode",
        api_key_command="set_chargemode",
        entity_category=EntityCategory.CONFIG,
        name="Lademodus",
        translation_key="selector_chargepoint_chargemode",
        valueMapCurrentValue={
            "instant_charging": "Instant Charging",
            "instant": "Instant Charging",
            "scheduled_charging": "Target Charging",
            "pv_charging": "PV Charging",
            "eco_charging": "ECO Charging",
            "target": "Target Charging",
            "standby": "Standby",
            "stop": "Stop",
            "pv": "PV Charging",
        },
        valueMapCommand={
            "Instant Charging": "instant",
            # "Scheduled Charging": "scheduled_charging",
            "PV Charging": "pv",
            "ECO Charging": "eco",
            "Target Charging": "target",
            "Stop": "stop",
        },
        api_value_map_command={
            "Instant Charging": "instant",
            "PV Charging": "pv",
            "ECO Charging": "eco",
            "Target Charging": "target",
            "Stop": "stop",
        },
        mqttTopicCommand="simpleAPI/set/chargepoint/_chargePointID_/chargemode",
        mqttTopicCurrentValue="get/connected_vehicle/config",
        options=[
            "Instant Charging",
            # "Scheduled Charging",
            "PV Charging",
            "ECO Charging",
            "Target Charging",
            "Stop",
            "Standby",
        ],
        value_fn=lambda x: _safeJsonGet(x, "chargemode"),
        api_value_fn=lambda x: x,
    ),
    openwbSelectEntityDescription(
        key="connected_vehicle",
        api_key="connected_vehicle_name",
        api_key_command="vehicle",
        entity_category=EntityCategory.CONFIG,
        name="Angeschlossenes Fahrzeug",
        translation_key="selector_connected_vehicle",
        mqttTopicCommand="set/chargepoint/_chargePointID_/config/ev",
        mqttTopicCurrentValue="get/connected_vehicle/info",
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
        api_value_fn=lambda x: x,
        entity_registry_enabled_default=False,
    ),
]

NUMBERS_PER_CHARGEPOINT = [
    openWBNumberEntityDescription(
        key="manual_soc",
        api_key="soc",
        api_key_command="manual_soc",
        name="Aktueller SoC (Manuelles SoC Modul)",
        native_unit_of_measurement=PERCENTAGE,
        device_class=NumberDeviceClass.BATTERY,
        native_min_value=0.0,
        native_max_value=100.0,
        native_step=1.0,
        entity_category=EntityCategory.CONFIG,
        mqttTopicCommand="set/vehicle/_vehicleID_/soc_module/calculated_soc_state/manual_soc",
        mqttTopicCurrentValue="chargepoint/_chargePointID_/get/connected_vehicle/soc",
        mqttTopicChargeMode=None,
        entity_registry_enabled_default=True,
        # entity_registry_enabled_default=False,
        value_fn=lambda x: _safeJsonGet(x, "soc"),
        api_value_fn=lambda x: _safeFloat(x),
    ),
    openwbDynamicNumberEntityDescription(
        key="instant_charging_current_control",
        api_key="instant_charging_current",
        api_key_command="chargecurrent",
        name="Soll-Ladestrom (Sofortladen)",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=NumberDeviceClass.CURRENT,
        icon="mdi:current-ac",
        native_min_value=6.0,
        native_max_value=32.0,
        native_step=1.0,
        entity_category=EntityCategory.CONFIG,
        mqttTopicTemplate="{mqtt_root}/chargepoint/{chargepoint_id}/set/charge_template",
        mqttTopicCommandTemplate="{mqtt_root}/simpleAPI/set/chargepoint/{chargepoint_id}/chargecurrent",
        value_fn=lambda x: _safeNestedGet(
            x, "chargemode", "instant_charging", "current"
        ),
        api_value_fn=lambda x: _safeFloat(x),
    ),
    openwbDynamicNumberEntityDescription(
        key="pv_charging_min_current_control",
        api_key="pv_charging_min_current",
        api_key_command="minimal_permanent_current",
        name="Min. Dauerstrom (PV-Laden)",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=NumberDeviceClass.CURRENT,
        icon="mdi:current-ac",
        native_min_value=0.0,
        native_max_value=32.0,
        native_step=1.0,
        entity_category=EntityCategory.CONFIG,
        mqttTopicTemplate="{mqtt_root}/chargepoint/{chargepoint_id}/set/charge_template",
        mqttTopicCommandTemplate="{mqtt_root}/simpleAPI/set/chargepoint/{chargepoint_id}/minimal_permanent_current",
        value_fn=lambda x: _safeNestedGet(
            x, "chargemode", "pv_charging", "min_current"
        ),
        api_value_fn=lambda x: _safeFloat(x),
    ),
    openwbDynamicNumberEntityDescription(
        key="instant_charging_energy_limit_control",
        api_key="instant_charging_amount",
        api_key_command="instant_charging_amount",
        name="Energie-Limit (Sofortladen)",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=NumberDeviceClass.ENERGY,
        native_min_value=1,
        native_max_value=50,
        native_step=1,
        entity_category=EntityCategory.CONFIG,
        mqttTopicTemplate="{mqtt_root}/chargepoint/{chargepoint_id}/set/charge_template",
        mqttTopicCommandTemplate="{mqtt_root}/simpleAPI/set/instant_charging_limit_amount",
        convert_before_publish_fn=lambda x: x * 1000.0,
        value_fn=lambda x: _safeNestedGet(
            x, "chargemode", "instant_charging", "limit", "amount"
        )
        / 1000
        if _safeNestedGet(x, "chargemode", "instant_charging", "limit", "amount")
        is not None
        else None,
        api_value_fn=lambda x: _safeFloat(x, 1000),
    ),
    openwbDynamicNumberEntityDescription(
        key="instant_charging_soc_limit_control",
        api_key="instant_charging_soc",
        api_key_command="instant_charging_soc",
        name="SoC-Limit (Sofortladen)",
        native_unit_of_measurement=PERCENTAGE,
        device_class=NumberDeviceClass.BATTERY,
        native_min_value=5,
        native_max_value=100,
        native_step=5,
        entity_category=EntityCategory.CONFIG,
        mqttTopicTemplate="{mqtt_root}/chargepoint/{chargepoint_id}/set/charge_template",
        mqttTopicCommandTemplate="{mqtt_root}/simpleAPI/set/instant_charging_limit_soc",
        value_fn=lambda x: _safeNestedGet(
            x, "chargemode", "instant_charging", "limit", "soc"
        )
        if _safeNestedGet(x, "chargemode", "instant_charging", "limit", "soc")
        is not None
        else None,
        api_value_fn=lambda x: _safeFloat(x),
    ),
    openwbDynamicNumberEntityDescription(
        key="price_based_charging_max_price",
        api_key="max_price_eco",
        api_key_command="max_price_eco",
        name="Max. Preis (Strompreisbasiertes Laden)",
        native_unit_of_measurement="ct/kWh",
        device_class=None,
        icon="mdi:currency-eur",
        native_min_value=0.0,
        native_max_value=100,
        native_step=1,
        entity_category=EntityCategory.CONFIG,
        mqttTopicTemplate="{mqtt_root}/chargepoint/{chargepoint_id}/set/charge_template",
        mqttTopicCommandTemplate="{mqtt_root}/simpleAPI/set/chargepoint/{chargepoint_id}/max_price_eco",
        value_fn=lambda x: _safeFloat(
            _safeNestedGet(x, "chargemode", "eco_charging", "max_price"),
            c=100000,
            op="mult",
        )
        if _safeNestedGet(x, "chargemode", "eco_charging", "max_price") is not None
        else None,
        # convert_before_publish_fn=lambda x: x / 100000.0,
        api_value_fn=lambda x: _safeFloat(x),
    ),
]

SENSORS_PER_COUNTER = [
    openwbSensorEntityDescription(
        key="voltages",
        api_key="voltages",
        name="Spannung (L1)",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
        value_fn=lambda x: _splitListToFloat(x, 0),
    ),
    openwbSensorEntityDescription(
        key="voltages",
        api_key="voltages",
        name="Spannung (L2)",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
        value_fn=lambda x: _splitListToFloat(x, 1),
    ),
    openwbSensorEntityDescription(
        key="voltages",
        api_key="voltages",
        name="Spannung (L3)",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
        value_fn=lambda x: _splitListToFloat(x, 2),
    ),
    openwbSensorEntityDescription(
        key="power_factors",
        api_key="power_factors",
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
        api_key="power_factors",
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
        api_key="power_factors",
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
        api_key="powers",
        name="Leistung (L1)",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:transmission-tower",
        value_fn=lambda x: _splitListToFloat(x, 0),
    ),
    openwbSensorEntityDescription(
        key="powers",
        api_key="powers",
        name="Leistung (L2)",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:transmission-tower",
        value_fn=lambda x: _splitListToFloat(x, 1),
    ),
    openwbSensorEntityDescription(
        key="powers",
        api_key="powers",
        name="Leistung (L3)",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:transmission-tower",
        value_fn=lambda x: _splitListToFloat(x, 2),
    ),
    openwbSensorEntityDescription(
        key="frequency",
        api_key="frequency",
        name="Frequenz",
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        # icon="mdi:current-ac",
    ),
    openwbSensorEntityDescription(
        key="currents",
        api_key="currents",
        name="Strom (L1)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        value_fn=lambda x: _splitListToFloat(x, 0),
    ),
    openwbSensorEntityDescription(
        key="currents",
        api_key="currents",
        name="Strom (L2)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        value_fn=lambda x: _splitListToFloat(x, 1),
    ),
    openwbSensorEntityDescription(
        key="currents",
        api_key="currents",
        name="Strom (L3)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        value_fn=lambda x: _splitListToFloat(x, 2),
    ),
    openwbSensorEntityDescription(
        key="power",
        api_key="power",
        name="Leistung",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        # state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        icon="mdi:transmission-tower",
    ),
    openwbSensorEntityDescription(
        key="fault_str",
        api_key="fault_str",
        name="Fehlerbeschreibung",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: _safeStringOp(x, lambda s: s.strip('"').strip(".")[0:255]),
    ),
    openwbSensorEntityDescription(
        key="exported",
        api_key="exported",
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
        api_key="imported",
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
        api_key="daily_imported",
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
        api_key="daily_exported",
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
        api_key="fault_state",
        name="Fehler",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
]

SENSORS_PER_BATTERY = [
    openwbSensorEntityDescription(
        key="soc",
        api_key="soc",
        name="Ladung",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        # icon="mdi:transmission-tower",
    ),
    openwbSensorEntityDescription(
        key="power",
        api_key="power",
        name="Leistung",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        icon="mdi:battery-charging",
    ),
    openwbSensorEntityDescription(
        key="fault_str",
        api_key="fault_str",
        name="Fehlerbeschreibung",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: _safeStringOp(x, lambda s: s.strip('"').strip(".")[0:255]),
    ),
    openwbSensorEntityDescription(
        key="exported",
        api_key="exported",
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
        api_key="imported",
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
        api_key="daily_imported",
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
        api_key="daily_exported",
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
        api_key="fault_state",
        name="Fehler",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
]

SENSORS_PER_PVGENERATOR = [
    openwbSensorEntityDescription(
        key="daily_exported",
        api_key="daily_exported",
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
        api_key="monthly_exported",
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
        api_key="yearly_exported",
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
        api_key="exported",
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
        api_key="power",
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
        api_key="currents",
        name="Strom (L1)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        value_fn=lambda x: _splitListToFloat(x, 0),
    ),
    openwbSensorEntityDescription(
        key="currents",
        api_key="currents",
        name="Strom (L2)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        value_fn=lambda x: _splitListToFloat(x, 1),
    ),
    openwbSensorEntityDescription(
        key="currents",
        api_key="currents",
        name="Strom (L3)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        value_fn=lambda x: _splitListToFloat(x, 2),
    ),
    openwbSensorEntityDescription(
        key="fault_str",
        api_key="fault_str",
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
        api_key="fault_state",
        name="Fehler",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
]

SENSORS_CONTROLLER = [
    # System
    openwbSensorEntityDescription(
        key="system/ip_address",
        api_key=None,
        name="IP-Adresse",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:earth",
        value_fn=lambda x: _safeStringOp(x, lambda s: s.replace('"', "")),
    ),
    openwbSensorEntityDescription(
        key="system/version",
        api_key=None,
        name="Version",
        device_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:folder-clock",
        value_fn=lambda x: _safeStringOp(x, lambda s: s.replace('"', "")),
    ),
    openwbSensorEntityDescription(
        key="system/lastlivevaluesJson",
        api_key="timestamp",
        name="Datenaktualisierung",
        device_class=SensorDeviceClass.TIMESTAMP,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:clock-time-eight",
        value_fn=lambda x: _extractTimestampFromJson(x, "timestamp"),
        api_value_fn=lambda x: _extractTimestamp(x),
    ),
    openwbSensorEntityDescription(
        key="system/lastlivevaluesJson",
        api_key="grid",
        name="Netzbezug/-einspeisung",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:transmission-tower",
        value_fn=lambda x: _splitJsonLastLiveValues(x, "grid", 1000),
        api_value_fn=lambda x: _safeFloat(x, 1000, op="mult"),
    ),
    openwbSensorEntityDescription(
        key="system/lastlivevaluesJson",
        api_key="house-power",
        name="Hausverbrauch",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:home-lightning-bolt",
        value_fn=lambda x: _splitJsonLastLiveValues(x, "house-power", 1000),
        api_value_fn=lambda x: _safeFloat(x, 1000, op="mult"),
    ),
    openwbSensorEntityDescription(
        key="system/lastlivevaluesJson",
        api_key="pv-all",
        name="PV-Leistung (Gesamt)",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:solar-power",
        value_fn=lambda x: _splitJsonLastLiveValues(x, "pv-all", 1000),
        api_value_fn=lambda x: _safeFloat(x, 1000, op="mult"),
    ),
    openwbSensorEntityDescription(
        key="system/lastlivevaluesJson",
        api_key="charging-all",
        name="Ladeleistung (Gesamt)",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:car-electric-outline",
        value_fn=lambda x: _splitJsonLastLiveValues(x, "charging-all", 1000),
        api_value_fn=lambda x: _safeFloat(x, 1000, op="mult"),
    ),
    openwbSensorEntityDescription(
        key="system/lastlivevaluesJson",
        api_key="bat-all-power",
        name="Batterieleistung (Gesamt)",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:battery-charging",
        value_fn=lambda x: _splitJsonLastLiveValues(x, "bat-all-power", 1000),
        api_value_fn=lambda x: _safeFloat(x, 1000, op="mult"),
    ),
    openwbSensorEntityDescription(
        key="system/lastlivevaluesJson",
        api_key="bat-all-soc",
        name="Batterieladung (Gesamt)",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda x: _splitJsonLastLiveValues(x, "bat-all-soc", 1),
        api_value_fn=lambda x: _safeFloat(x),
    ),
]


SENSORS_PER_VEHICLE = [
    openwbSensorEntityDescription(
        key="name",
        name="Bezeichnung",
        device_class=None,
        native_unit_of_measurement=None,
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
        suggested_display_precision=0,
    ),
    openwbSensorEntityDescription(
        key="soc_timestamp",
        name="Datenaktualisierung",
        device_class=SensorDeviceClass.TIMESTAMP,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:clock-time-eight",
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

# Lock-entities per chargepoint
LOCKS_PER_CHARGEPOINT = [
    openwbLockEntityDescription(
        key="manual_lock",
        api_key="manual_lock",
        api_key_command="chargepoint_lock",
        name="Manuelle Sperre",
        entity_category=EntityCategory.CONFIG,
        translation_key="manual_lock",
        # openWB Topic-Struktur: openWB/set/chargepoint/4/set/manual_lock
        mqttTopicCommand="set/chargepoint/_chargePointID_/set/manual_lock",
        mqttTopicCurrentValue="_chargePointID_/set/manual_lock",
        api_value_map_command={"lock": "1", "unlock": "0"},
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
