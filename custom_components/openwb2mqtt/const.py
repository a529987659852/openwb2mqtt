"""The openwbmqtt component for controlling the openWB wallbox via home assistant / MQTT."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import datetime
import json
from typing import TYPE_CHECKING, Any
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
from homeassistant.const import (
    CURRENCY_EURO,
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
from homeassistant.helpers.entity import EntityCategory, EntityDescription
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

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
API_TOKEN = "api_token"
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
# Prefix of all unique IDs and entity IDs of a config entry (stored by the 1.2 migration)
ID_PREFIX = "id_prefix"

# Device types of the simpleAPI
SUPPORTED_DEVICE_TYPES = ["chargepoint", "counter", "bat", "pv", "consumer"]
# Device types that older versions of this integration supported
REMOVED_DEVICE_TYPES = ["controller", "vehicle"]
# Readable names, also used in the legacy MQTT device identifiers
DEVICE_TYPE_NAMES = {
    "chargepoint": "Chargepoint",
    "counter": "Counter",
    "bat": "Battery",
    "pv": "PV",
    "consumer": "Consumer",
}

# HTTP API (simpleAPI)
HTTP_UPDATE_INTERVAL = 15  # seconds
# Parameter that reads all values of one device, per device type
HTTP_READ_PARAMETER = {
    "chargepoint": "get_chargepoint_all",
    "counter": "get_counter",
    "bat": "get_battery",
    "pv": "get_pv",
    "consumer": "get_consumer",
}
# The answer contains the key f"{prefix}_{device_id}", per device type
HTTP_RESPONSE_PREFIX = {
    "chargepoint": "chargepoint",
    "counter": "counter",
    "bat": "battery",
    "pv": "pv",
    "consumer": "consumer",
}
# HTTP key -> MQTT topic name, so that both transports use the same value keys
HTTP_KEY_RENAMES = {
    "chargepoint": {
        "connected_vehicle_name": "vehicle_name",
        "config_name": "config/name",  # delivered by get_chargepoint_all (from chargepoint config)
        "soc": "soc/soc",
        "soc_timestamp": "pro_soc_timestamp",  # openWB Pro timestamp (get/soc_timestamp)
        "range_charged": "soc/range_charged",
        "pv_charging_min_current": "minimal_permanent_current",
        "instant_charging_amount": "instant_charging_limit_amount",
        "instant_charging_soc": "instant_charging_limit_soc",
        "pv_charging_amount": "pv_charging_limit_amount",  # delivered by get_chargepoint_all (Wh)
        "pv_charging_soc": "pv_charging_limit_soc",  # delivered by get_chargepoint_all (%)
        # "limit" is a dict, so it arrives flattened as limit/message and limit/limiting_value
        "limit/message": "control_parameter/limit/message",
        "limit/limiting_value": "control_parameter/limit/limiting_value",
    },
    "consumer": {
        "usage_type": "usage/type",
    },
}
# HTTP reads Wh, writes kWh; MQTT uses kWh both ways
HTTP_WH_KEYS = ["instant_charging_limit_amount", "pv_charging_limit_amount"]
# Both transports deliver these prices in ct/kWh (simpleAPI x100000), the entities show EUR/kWh
CENT_KEYS = ["max_price_eco"]
PRICE_UNIT = f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}"

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

# Device type selection, shared by the MQTT and the HTTP API schema
DEVICE_TYPE_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=[
            SelectOptionDict(value="counter", label="Counter"),
            SelectOptionDict(value="chargepoint", label="Chargepoint"),
            SelectOptionDict(value="pv", label="PV Generator"),
            SelectOptionDict(value="bat", label="Battery"),
            SelectOptionDict(value="consumer", label="Consumer"),
        ],
        mode=SelectSelectorMode.DROPDOWN,
        translation_key="config_selector_devicetype",  # translation is maintained in translations/<lang>.json via this translation_key
    )
)

DATA_SCHEMA_MQTT = vol.Schema(
    {
        vol.Required(MQTT_ROOT_TOPIC, default=MQTT_ROOT_TOPIC_DEFAULT): cv.string,
        vol.Required(DEVICETYPE, default="chargepoint"): DEVICE_TYPE_SELECTOR,
        vol.Required(DEVICEID, default=4): cv.positive_int,
    }
)

DATA_SCHEMA_API = vol.Schema(
    {
        vol.Required(API_PREFIX, default=MQTT_ROOT_TOPIC_DEFAULT): cv.string,
        vol.Required(API_URL): cv.string,
        vol.Optional(API_TOKEN): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Required(DEVICETYPE, default="chargepoint"): DEVICE_TYPE_SELECTOR,
        vol.Required(DEVICEID, default=4): cv.positive_int,
    }
)

# Max. charging power of the wallbox, shared by both chargepoint options schemas
WALLBOX_POWER_FIELD = {
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

DATA_SCHEMA_OPTIONS_CP_MQTT = vol.Schema(WALLBOX_POWER_FIELD)

DATA_SCHEMA_OPTIONS_CP = vol.Schema(
    {
        **WALLBOX_POWER_FIELD,
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


def _safeNumber(x: Any) -> int | float | None:
    """Convert a value to a number, but keep whole numbers from the payload as int.

    28 stays 28 (state "28", not "28.0"), everything else becomes a float.
    """
    if isinstance(x, int) and not isinstance(x, bool):
        return x
    return _safeFloat(x)


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


def _extractTimestamp(x: str) -> datetime.datetime | None:
    if x is None:
        return None
    try:
        return datetime.datetime.fromtimestamp(float(x), tz=ZoneInfo("UTC"))
    except (ValueError, TypeError):
        return None


def parse_mqtt_payload(payload: str) -> Any:
    """Turn a simpleAPI MQTT payload into a Python value.

    The payloads are mixed: JSON-quoted strings, bare strings,
    Python-style booleans (True/False) and a bare null.
    """
    # payload is a str because we subscribe with encoding="utf-8" (the default)
    text = payload.strip()
    if text in ("True", "true"):
        return True
    if text in ("False", "false"):
        return False
    if text in ("None", "null", ""):
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def flatten_api_data(data: dict[str, Any]) -> dict[str, Any]:
    """[a, b] -> key/1, key/2 and {"x": 1} -> key/x (same keys as the MQTT topics)."""
    flat: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, list):
            for index, item in enumerate(value, start=1):
                flat[f"{key}/{index}"] = item
        elif isinstance(value, dict):
            for sub_key, sub_value in value.items():
                flat[f"{key}/{sub_key}"] = sub_value
        else:
            flat[key] = value
    return flat


def normalize_http_data(data: dict[str, Any], device_type: str) -> dict[str, Any]:
    """Bring the values of one HTTP device into the same shape as the MQTT values."""
    renames = HTTP_KEY_RENAMES.get(device_type, {})
    normalized: dict[str, Any] = {}
    for key, value in flatten_api_data(data).items():
        # HTTP strings are JSON-encoded twice ("\"Kein Fehler.\"", "null"),
        # so remove one JSON layer
        if isinstance(value, str):
            value = parse_mqtt_payload(value)
        normalized[renames.get(key, key)] = value
    # HTTP returns these amounts in Wh, MQTT in kWh
    for key in HTTP_WH_KEYS:
        if key in normalized:
            normalized[key] = _kwh_from_wh(normalized[key])
    # HTTP returns these prices in ct/kWh, the entities show EUR/kWh
    for key in CENT_KEYS:
        if key in normalized:
            normalized[key] = _eur_from_cent(normalized[key])
    return normalized


def format_command_value(value: str | float | bool, for_http: bool) -> str:
    """Turn a value into the text that the openWB expects in a command."""
    if isinstance(value, bool):  # bool first: bool is a subclass of int
        if for_http:
            return "1" if value else "0"
        return "true" if value else "false"
    if isinstance(value, float):
        value = round(value, 2)  # never send 0.30000000000000004
        if value.is_integer():
            return str(int(value))  # "16" instead of "16.0"
    return str(value)


def _kwh_from_wh(value: Any) -> float | None:
    """Convert Wh to kWh."""
    return _safeFloat(value, 1000)


def _eur_from_cent(value: Any) -> float | None:
    """Convert a price in ct/kWh to EUR/kWh, rounded to 4 decimals."""
    price = _safeFloat(value, 100)
    if price is None:
        return None
    return round(price, 4)


def _shorten_text(value: Any) -> str:
    """Remove quotes and a trailing dot and cut the text to 255 characters."""
    if value is None:
        return ""
    return str(value).strip('"').strip(".")[0:255]


def _to_bool(value: Any) -> bool | None:
    """Turn True/False, "true"/"on", 1/0 and similar into a bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "on"):
            return True
        if text in ("false", "off"):
            return False
    try:
        return bool(int(value))
    except (ValueError, TypeError):
        return None


def max_current_for_wallbox_power(power: str | None) -> int:
    """Maximum charging current in A for the configured wallbox power."""
    if power == "11":
        return 16
    return 32


def get_id_prefix(entry: ConfigEntry) -> str:
    """Prefix for unique_id/entity_id. Stored by the 1.2 migration."""
    if ID_PREFIX in entry.data:
        return entry.data[ID_PREFIX]
    # Same rule as before minor version 2: HTTP used the title, MQTT the unique_id.
    # (Legacy MQTT with unique_id None produced the prefix "None"; such entries
    #  cannot be created by the config flow, so we fall back to the title.)
    communication_method = entry.data.get(COMMUNICATION_METHOD, COMM_METHOD_MQTT)
    if communication_method == COMM_METHOD_HTTP or entry.unique_id is None:
        return entry.title
    return entry.unique_id


# ---------------------------------------------------------------------------
# simpleAPI entity descriptions (HTTP and MQTT)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class OpenWBEntityDescription(EntityDescription):
    """Fields that every simpleAPI entity description shares."""

    value_key: str
    value_fn: Callable[[Any], Any] | None = None
    http_command: str | None = None
    mqtt_command: str | None = None  # below {root}/simpleAPI/, may contain {device_id}
    supports_http: bool = True
    supports_mqtt: bool = True


@dataclass(frozen=True, kw_only=True)
class OpenWBSensorEntityDescription(OpenWBEntityDescription, SensorEntityDescription):
    """Describe a simpleAPI sensor."""

    value_map: dict[Any, str] | None = None


@dataclass(frozen=True, kw_only=True)
class OpenWBBinarySensorEntityDescription(
    OpenWBEntityDescription, BinarySensorEntityDescription
):
    """Describe a simpleAPI binary sensor."""


@dataclass(frozen=True, kw_only=True)
class OpenWBNumberEntityDescription(OpenWBEntityDescription, NumberEntityDescription):
    """Describe a simpleAPI number."""

    max_from_wallbox_power: bool = False


@dataclass(frozen=True, kw_only=True)
class OpenWBSelectEntityDescription(OpenWBEntityDescription, SelectEntityDescription):
    """Describe a simpleAPI select."""

    value_map: dict[Any, str] | None = None  # API value -> option
    command_map: dict[str, str] | None = None  # option -> API value


@dataclass(frozen=True, kw_only=True)
class OpenWBLockEntityDescription(OpenWBEntityDescription, LockEntityDescription):
    """Describe a simpleAPI lock."""


def _rounded_kwh(value: Any) -> float | None:
    """Convert Wh to kWh, rounded to 3 decimals."""
    kwh = _kwh_from_wh(value)
    if kwh is None:
        return None
    return round(kwh, 3)


def _absolute_value(value: Any) -> float | None:
    """Return the value as a positive number."""
    number = _safeFloat(value)
    if number is None:
        return None
    return abs(number)


def _phase_sensors(
    value_key: str, name: str, **fields: Any
) -> list[OpenWBSensorEntityDescription]:
    """Create one sensor per phase (L1, L2, L3).

    This is the only place that uses **fields: all other fields are passed
    unchanged to every phase sensor.
    """
    sensors: list[OpenWBSensorEntityDescription] = []
    for phase in range(1, 4):
        sensors.append(  # noqa: PERF401 - a plain loop is easier to read
            OpenWBSensorEntityDescription(
                key=f"{value_key}/{phase}",
                value_key=f"{value_key}/{phase}",
                name=f"{name} (L{phase})",
                value_fn=_safeFloat,
                **fields,
            )
        )
    return sensors


CHARGEPOINT_SENSORS: list[OpenWBSensorEntityDescription] = [
    *_phase_sensors(
        "currents",
        "Strom",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
    ),
    OpenWBSensorEntityDescription(
        key="daily_imported",
        value_key="daily_imported",
        name="Geladene Energie (Heute)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:counter",
        value_fn=_rounded_kwh,
    ),
    OpenWBSensorEntityDescription(
        key="daily_exported",
        value_key="daily_exported",
        name="Entladene Energie (Heute)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:counter",
        entity_registry_enabled_default=False,
        value_fn=_rounded_kwh,
    ),
    OpenWBSensorEntityDescription(
        key="evse_current",
        # MQTT: the daemon writes get/evse_current and set/current to the same
        # topic, so the value can flip
        value_key="evse_current",
        name="Ladestromvorgabe",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        entity_registry_enabled_default=False,
        suggested_display_precision=1,
        value_fn=_safeFloat,
    ),
    OpenWBSensorEntityDescription(
        key="exported",
        value_key="exported",
        name="Entladene Energie (Gesamt)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:counter",
        entity_registry_enabled_default=False,
        suggested_display_precision=0,
        value_fn=_rounded_kwh,
    ),
    OpenWBSensorEntityDescription(
        key="fault_str",
        value_key="fault_str",
        name="Fehlerbeschreibung",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_shorten_text,
    ),
    OpenWBSensorEntityDescription(
        key="imported",
        value_key="imported",
        name="Geladene Energie (Gesamt)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:counter",
        suggested_display_precision=0,
        value_fn=_rounded_kwh,
    ),
    # No value_fn: sensor.py picks the icon from the number of phases
    OpenWBSensorEntityDescription(
        key="phases_in_use",
        value_key="phases_in_use",
        name="Aktive Phasen",
    ),
    OpenWBSensorEntityDescription(
        key="power",
        value_key="power",
        name="Ladeleistung",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:car-electric-outline",
        value_fn=_safeNumber,
    ),
    OpenWBSensorEntityDescription(
        key="state_str",
        value_key="state_str",
        name="Ladezustand",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_umlauteEinfuegen,
    ),
    *_phase_sensors(
        "voltages",
        "Spannung",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
    ),
    *_phase_sensors(
        "power_factors",
        "Leistungsfaktor",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    *_phase_sensors(
        "powers",
        "Leistung",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:car-electric-outline",
    ),
    OpenWBSensorEntityDescription(
        key="frequency",
        value_key="frequency",
        name="Frequenz",
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        value_fn=_safeFloat,
    ),
    # MQTT: config/name, HTTP: config_name
    OpenWBSensorEntityDescription(
        key="config/name",
        value_key="config/name",
        name="Ladepunkt",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_visible_default=False,
    ),
    OpenWBSensorEntityDescription(
        key="vehicle_id",
        value_key="vehicle_id",
        name="Fahrzeug-ID",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_visible_default=False,
    ),
    OpenWBSensorEntityDescription(
        key="vehicle_name",
        value_key="vehicle_name",
        name="Fahrzeug",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_visible_default=False,
    ),
    OpenWBSensorEntityDescription(
        key="charge_template_name",
        value_key="charge_template_name",
        name="Lade-Profil",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_visible_default=False,
        supports_mqtt=False,
    ),
    OpenWBSensorEntityDescription(
        key="chargemode",
        value_key="chargemode",
        name="Lademodus",
        translation_key="sensor_lademodus",
        value_map={
            "standby": "Standby",
            "stop": "Stop",
            "scheduled_charging": "Scheduled Charging",
            "time_charging": "Time Charging",
            "instant_charging": "Instant Charging",
            "pv_charging": "PV Charging",
            "eco_charging": "ECO Charging",
        },
    ),
    OpenWBSensorEntityDescription(
        key="soc/soc",
        value_key="soc/soc",
        name="Ladung",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        value_fn=_safeNumber,
    ),
    OpenWBSensorEntityDescription(
        key="soc/timestamp",
        value_key="soc/timestamp",
        name="SoC-Datenaktualisierung",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-time-eight",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_extractTimestamp,
        supports_http=False,  # HTTP has no vehicle SoC timestamp
    ),
    OpenWBSensorEntityDescription(
        key="rfid",
        value_key="rfid",
        name="Zuletzt gescannter RFID-Tag",
        icon="mdi:tag-multiple",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    OpenWBSensorEntityDescription(
        key="soc/range_charged",
        value_key="soc/range_charged",
        name="Geladene Entfernung",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        icon="mdi:map-marker-distance",
        entity_registry_enabled_default=False,
        suggested_display_precision=1,
        value_fn=_safeNumber,
    ),
    OpenWBSensorEntityDescription(
        key="instant_charging_current",
        value_key="instant_charging_current",
        name="Soll-Ladestrom (Sofortladen)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        suggested_display_precision=1,
        value_fn=_safeFloat,
        supports_mqtt=False,
    ),
    OpenWBSensorEntityDescription(
        key="minimal_permanent_current",
        value_key="minimal_permanent_current",
        name="Min. Dauerstrom (PV-Laden)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        suggested_display_precision=1,
        value_fn=_safeFloat,
    ),
    OpenWBSensorEntityDescription(
        key="max_price_eco",
        value_key="max_price_eco",
        name="Max. Preis (Strompreisbasiertes Laden)",
        native_unit_of_measurement=PRICE_UNIT,
        icon="mdi:currency-eur",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    OpenWBSensorEntityDescription(
        key="pro_soc",
        value_key="pro_soc",
        name="SoC (openWB Pro)",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        # HTTP sends 0 instead of null without an openWB Pro
        value_fn=_safeFloat,
    ),
    OpenWBSensorEntityDescription(
        key="pro_soc_timestamp",
        value_key="pro_soc_timestamp",
        name="SoC-Datenaktualisierung (openWB Pro)",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_extractTimestamp,
    ),
    OpenWBSensorEntityDescription(
        key="charging_current",
        value_key="charging_current",
        name="Ladestrom (aktuell)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value_fn=_safeFloat,
        supports_http=False,
    ),
    OpenWBSensorEntityDescription(
        key="charging_power",
        value_key="charging_power",
        name="Ladeleistung (aktuell)",
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_registry_enabled_default=False,
        value_fn=_safeFloat,
        supports_http=False,
    ),
    OpenWBSensorEntityDescription(
        key="charging_voltage",
        value_key="charging_voltage",
        name="Ladespannung (aktuell)",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        entity_registry_enabled_default=False,
        value_fn=_safeFloat,
        supports_http=False,
    ),
    OpenWBSensorEntityDescription(
        key="serial_number",
        value_key="serial_number",
        name="Seriennummer",
        entity_category=EntityCategory.DIAGNOSTIC,
        supports_http=False,
    ),
    OpenWBSensorEntityDescription(
        key="version",
        value_key="version",
        name="Version",
        entity_category=EntityCategory.DIAGNOSTIC,
        supports_http=False,
    ),
    # Both transports deliver rfid_timestamp
    OpenWBSensorEntityDescription(
        key="rfid_timestamp",
        value_key="rfid_timestamp",
        name="RFID-Zeitstempel",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_extractTimestamp,
    ),
    # Why the charging power is limited right now. Both values are null
    # (state unknown) when no limit is active.
    OpenWBSensorEntityDescription(
        key="control_parameter/limit/message",
        value_key="control_parameter/limit/message",
        name="Ladebegrenzung (Meldung)",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_shorten_text,
    ),
    # Plain text, no enum: the possible values are not defined by the simpleAPI
    OpenWBSensorEntityDescription(
        key="control_parameter/limit/limiting_value",
        value_key="control_parameter/limit/limiting_value",
        name="Ladebegrenzung (Grund)",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_shorten_text,
    ),
    # Minimum current of the active charge mode; the MQTT daemon does not publish it
    OpenWBSensorEntityDescription(
        key="min_current",
        value_key="min_current",
        name="Mindeststrom (Lademodus)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=1,
        value_fn=_safeFloat,
        supports_mqtt=False,
    ),
]

CHARGEPOINT_BINARY_SENSORS: list[OpenWBBinarySensorEntityDescription] = [
    OpenWBBinarySensorEntityDescription(
        key="plug_state",
        value_key="plug_state",
        name="Ladekabel",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=_to_bool,
    ),
    OpenWBBinarySensorEntityDescription(
        key="charge_state",
        value_key="charge_state",
        name="Autoladestatus",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=_to_bool,
    ),
    OpenWBBinarySensorEntityDescription(
        key="fault_state",
        value_key="fault_state",
        name="Fehler",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_to_bool,
    ),
]

COUNTER_SENSORS: list[OpenWBSensorEntityDescription] = [
    *_phase_sensors(
        "voltages",
        "Spannung",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
    ),
    *_phase_sensors(
        "power_factors",
        "Leistungsfaktor",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    *_phase_sensors(
        "powers",
        "Leistung",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:transmission-tower",
    ),
    OpenWBSensorEntityDescription(
        key="frequency",
        value_key="frequency",
        name="Frequenz",
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        value_fn=_safeNumber,
    ),
    *_phase_sensors(
        "currents",
        "Strom",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
    ),
    OpenWBSensorEntityDescription(
        key="power",
        value_key="power",
        name="Leistung",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:transmission-tower",
        value_fn=_safeNumber,
    ),
    OpenWBSensorEntityDescription(
        key="fault_str",
        value_key="fault_str",
        name="Fehlerbeschreibung",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_shorten_text,
    ),
    OpenWBSensorEntityDescription(
        key="exported",
        value_key="exported",
        name="Exportierte Energie (Gesamt)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:transmission-tower-export",
        suggested_display_precision=0,
        value_fn=_rounded_kwh,
    ),
    OpenWBSensorEntityDescription(
        key="imported",
        value_key="imported",
        name="Importierte Energie (Gesamt)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:transmission-tower-import",
        suggested_display_precision=0,
        value_fn=_rounded_kwh,
    ),
    OpenWBSensorEntityDescription(
        key="daily_imported",
        value_key="daily_imported",
        name="Importierte Energie (Heute)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:transmission-tower-import",
        suggested_display_precision=1,
        value_fn=_rounded_kwh,
    ),
    OpenWBSensorEntityDescription(
        key="daily_exported",
        value_key="daily_exported",
        name="Exportierte Energie (Heute)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:transmission-tower-export",
        suggested_display_precision=1,
        value_fn=_rounded_kwh,
    ),
]

COUNTER_BINARY_SENSORS: list[OpenWBBinarySensorEntityDescription] = [
    OpenWBBinarySensorEntityDescription(
        key="fault_state",
        value_key="fault_state",
        name="Fehler",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_to_bool,
    ),
]

BATTERY_SENSORS: list[OpenWBSensorEntityDescription] = [
    OpenWBSensorEntityDescription(
        key="soc",
        value_key="soc",
        name="Ladung",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=_safeNumber,
    ),
    OpenWBSensorEntityDescription(
        key="power",
        value_key="power",
        name="Leistung",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:battery-charging",
        value_fn=_safeNumber,
    ),
    OpenWBSensorEntityDescription(
        key="fault_str",
        value_key="fault_str",
        name="Fehlerbeschreibung",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_shorten_text,
    ),
    OpenWBSensorEntityDescription(
        key="exported",
        value_key="exported",
        name="Entladene Energie (Gesamt)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:battery-arrow-up",
        suggested_display_precision=0,
        value_fn=_rounded_kwh,
    ),
    OpenWBSensorEntityDescription(
        key="imported",
        value_key="imported",
        name="Geladene Energie (Gesamt)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:battery-arrow-down",
        suggested_display_precision=0,
        value_fn=_rounded_kwh,
    ),
    OpenWBSensorEntityDescription(
        key="daily_imported",
        value_key="daily_imported",
        name="Geladene Energie (Heute)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:battery-arrow-down",
        suggested_display_precision=1,
        value_fn=_rounded_kwh,
    ),
    OpenWBSensorEntityDescription(
        key="daily_exported",
        value_key="daily_exported",
        name="Entladene Energie (Heute)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:battery-arrow-up",
        suggested_display_precision=1,
        value_fn=_rounded_kwh,
    ),
    *_phase_sensors(
        "currents",
        "Strom",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        entity_registry_enabled_default=False,
    ),
]

BATTERY_BINARY_SENSORS: list[OpenWBBinarySensorEntityDescription] = [
    OpenWBBinarySensorEntityDescription(
        key="fault_state",
        value_key="fault_state",
        name="Fehler",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_to_bool,
    ),
    OpenWBBinarySensorEntityDescription(
        key="power_limit_controllable",
        value_key="power_limit_controllable",
        name="Leistungsbegrenzung steuerbar",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_to_bool,
    ),
]

PV_SENSORS: list[OpenWBSensorEntityDescription] = [
    OpenWBSensorEntityDescription(
        key="daily_exported",
        value_key="daily_exported",
        name="Zählerstand (Heute)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:counter",
        suggested_display_precision=1,
        value_fn=_rounded_kwh,
    ),
    OpenWBSensorEntityDescription(
        key="monthly_exported",
        value_key="monthly_exported",
        name="Zählerstand (Monat)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:counter",
        suggested_display_precision=0,
        value_fn=_rounded_kwh,
    ),
    OpenWBSensorEntityDescription(
        key="yearly_exported",
        value_key="yearly_exported",
        name="Zählerstand (Jahr)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:counter",
        suggested_display_precision=0,
        value_fn=_rounded_kwh,
    ),
    OpenWBSensorEntityDescription(
        key="exported",
        value_key="exported",
        name="Zählerstand (Gesamt)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:counter",
        suggested_display_precision=0,
        value_fn=_rounded_kwh,
    ),
    OpenWBSensorEntityDescription(
        key="power",
        value_key="power",
        name="Leistung",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:solar-power",
        suggested_display_precision=0,
        value_fn=_absolute_value,
    ),
    *_phase_sensors(
        "currents",
        "Strom",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
    ),
    OpenWBSensorEntityDescription(
        key="fault_str",
        value_key="fault_str",
        name="Fehlerbeschreibung",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_shorten_text,
    ),
    # get_pv has no imported; only the separate get_pv_imported (would need a 2nd request)
    OpenWBSensorEntityDescription(
        key="imported",
        value_key="imported",
        name="Importierte Energie (Gesamt)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:transmission-tower-import",
        entity_registry_enabled_default=False,
        suggested_display_precision=0,
        value_fn=_rounded_kwh,
        supports_http=False,
    ),
]

PV_BINARY_SENSORS: list[OpenWBBinarySensorEntityDescription] = [
    OpenWBBinarySensorEntityDescription(
        key="fault_state",
        value_key="fault_state",
        name="Fehler",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_to_bool,
    ),
]

CONSUMER_SENSORS: list[OpenWBSensorEntityDescription] = [
    OpenWBSensorEntityDescription(
        key="power",
        value_key="power",
        name="Leistung",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:power-plug",
        value_fn=_safeNumber,
    ),
    *_phase_sensors(
        "powers",
        "Leistung",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_registry_enabled_default=False,
    ),
    *_phase_sensors(
        "currents",
        "Strom",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        entity_registry_enabled_default=False,
    ),
    *_phase_sensors(
        "voltages",
        "Spannung",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
        entity_registry_enabled_default=False,
    ),
    OpenWBSensorEntityDescription(
        key="imported",
        value_key="imported",
        name="Importierte Energie (Gesamt)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=0,
        value_fn=_rounded_kwh,
    ),
    OpenWBSensorEntityDescription(
        key="exported",
        value_key="exported",
        name="Exportierte Energie (Gesamt)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        entity_registry_enabled_default=False,
        suggested_display_precision=0,
        value_fn=_rounded_kwh,
    ),
    OpenWBSensorEntityDescription(
        key="daily_imported",
        value_key="daily_imported",
        name="Importierte Energie (Heute)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=_rounded_kwh,
    ),
    # No value_fn: sensor.py picks the icon from the number of phases
    OpenWBSensorEntityDescription(
        key="phases_in_use",
        value_key="phases_in_use",
        name="Aktive Phasen",
    ),
    OpenWBSensorEntityDescription(
        key="state_str",
        value_key="state_str",
        name="Status",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_umlauteEinfuegen,
    ),
    OpenWBSensorEntityDescription(
        key="fault_str",
        value_key="fault_str",
        name="Fehlerbeschreibung",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_shorten_text,
    ),
    OpenWBSensorEntityDescription(
        key="usage/type",
        value_key="usage/type",
        name="Verwendungsart",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
]

CONSUMER_BINARY_SENSORS: list[OpenWBBinarySensorEntityDescription] = [
    OpenWBBinarySensorEntityDescription(
        key="charge_state",
        value_key="charge_state",
        name="Aktiv",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=_to_bool,
    ),
    OpenWBBinarySensorEntityDescription(
        key="fault_state",
        value_key="fault_state",
        name="Fehler",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_to_bool,
    ),
]

# Option lists of the limit selects ("Begrenzung"), shared by Sofortladen and PV-Laden
LIMIT_OPTIONS = ["Keine", "SoC", "Energiemenge"]
LIMIT_VALUE_MAP = {"none": "Keine", "soc": "SoC", "amount": "Energiemenge"}
LIMIT_COMMAND_MAP = {"Keine": "none", "SoC": "soc", "Energiemenge": "amount"}

CHARGEPOINT_NUMBERS: list[OpenWBNumberEntityDescription] = [
    OpenWBNumberEntityDescription(
        key="manual_soc",
        value_key="soc/soc",
        name="Aktueller SoC (Manuelles SoC Modul)",
        http_command="manual_soc",
        supports_mqtt=False,
        native_unit_of_measurement=PERCENTAGE,
        device_class=NumberDeviceClass.BATTERY,
        native_min_value=0.0,
        native_max_value=100.0,
        native_step=1.0,
        entity_category=EntityCategory.CONFIG,
        value_fn=_safeFloat,
    ),
    OpenWBNumberEntityDescription(
        key="instant_charging_current_control",
        value_key="instant_charging_current",  # MQTT: shows the last sent value
        name="Soll-Ladestrom (Sofortladen)",
        http_command="chargecurrent",
        mqtt_command="set/chargepoint/{device_id}/chargecurrent",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=NumberDeviceClass.CURRENT,
        icon="mdi:current-ac",
        native_min_value=6.0,
        native_max_value=32.0,
        native_step=1.0,
        entity_category=EntityCategory.CONFIG,
        max_from_wallbox_power=True,
        value_fn=_safeFloat,
    ),
    OpenWBNumberEntityDescription(
        key="pv_charging_min_current_control",
        value_key="minimal_permanent_current",
        name="Min. Dauerstrom (PV-Laden)",
        http_command="minimal_permanent_current",
        mqtt_command="set/chargepoint/{device_id}/minimal_permanent_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=NumberDeviceClass.CURRENT,
        icon="mdi:current-ac",
        native_min_value=0.0,
        native_max_value=32.0,
        native_step=1.0,
        entity_category=EntityCategory.CONFIG,
        max_from_wallbox_power=True,
        value_fn=_safeFloat,
    ),
    OpenWBNumberEntityDescription(
        key="instant_charging_energy_limit_control",
        value_key="instant_charging_limit_amount",
        name="Energie-Limit (Sofortladen)",
        http_command="instant_charging_amount",
        # API converts kWh -> Wh itself; MQTT: acts on the lowest chargepoint ID
        mqtt_command="set/instant_charging_limit_amount",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=NumberDeviceClass.ENERGY,
        native_min_value=1,
        native_max_value=50,
        native_step=1,
        entity_category=EntityCategory.CONFIG,
        value_fn=_safeFloat,
    ),
    OpenWBNumberEntityDescription(
        key="instant_charging_soc_limit_control",
        value_key="instant_charging_limit_soc",
        name="SoC-Limit (Sofortladen)",
        http_command="instant_charging_soc",
        mqtt_command="set/instant_charging_limit_soc",  # MQTT: acts on the lowest chargepoint ID
        native_unit_of_measurement=PERCENTAGE,
        device_class=NumberDeviceClass.BATTERY,
        # API accepts 0..100; HA keeps 5..100 step 5
        native_min_value=5,
        native_max_value=100,
        native_step=5,
        entity_category=EntityCategory.CONFIG,
        value_fn=_safeFloat,
    ),
    OpenWBNumberEntityDescription(
        key="price_based_charging_max_price",
        value_key="max_price_eco",
        name="Max. Preis (Strompreisbasiertes Laden)",
        # Both set commands take ct/kWh; the coordinators convert from/to EUR/kWh
        http_command="max_price_eco",
        mqtt_command="set/chargepoint/{device_id}/max_price_eco",
        native_unit_of_measurement=PRICE_UNIT,
        icon="mdi:currency-eur",
        native_min_value=-1.0,
        native_max_value=2.0,
        native_step=0.01,
        entity_category=EntityCategory.CONFIG,
        value_fn=_safeFloat,
    ),
    OpenWBNumberEntityDescription(
        key="minimal_pv_soc",
        # HTTP has no getter (write only), so HTTP shows the last sent value;
        # MQTT reads minimal_pv_soc
        value_key="minimal_pv_soc",
        name="Min. SoC (PV-Laden)",
        http_command="minimal_pv_soc",
        mqtt_command="set/chargepoint/{device_id}/minimal_pv_soc",
        native_unit_of_measurement=PERCENTAGE,
        device_class=NumberDeviceClass.BATTERY,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        entity_category=EntityCategory.CONFIG,
        value_fn=_safeFloat,
    ),
    OpenWBNumberEntityDescription(
        key="pv_charging_limit_soc",
        value_key="pv_charging_limit_soc",  # read on both transports
        name="SoC-Limit (PV-Laden)",
        http_command="pv_charging_soc",
        mqtt_command="set/pv_charging_limit_soc",  # MQTT: acts on the lowest chargepoint ID
        native_unit_of_measurement=PERCENTAGE,
        device_class=NumberDeviceClass.BATTERY,
        # API accepts 0..100; HA keeps 5..100 step 5
        native_min_value=5,
        native_max_value=100,
        native_step=5,
        entity_category=EntityCategory.CONFIG,
        value_fn=_safeFloat,
    ),
    OpenWBNumberEntityDescription(
        key="pv_charging_limit_amount",
        value_key="pv_charging_limit_amount",  # read on both transports
        name="Energie-Limit (PV-Laden)",
        http_command="pv_charging_amount",
        mqtt_command="set/pv_charging_limit_amount",  # MQTT: acts on the lowest chargepoint ID
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=NumberDeviceClass.ENERGY,
        native_min_value=1,
        native_max_value=50,
        native_step=1,
        entity_category=EntityCategory.CONFIG,
        value_fn=_safeFloat,
    ),
]

BATTERY_NUMBERS: list[OpenWBNumberEntityDescription] = [
    OpenWBNumberEntityDescription(
        key="bat_power_reserve",
        value_key="bat_power_reserve",  # no read value: shows the last sent value
        name="Reservierte Speicherleistung",
        http_command="bat_power_reserve",
        mqtt_command="set/bat_power_reserve",  # global
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=NumberDeviceClass.POWER,
        # API: integer W >= 0, no upper limit; 10000 is our own bound
        native_min_value=0,
        native_max_value=10000,
        native_step=100,
        entity_category=EntityCategory.CONFIG,
        value_fn=_safeFloat,
    ),
]

CHARGEPOINT_SELECTS: list[OpenWBSelectEntityDescription] = [
    OpenWBSelectEntityDescription(
        key="instant_charging_limitation",
        value_key="instant_charging_limit",
        name="Begrenzung (Sofortladen)",
        http_command="instant_charging_limit",
        mqtt_command="set/instant_charging_limit",  # acts on the lowest chargepoint ID
        translation_key="selector_chargepoint_dynamic_chargemode",
        entity_category=EntityCategory.CONFIG,
        options=LIMIT_OPTIONS,
        value_map=LIMIT_VALUE_MAP,
        command_map=LIMIT_COMMAND_MAP,
    ),
    OpenWBSelectEntityDescription(
        key="chargemode",
        value_key="chargemode",
        name="Lademodus",
        http_command="set_chargemode",
        mqtt_command="set/chargepoint/{device_id}/chargemode",
        translation_key="selector_chargepoint_chargemode",
        entity_category=EntityCategory.CONFIG,
        # No "Standby": it cannot be set, so the state is unknown during standby
        options=[
            "Instant Charging",
            "PV Charging",
            "ECO Charging",
            "Target Charging",
            "Stop",
        ],
        # Read values are the long names; the short names are only aliases
        # of the set commands
        value_map={
            "instant_charging": "Instant Charging",
            "instant": "Instant Charging",
            "pv_charging": "PV Charging",
            "pv": "PV Charging",
            "eco_charging": "ECO Charging",
            "eco": "ECO Charging",
            "scheduled_charging": "Target Charging",
            "target": "Target Charging",
            "stop": "Stop",
        },
        command_map={
            "Instant Charging": "instant",
            "PV Charging": "pv",
            "ECO Charging": "eco",
            "Target Charging": "target",
            "Stop": "stop",
        },
    ),
    OpenWBSelectEntityDescription(
        key="connected_vehicle",
        value_key="vehicle_name",
        name="Angeschlossenes Fahrzeug",
        # The options are the vehicle names from the options flow; the
        # command sends the id of the chosen vehicle
        http_command="vehicle",
        supports_mqtt=False,
        translation_key="selector_connected_vehicle",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    OpenWBSelectEntityDescription(
        key="pv_charging_limit",
        value_key="pv_charging_limit",  # read on both transports
        name="Begrenzung (PV-Laden)",
        http_command="pv_charging_limit",
        mqtt_command="set/pv_charging_limit",  # acts on the lowest chargepoint ID
        entity_category=EntityCategory.CONFIG,
        options=LIMIT_OPTIONS,
        value_map=LIMIT_VALUE_MAP,
        command_map=LIMIT_COMMAND_MAP,
    ),
]

BATTERY_SELECTS: list[OpenWBSelectEntityDescription] = [
    OpenWBSelectEntityDescription(
        key="bat_mode",
        value_key="bat_mode",  # no read value: shows the last sent value
        name="Speicherbeachtung",
        http_command="bat_mode",
        mqtt_command="set/bat_mode",  # global
        entity_category=EntityCategory.CONFIG,
        options=["Speicher-Mindest-SoC", "Fahrzeuge", "Speicher"],
        value_map={
            "min_soc_bat_mode": "Speicher-Mindest-SoC",
            "ev_mode": "Fahrzeuge",
            "bat_mode": "Speicher",
        },
        command_map={
            "Speicher-Mindest-SoC": "min_soc_bat_mode",
            "Fahrzeuge": "ev_mode",
            "Speicher": "bat_mode",
        },
    ),
]

CHARGEPOINT_LOCKS: list[OpenWBLockEntityDescription] = [
    OpenWBLockEntityDescription(
        key="manual_lock",
        value_key="manual_lock",  # read: manual_lock (from set/manual_lock)
        name="Manuelle Sperre",
        http_command="chargepoint_lock",  # 1 / 0
        mqtt_command="set/chargepoint/{device_id}/chargepoint_lock",  # true / false
        translation_key="manual_lock",
        entity_category=EntityCategory.CONFIG,
        value_fn=_to_bool,
    ),
]

# Which descriptions belong to which device type ("chargepoint", "counter", "bat", "pv",
# "consumer").
# An empty list means the device type has no entities of that platform.
SENSORS_BY_DEVICE_TYPE: dict[str, list[OpenWBSensorEntityDescription]] = {
    "chargepoint": CHARGEPOINT_SENSORS,
    "counter": COUNTER_SENSORS,
    "bat": BATTERY_SENSORS,
    "pv": PV_SENSORS,
    "consumer": CONSUMER_SENSORS,
}

BINARY_SENSORS_BY_DEVICE_TYPE: dict[str, list[OpenWBBinarySensorEntityDescription]] = {
    "chargepoint": CHARGEPOINT_BINARY_SENSORS,
    "counter": COUNTER_BINARY_SENSORS,
    "bat": BATTERY_BINARY_SENSORS,
    "pv": PV_BINARY_SENSORS,
    "consumer": CONSUMER_BINARY_SENSORS,
}

NUMBERS_BY_DEVICE_TYPE: dict[str, list[OpenWBNumberEntityDescription]] = {
    "chargepoint": CHARGEPOINT_NUMBERS,
    "counter": [],
    "bat": BATTERY_NUMBERS,
    "pv": [],
    "consumer": [],
}

SELECTS_BY_DEVICE_TYPE: dict[str, list[OpenWBSelectEntityDescription]] = {
    "chargepoint": CHARGEPOINT_SELECTS,
    "counter": [],
    "bat": BATTERY_SELECTS,
    "pv": [],
    "consumer": [],
}

LOCKS_BY_DEVICE_TYPE: dict[str, list[OpenWBLockEntityDescription]] = {
    "chargepoint": CHARGEPOINT_LOCKS,
    "counter": [],
    "bat": [],
    "pv": [],
    "consumer": [],
}
