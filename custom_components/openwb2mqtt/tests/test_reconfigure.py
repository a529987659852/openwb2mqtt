"""Tests for the reconfigure step of the openwb2mqtt config flow."""

from unittest.mock import patch
import pytest
from homeassistant.data_entry_flow import FlowResultType
from tests.common import MockConfigEntry
from config.custom_components.openwb2mqtt.api_client import (
    OpenWB2MqttApiClientCommunicationError, OpenWB2MqttApiClientError)

DOMAIN = "openwb2mqtt"
VALIDATE = "config.custom_components.openwb2mqtt.config_flow._async_validate_api_url"


def _http_entry(hass):
    e = MockConfigEntry(domain=DOMAIN, title="openWB-chargepoint-4", unique_id="openWB-chargepoint-4",
        data={"communication_method": "HTTP API", "api_prefix": "openWB",
              "api_url": "http://10.0.0.1/openWB/simpleAPI/simpleapi.php",
              "DEVICETYPE": "chargepoint", "DEVICEID": 4, "wallbox_power": "11", "vehicles": {}})
    e.add_to_hass(hass); return e

async def test_reconfigure_success(hass):
    e = _http_entry(hass)
    r = await e.start_reconfigure_flow(hass)
    assert r["type"] is FlowResultType.FORM and r["step_id"] == "reconfigure"
    with patch(VALIDATE) as v, patch("config.custom_components.openwb2mqtt.async_setup_entry", return_value=True):
        r = await hass.config_entries.flow.async_configure(r["flow_id"],
            {"api_url": " http://10.0.0.99/openWB/simpleAPI/simpleapi.php "})
        await hass.async_block_till_done()
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "reconfigure_successful"
    v.assert_awaited_once()
    assert e.data["api_url"] == "http://10.0.0.99/openWB/simpleAPI/simpleapi.php"
    assert e.unique_id == "openWB-chargepoint-4" and e.title == "openWB-chargepoint-4"
    assert e.data["DEVICEID"] == 4 and e.data["api_prefix"] == "openWB"

@pytest.mark.parametrize("exc,err", [(OpenWB2MqttApiClientCommunicationError, "cannot_connect"),
                                     (OpenWB2MqttApiClientError, "invalid_api_response")])
async def test_reconfigure_errors_then_recover(hass, exc, err):
    e = _http_entry(hass)
    r = await e.start_reconfigure_flow(hass)
    with patch(VALIDATE, side_effect=exc("x")):
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"api_url": "http://bad"})
    assert r["type"] is FlowResultType.FORM and r["errors"] == {"base": err}
    assert e.data["api_url"].startswith("http://10.0.0.1")
    with patch(VALIDATE), patch("config.custom_components.openwb2mqtt.async_setup_entry", return_value=True):
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"api_url": "http://good/simpleapi.php"})
        await hass.async_block_till_done()
    assert r["reason"] == "reconfigure_successful" and e.data["api_url"] == "http://good/simpleapi.php"

async def test_reconfigure_mqtt_aborts(hass):
    e = MockConfigEntry(domain=DOMAIN, title="openWB-pv-1", unique_id="openWB-pv-1",
        data={"communication_method": "MQTT", "mqttroot": "openWB", "DEVICETYPE": "pv", "DEVICEID": 1})
    e.add_to_hass(hass)
    r = await e.start_reconfigure_flow(hass)
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "reconfigure_not_supported_mqtt"

async def test_validate_hits_simpleapi(hass, aioclient_mock):
    from config.custom_components.openwb2mqtt.config_flow import _async_validate_api_url
    aioclient_mock.get("http://wb/simpleapi.php/?get_lastlivevaluesjson&raw=true", json={"ok": 1})
    await _async_validate_api_url(hass, "http://wb/simpleapi.php")
    aioclient_mock.clear_requests()
    aioclient_mock.get("http://wb/simpleapi.php/?get_lastlivevaluesjson&raw=true", text="<html>nope</html>")
    with pytest.raises(OpenWB2MqttApiClientError):
        await _async_validate_api_url(hass, "http://wb/simpleapi.php")
