"""API client for openWB2 MQTT."""

from __future__ import annotations

import asyncio
import logging
import socket

import aiohttp

# import async_timeout

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

    async def async_get_data(self, endpoint: str) -> any:
        """Get data from the API."""
        return await self._api_wrapper("get", f"{self._api_url}/{endpoint}")

    async def async_set_data(self, data: dict | str) -> any:
        """Set data via the API."""
        return await self._api_wrapper("post", self._api_url, data=data)

    async def _api_wrapper(
        self,
        method: str,
        url: str,
        data: dict | str | None = None,
        headers: dict | None = None,
    ) -> any:
        """Wrap the API call."""
        _LOGGER.debug("Calling API: %s %s, data: %s", method.upper(), url, data)
        if headers is None:
            headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            async with asyncio.timeout(10):
                if method.lower() == "post":
                    headers["Content-Type"] = "application/x-www-form-urlencoded"
                response = await self._session.request(
                    method=method,
                    url=url,
                    headers=headers,
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
            _LOGGER.exception("Something really wrong happened!")
            raise OpenWB2MqttApiClientError(
                "Something really wrong happened!"
            ) from exception


class OpenWB2MqttApiClientError(Exception):
    """Exception to indicate a general API error."""


class OpenWB2MqttApiClientCommunicationError(OpenWB2MqttApiClientError):
    """Exception to indicate a communication error."""
