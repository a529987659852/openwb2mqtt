"""The openwbmqtt component for controlling the openWB wallbox via home assistant / MQTT."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback

# Import global values.
from .const import (
    API_PREFIX,
    COMM_METHOD_HTTP,
    COMM_METHOD_MQTT,
    COMMUNICATION_METHOD,
    DATA_SCHEMA,
    DATA_SCHEMA_API,
    DATA_SCHEMA_MQTT,
    DATA_SCHEMA_OPTIONS,
    DEVICEID,
    DEVICETYPE,
    DOMAIN,
    MQTT_ROOT_TOPIC,
    MQTT_ROOT_TOPIC_DEFAULT,
)


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
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

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
            {"api_url": "http://192.168.0.68/simpleAPI/web/simpleapi.php"},
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
            combined_data = {**self.stored_user_input, **user_input}
            title = self._get_title(combined_data)
            await self.async_set_unique_id(title)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=title,
                data=combined_data,
            )

        data_schema = self.add_suggested_values_to_schema(data_schema, suggested_values)

        return self.async_show_form(
            step_id=step_id,
            data_schema=data_schema,
            errors=errors,
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


class OptionsFlowHandler(OptionsFlow):
    """Handle an options flow for openWB2 MQTT."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(step_id="init", data_schema=DATA_SCHEMA_OPTIONS)
