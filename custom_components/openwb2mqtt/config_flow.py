"""The openwbmqtt component for controlling the openWB wallbox via home assistant / MQTT."""

from __future__ import annotations

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api_client import (
    OpenWB2MqttApiClient,
    OpenWB2MqttApiClientCommunicationError,
    OpenWB2MqttApiClientError,
)

# Import global values.
from .const import (
    API_PREFIX,
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
    MQTT_ROOT_TOPIC,
    MQTT_ROOT_TOPIC_DEFAULT,
)


def _parse_vehicles_string(vehicles_str: str) -> dict[str, str]:
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


async def _async_validate_api_url(hass: HomeAssistant, api_url: str) -> None:
    """Check that the openWB simpleAPI answers under the given URL.

    Raises OpenWB2MqttApiClientCommunicationError if the host is unreachable or
    answers with an HTTP error, OpenWB2MqttApiClientError for anything else
    (e.g. the response is not JSON, i.e. the URL does not point to the simpleAPI).
    """
    client = OpenWB2MqttApiClient(
        api_url=api_url,
        token=None,
        session=async_get_clientsession(hass),
    )
    # Lightweight query that is supported regardless of the configured device type
    await client.async_get_data("?get_lastlivevaluesjson&raw=true")


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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowHandler:
        """Get the options flow for this handler."""
        return OptionsFlowHandler()

    async def async_step_user(self, user_input=None):
        """Handle the user step."""
        if user_input is not None:
            self.stored_user_input = user_input
            comm_method = user_input[COMMUNICATION_METHOD]
            if comm_method == COMM_METHOD_HTTP:
                return await self.async_step_details_api()
            else:
                return await self.async_step_details_mqtt()

        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA)

    async def async_step_details_api(self, user_input=None):
        """Handle the details step of the configuration for API communication."""
        return await self._async_step_details(
            user_input,
            "details_api",
            DATA_SCHEMA_API,
            {"api_url": "http://192.168.0.68/openWB/simpleAPI/simpleapi.php"},
        )

    async def async_step_details_mqtt(self, user_input=None):
        """Handle the details step of the configuration for MQTT communication."""
        return await self._async_step_details(
            user_input,
            "details_mqtt",
            DATA_SCHEMA_MQTT,
            {MQTT_ROOT_TOPIC: MQTT_ROOT_TOPIC_DEFAULT},
        )

    async def _async_step_details(
        self, user_input, step_id, data_schema, suggested_values
    ):
        """Handle the details step of the configuration."""
        errors = {}

        if user_input is not None:
            self.stored_user_input.update(user_input)
            if self.stored_user_input.get(DEVICETYPE) == "chargepoint":
                return await self.async_step_chargepoint()

            title = self._get_title(self.stored_user_input)
            await self.async_set_unique_id(title)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=title,
                data=self.stored_user_input,
            )

        data_schema = self.add_suggested_values_to_schema(data_schema, suggested_values)

        return self.async_show_form(
            step_id=step_id,
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_chargepoint(self, user_input=None):
        """Handle the chargepoint step of the configuration."""
        errors = {}
        comm_method = self.stored_user_input.get(COMMUNICATION_METHOD)

        if user_input is not None:
            combined_data = {**self.stored_user_input, **user_input}
            title = self._get_title(combined_data)
            await self.async_set_unique_id(title)
            self._abort_if_unique_id_configured()

            # vehicle list as provided by the user (1=Standard-Fahrzeug, 2=Fahrzeug (2))
            vehicle_list = user_input.get(CONF_VEHICLES)
            # string -> dict{1=Standard-Fahrzeug, 2=Fahrzeug (2))}
            combined_data[CONF_VEHICLES] = _parse_vehicles_string(vehicle_list)

            return self.async_create_entry(
                title=title,
                data=combined_data,
            )

        if comm_method == COMM_METHOD_MQTT:
            return self.async_show_form(
                step_id="chargepoint",
                data_schema=DATA_SCHEMA_OPTIONS_CP_MQTT,
                errors=errors,
            )
        else:
            return self.async_show_form(
                step_id="chargepoint",
                data_schema=DATA_SCHEMA_OPTIONS_CP,
                errors=errors,
            )

    async def async_step_reconfigure(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing entry.

        Only connection parameters can be changed here. API prefix / MQTT root
        topic, device type and device id make up the unique_id of the entry
        (and thus of all entities); changing them would orphan the existing
        entities, so a new entry is required for that.
        """
        entry = self._get_reconfigure_entry()

        # For MQTT, the connection itself is handled by the HA MQTT integration;
        # the only remaining fields (root topic, device type/id) define the identity.
        if entry.data.get(COMMUNICATION_METHOD) != COMM_METHOD_HTTP:
            return self.async_abort(reason="reconfigure_not_supported_mqtt")

        errors: dict[str, str] = {}

        if user_input is not None:
            api_url = user_input[API_URL].strip()
            try:
                await _async_validate_api_url(self.hass, api_url)
            except OpenWB2MqttApiClientCommunicationError:
                errors["base"] = "cannot_connect"
            except OpenWB2MqttApiClientError:
                errors["base"] = "invalid_api_response"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={API_URL: api_url},
                )

        suggested_values = user_input or {API_URL: entry.data.get(API_URL, "")}
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                DATA_SCHEMA_RECONFIGURE_API, suggested_values
            ),
            errors=errors,
            description_placeholders={"entry_title": entry.title},
        )

    def _get_title(self, user_input: dict) -> str:
        """Get the title for the config entry."""
        if user_input.get(COMMUNICATION_METHOD) == COMM_METHOD_MQTT:
            prefix = user_input[MQTT_ROOT_TOPIC]
        else:
            prefix = user_input[API_PREFIX]

        if user_input[DEVICETYPE] == "controller":
            return f"{prefix}-{user_input[DEVICETYPE]}"
        return f"{prefix}-{user_input[DEVICETYPE]}-{user_input[DEVICEID]}"


class OptionsFlowHandler(OptionsFlowWithReload):
    """Handle an options flow for openWB2 MQTT."""

    async def async_step_init(self, user_input=None):
        """Manage the options."""

        # Currently, only the chargepoint offers options
        if self.config_entry.data.get(DEVICETYPE) != "chargepoint":
            return self.async_abort(reason="no_conf_options_supported")

        # Create the entry with user input
        if user_input is not None:
            # vehicle list as provided by the user (1=Standard-Fahrzeug, 2=Fahrzeug (2))
            vehicle_list = user_input.get(CONF_VEHICLES)
            # string -> dict{1=Standard-Fahrzeug, 2=Fahrzeug (2))}
            user_input[CONF_VEHICLES] = _parse_vehicles_string(vehicle_list)
            return self.async_create_entry(title="", data=user_input)

        # Otherwise show a form to the user and ask for configuration options
        # If there are options currently configured, propose them.
        wallbox_power = self.config_entry.options.get(CONF_WALLBOX_POWER)
        suggested_values = {CONF_WALLBOX_POWER: wallbox_power}
        current_options_carlist = self.config_entry.options.get(CONF_VEHICLES, {})
        comm_method = self.config_entry.data.get(COMMUNICATION_METHOD)

        if len(current_options_carlist) > 0:
            # Convert dict -> string for output
            current_options_carlist_str = _format_vehicles_dict(current_options_carlist)
            suggested_values[CONF_VEHICLES] = current_options_carlist_str

        if comm_method == COMM_METHOD_MQTT:
            data_schema = self.add_suggested_values_to_schema(
                DATA_SCHEMA_OPTIONS_CP_MQTT, suggested_values
            )
        else:
            data_schema = self.add_suggested_values_to_schema(
                DATA_SCHEMA_OPTIONS_CP, suggested_values
            )

        return self.async_show_form(step_id="init", data_schema=data_schema)
