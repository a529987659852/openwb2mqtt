"""Check the one retry of the HTTP API client.

The test uses a fake aiohttp session, so it needs no running Home Assistant
and no wallbox.
"""

import asyncio
from typing import Any

import aiohttp
from custom_components.openwb2mqtt.api_client import (
    OpenWB2MqttApiClient,
    OpenWB2MqttApiClientCommunicationError,
)
import pytest

ANSWER = {"success": True}


class FakeResponse:
    """Answer of a request that worked."""

    def raise_for_status(self) -> None:
        """The HTTP status is always OK."""

    async def json(self) -> dict[str, Any]:
        """Return the JSON answer."""
        return ANSWER


class FakeSession:
    """Session that raises the given exceptions, one per call, then answers."""

    def __init__(self, errors: list[Exception]) -> None:
        """Store the exceptions for the first calls."""
        self.errors = errors
        self.calls = 0

    async def request(self, **kwargs: Any) -> FakeResponse:
        """Raise the next exception or return an answer."""
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return FakeResponse()


def _make_client(session: FakeSession) -> OpenWB2MqttApiClient:
    """Return a client that uses the fake session."""
    return OpenWB2MqttApiClient(
        api_url="http://openwb.local/simpleapi.php",
        token=None,
        session=session,  # type: ignore[arg-type]
    )


def test_retry_after_dropped_connection() -> None:
    """A dropped connection is retried once and the answer is returned."""
    session = FakeSession([aiohttp.ServerDisconnectedError()])
    result = asyncio.run(_make_client(session).async_set_data({"chargemode": "pv"}))
    assert result == ANSWER
    assert session.calls == 2


def test_no_second_retry() -> None:
    """If the retry also fails, the error is raised."""
    session = FakeSession(
        [aiohttp.ServerDisconnectedError(), aiohttp.ServerDisconnectedError()]
    )
    with pytest.raises(OpenWB2MqttApiClientCommunicationError):
        asyncio.run(_make_client(session).async_get_data({"get_chargepoint_all": "6"}))
    assert session.calls == 2


def test_no_retry_after_timeout() -> None:
    """A timeout is not retried."""
    session = FakeSession([aiohttp.ServerTimeoutError()])
    with pytest.raises(OpenWB2MqttApiClientCommunicationError):
        asyncio.run(_make_client(session).async_get_data({"get_chargepoint_all": "6"}))
    assert session.calls == 1
