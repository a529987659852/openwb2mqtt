"""The openwbmqtt component for controlling the openWB wallbox via home assistant / MQTT."""

from __future__ import annotations

from homeassistant.config_entries import ConfigFlow

# Import global values.
from .const import DATA_SCHEMA, DEVICEID, DEVICETYPE, DOMAIN, MQTT_ROOT_TOPIC


class openwbmqttConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configuration flow for the configuration of the openWB integration.

    When custom component is added by the user, they must provide
    - MQTT root topic
    - Device type
    - Device ID
    --> See DATA_SCHEMA.
    """

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Ask user for configuration data."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA)
        if user_input[DEVICETYPE] == "controller":
            title = f"{user_input[MQTT_ROOT_TOPIC]}-{user_input[DEVICETYPE]}"
        else:
            title = f"{user_input[MQTT_ROOT_TOPIC]}-{user_input[DEVICETYPE]}-{user_input[DEVICEID]}"
        await self.async_set_unique_id(title)

        # Abort if the same integration was already configured.
        if user_input[DEVICETYPE] == "controller":
            self._abort_if_unique_id_configured(error="controller_already_configured")
        elif user_input[DEVICETYPE] == "bat":
            self._abort_if_unique_id_configured(error="batterie_already_configured")
        elif user_input[DEVICETYPE] == "counter":
            self._abort_if_unique_id_configured(error="counter_already_configured")
        elif user_input[DEVICETYPE] == "pv":
            self._abort_if_unique_id_configured(error="pv_already_configured")
        elif user_input[DEVICETYPE] == "chargepoint":
            self._abort_if_unique_id_configured(error="chargepoint_already_configured")
        elif user_input[DEVICETYPE] == "vehicle":
            self._abort_if_unique_id_configured(error="vehicle_already_configured")
        else:
            self._abort_if_unique_id_configured()

        # Create entities
        return self.async_create_entry(
            title=title,
            data=user_input,
        )
