"""API client for openWB2 MQTT."""

import asyncio
import logging
import socket
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


class OpenWB2MqttApiClient:
    """API client for openWB2 MQTT."""

    def __init__(
        self,
        api_url: str,
        token: str | None,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize the API client."""
        self._api_url = api_url
        self._token = token
        self._session = session

    async def async_get_data(self, params: dict[str, str]) -> dict[str, Any]:
        """Read data, e.g. params={"get_chargepoint_all": "6"}."""
        return await self._api_wrapper("get", params=params)

    async def async_set_data(self, data: dict[str, str]) -> dict[str, Any]:
        """Send a command as form data, e.g. {"chargemode": "pv", "chargepoint_nr": "6"}."""
        return await self._api_wrapper("post", data=data)

    async def _api_wrapper(
        self,
        method: str,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Call the API and return the JSON answer."""
        _LOGGER.debug(
            "Calling API: %s %s, params: %s, data: %s",
            method.upper(),
            self._api_url,
            params,
            data,
        )
        headers: dict[str, str] = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            # One time budget for the first try and the retry together
            async with asyncio.timeout(10):
                try:
                    json_response = await self._send_request(
                        method, headers, params, data
                    )
                except aiohttp.ClientConnectionError as exception:
                    if isinstance(exception, TimeoutError):
                        raise  # ServerTimeoutError: the openWB did not answer
                    # The openWB (or a proxy) closed a kept-alive connection.
                    # Sending again is safe, also for POST: every simpleAPI set
                    # command writes an absolute value.
                    _LOGGER.debug(
                        "Connection to the openWB lost (%r), sending the request again",
                        exception,
                    )
                    json_response = await self._send_request(
                        method, headers, params, data
                    )
        except TimeoutError as exception:
            raise OpenWB2MqttApiClientCommunicationError(
                "Timeout after 10 s",
            ) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            raise OpenWB2MqttApiClientCommunicationError(
                f"{type(exception).__name__}: {exception}",
            ) from exception
        except Exception as exception:
            raise OpenWB2MqttApiClientError(
                "Something really wrong happened!"
            ) from exception
        return json_response

    async def _send_request(
        self,
        method: str,
        headers: dict[str, str],
        params: dict[str, str] | None,
        data: dict[str, str] | None,
    ) -> dict[str, Any]:
        """Send one request and return the JSON answer."""
        # aiohttp sets the form Content-Type for dict data itself
        response = await self._session.request(
            method=method,
            url=self._api_url,
            headers=headers,
            params=params,
            data=data,
        )
        response.raise_for_status()
        json_response = await response.json()
        _LOGGER.debug("API response: %s", json_response)
        return json_response


class OpenWB2MqttApiClientError(Exception):
    """Exception to indicate a general API error."""


class OpenWB2MqttApiClientCommunicationError(OpenWB2MqttApiClientError):
    """Exception to indicate a communication error."""
