"""The openwbmqtt component for controlling the openWB wallbox via home assistant / MQTT."""

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_VERIFY_SSL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api_client import (
    OpenWB2MqttApiClient,
    OpenWB2MqttApiClientCommunicationError,
    OpenWB2MqttApiClientError,
)
from .common import get_vehicles

# Import global values.
from .const import (
    API_PREFIX,
    API_TOKEN,
    API_URL,
    COMM_METHOD_HTTP,
    COMM_METHOD_MQTT,
    COMMUNICATION_METHOD,
    CONF_VEHICLES,
    CONF_WALLBOX_POWER,
    DATA_SCHEMA,
    DATA_SCHEMA_API,
    DATA_SCHEMA_MQTT,
    DATA_SCHEMA_OPTIONS_CP,
    DATA_SCHEMA_OPTIONS_CP_MQTT,
    DATA_SCHEMA_RECONFIGURE_API,
    DEVICEID,
    DEVICETYPE,
    DOMAIN,
    HTTP_RESPONSE_PREFIX,
    ID_PREFIX,
    MQTT_ROOT_TOPIC,
    MQTT_ROOT_TOPIC_DEFAULT,
)


def _parse_vehicles_string(vehicles_str: str | None) -> dict[str, str]:
    """Parse a comma-separated string of ID=Name pairs into a dictionary."""
    if not vehicles_str:
        return {}
    try:
        vehicles = {}
        for item in vehicles_str.split(","):
            vid, name = item.split("=")
            vid = vid.strip()
            name = name.strip()
            if vid in vehicles:
                raise ValueError(f"Duplicate vehicle ID: {vid}")
            if name in vehicles.values():
                raise ValueError(f"Duplicate vehicle name: {name}")
            vehicles[vid] = name
        return vehicles
    except IndexError as exc:
        raise ValueError("Invalid vehicle format. Expected ID=Name.") from exc


def _format_vehicles_dict(vehicles_dict: dict[str, str]) -> str:
    """Format a dictionary of vehicles into a comma-separated string."""
    if not vehicles_dict:
        return ""
    return ", ".join([f"{vid}={name}" for vid, name in vehicles_dict.items()])


class openwbmqttConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configuration flow for the configuration of the openWB integration.

    When custom component is added by the user, they must provide
    - MQTT root topic
    - Device type
    - Device ID
    --> See DATA_SCHEMA.
    """

    VERSION = 1
    MINOR_VERSION = 2

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.stored_user_input: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowHandler:
        """Get the options flow for this handler."""
        return OptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step."""
        if user_input is not None:
            self.stored_user_input = user_input
            comm_method = user_input[COMMUNICATION_METHOD]
            if comm_method == COMM_METHOD_HTTP:
                return await self.async_step_details_api()
            return await self.async_step_details_mqtt()

        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA)

    async def async_step_details_api(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the details step of the configuration for API communication."""
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self._async_check_api(user_input)
            if error is not None:
                errors["base"] = error

        return await self._async_step_details(
            user_input,
            "details_api",
            DATA_SCHEMA_API,
            {API_URL: "http://openwb.local/openWB/simpleAPI/simpleapi.php"},
            errors,
        )

    async def async_step_details_mqtt(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the details step of the configuration for MQTT communication."""
        if not self.hass.config_entries.async_entries("mqtt"):
            return self.async_abort(reason="mqtt_not_configured")

        return await self._async_step_details(
            user_input,
            "details_mqtt",
            DATA_SCHEMA_MQTT,
            {MQTT_ROOT_TOPIC: MQTT_ROOT_TOPIC_DEFAULT},
            {},
        )

    async def _async_check_api(self, user_input: dict[str, Any]) -> str | None:
        """Check the HTTP API and the device ID. Return an error key or None.

        The check is tolerant: only a failed connection or a device ID that
        is clearly missing in the openWB answer is an error.
        """
        api_client = OpenWB2MqttApiClient(
            api_url=user_input[API_URL],
            token=user_input.get(API_TOKEN),
            session=async_get_clientsession(
                self.hass, verify_ssl=user_input.get(CONF_VERIFY_SSL, True)
            ),
        )
        try:
            components = await api_client.async_get_data({"list_components": "all"})
        except OpenWB2MqttApiClientCommunicationError:
            return "cannot_connect"
        except OpenWB2MqttApiClientError:
            # For example an older openWB without list_components
            return None

        if not isinstance(components, dict):
            return None

        # The answer uses "battery" for the device type "bat"
        response_key = HTTP_RESPONSE_PREFIX[user_input[DEVICETYPE]]
        id_list = components.get(response_key)
        if not isinstance(id_list, list):
            return None

        known_ids = [str(device_id) for device_id in id_list]
        if str(user_input[DEVICEID]) not in known_ids:
            return "unknown_device_id"
        return None

    async def _async_step_details(
        self,
        user_input: dict[str, Any] | None,
        step_id: str,
        data_schema: vol.Schema,
        suggested_values: dict[str, Any],
        errors: dict[str, str],
    ) -> ConfigFlowResult:
        """Handle the details step of the configuration."""
        if user_input is not None and not errors:
            self.stored_user_input.update(user_input)
            if self.stored_user_input.get(DEVICETYPE) == "chargepoint":
                return await self.async_step_chargepoint()

            title = self._get_title(self.stored_user_input)
            await self.async_set_unique_id(title)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=title,
                data={**self.stored_user_input, ID_PREFIX: title},
            )

        if user_input is not None:
            # Show the form again with the values the user entered
            suggested_values = user_input

        data_schema = self.add_suggested_values_to_schema(data_schema, suggested_values)

        return self.async_show_form(
            step_id=step_id,
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_chargepoint(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the chargepoint step of the configuration."""
        errors: dict[str, str] = {}
        comm_method = self.stored_user_input.get(COMMUNICATION_METHOD)

        if comm_method == COMM_METHOD_MQTT:
            data_schema = DATA_SCHEMA_OPTIONS_CP_MQTT
        else:
            data_schema = DATA_SCHEMA_OPTIONS_CP

        if user_input is not None:
            combined_data = {**self.stored_user_input, **user_input}
            title = self._get_title(combined_data)
            await self.async_set_unique_id(title)
            self._abort_if_unique_id_configured()

            # vehicle list as provided by the user (1=Standard-Fahrzeug, 2=Fahrzeug (2))
            vehicle_list = user_input.get(CONF_VEHICLES)
            try:
                # string -> dict{1=Standard-Fahrzeug, 2=Fahrzeug (2))}
                combined_data[CONF_VEHICLES] = _parse_vehicles_string(vehicle_list)
            except ValueError:
                errors["base"] = "invalid_vehicle_list"
            else:
                combined_data[ID_PREFIX] = title
                return self.async_create_entry(
                    title=title,
                    data=combined_data,
                )

            data_schema = self.add_suggested_values_to_schema(data_schema, user_input)

        return self.async_show_form(
            step_id="chargepoint",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the connection of an HTTP entry, e.g. after a new IP address.

        Ported from PR #98. Only API URL, token and SSL check can be changed.
        Prefix, device type and device ID define the entity IDs, so they stay.
        """
        entry = self._get_reconfigure_entry()

        # Old v0.3.x entries have no communication method and are MQTT entries.
        # For MQTT, the connection is managed by the MQTT integration.
        if entry.data.get(COMMUNICATION_METHOD, COMM_METHOD_MQTT) != COMM_METHOD_HTTP:
            return self.async_abort(reason="reconfigure_not_supported_mqtt")

        errors: dict[str, str] = {}
        if user_input is not None:
            new_data = dict(entry.data)
            new_data[API_URL] = user_input[API_URL].strip()
            new_data[CONF_VERIFY_SSL] = user_input.get(CONF_VERIFY_SSL, True)
            token = user_input.get(API_TOKEN)
            if token:
                new_data[API_TOKEN] = token
            else:
                # An empty token field removes the token
                new_data.pop(API_TOKEN, None)

            # Same check as in the config flow: connection and device ID
            error = await self._async_check_api(new_data)
            if error is not None:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(entry, data=new_data)

        if user_input is not None:
            suggested_values = user_input
        else:
            suggested_values = {
                API_URL: entry.data.get(API_URL, ""),
                API_TOKEN: entry.data.get(API_TOKEN, ""),
                CONF_VERIFY_SSL: entry.data.get(CONF_VERIFY_SSL, True),
            }
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                DATA_SCHEMA_RECONFIGURE_API, suggested_values
            ),
            errors=errors,
            description_placeholders={
                "entry_title": entry.title,
                "example_url": "http://openwb.local/openWB/simpleAPI/simpleapi.php",
            },
        )

    def _get_title(self, user_input: dict[str, Any]) -> str:
        """Get the title for the config entry."""
        if user_input.get(COMMUNICATION_METHOD) == COMM_METHOD_MQTT:
            prefix = user_input[MQTT_ROOT_TOPIC]
        else:
            prefix = user_input[API_PREFIX]

        return f"{prefix}-{user_input[DEVICETYPE]}-{user_input[DEVICEID]}"


class OptionsFlowHandler(OptionsFlowWithReload):
    """Handle an options flow for openWB2 MQTT."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        # Currently, only the chargepoint offers options
        if self.config_entry.data.get(DEVICETYPE) != "chargepoint":
            return self.async_abort(reason="no_conf_options_supported")

        comm_method = self.config_entry.data.get(COMMUNICATION_METHOD, COMM_METHOD_MQTT)
        if comm_method == COMM_METHOD_MQTT:
            data_schema = DATA_SCHEMA_OPTIONS_CP_MQTT
        else:
            data_schema = DATA_SCHEMA_OPTIONS_CP

        # Create the entry with user input
        if user_input is not None:
            # vehicle list as provided by the user (1=Standard-Fahrzeug, 2=Fahrzeug (2))
            vehicle_list = user_input.get(CONF_VEHICLES)
            try:
                # string -> dict{1=Standard-Fahrzeug, 2=Fahrzeug (2))}
                vehicles = _parse_vehicles_string(vehicle_list)
            except ValueError:
                errors["base"] = "invalid_vehicle_list"
            else:
                user_input[CONF_VEHICLES] = vehicles
                return self.async_create_entry(title="", data=user_input)

            # Show the form again with the values the user entered
            data_schema = self.add_suggested_values_to_schema(data_schema, user_input)
            return self.async_show_form(
                step_id="init", data_schema=data_schema, errors=errors
            )

        # Otherwise show a form to the user and ask for configuration options
        # Propose the current values. Before the options flow was saved once,
        # they are only in the entry data (from the config flow).
        entry = self.config_entry
        wallbox_power = entry.options.get(
            CONF_WALLBOX_POWER, entry.data.get(CONF_WALLBOX_POWER)
        )
        suggested_values: dict[str, Any] = {CONF_WALLBOX_POWER: wallbox_power}
        current_options_carlist = get_vehicles(entry)

        if len(current_options_carlist) > 0:
            # Convert dict -> string for output
            current_options_carlist_str = _format_vehicles_dict(current_options_carlist)
            suggested_values[CONF_VEHICLES] = current_options_carlist_str

        data_schema = self.add_suggested_values_to_schema(data_schema, suggested_values)

        return self.async_show_form(step_id="init", data_schema=data_schema)
