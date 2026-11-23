"""API client for openWB2 MQTT."""

from __future__ import annotations

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
            async with asyncio.timeout(10):
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
        except TimeoutError as exception:
            raise OpenWB2MqttApiClientCommunicationError(
                "Timeout error fetching information",
            ) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            raise OpenWB2MqttApiClientCommunicationError(
                "Error fetching information",
            ) from exception
        except Exception as exception:
            raise OpenWB2MqttApiClientError(
                "Something really wrong happened!"
            ) from exception


class OpenWB2MqttApiClientError(Exception):
    """Exception to indicate a general API error."""


class OpenWB2MqttApiClientCommunicationError(OpenWB2MqttApiClientError):
    """Exception to indicate a communication error."""
