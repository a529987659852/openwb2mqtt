"""Common fixtures for the openwb2mqtt tests."""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow Home Assistant to load the custom integration in every test."""


@pytest.fixture
def mock_mqtt_subscribe() -> Generator[MagicMock]:
    """Replace the MQTT subscribe function with a mock.

    Tests can read the callback that was passed to the mock and call it
    to simulate an incoming message.
    """
    with patch("homeassistant.components.mqtt.async_subscribe") as mock_sub:
        yield mock_sub


@pytest.fixture
def mock_mqtt_publish() -> Generator[MagicMock]:
    """Replace the MQTT publish function with a mock."""
    with patch("homeassistant.components.mqtt.async_publish") as mock_pub:
        yield mock_pub
