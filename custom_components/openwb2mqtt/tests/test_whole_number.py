"""Check that whole-step numbers are shown without a trailing .0."""

from typing import Any

from custom_components.openwb2mqtt.const import _whole_number
import pytest


@pytest.mark.parametrize(
    ("value", "step", "expected"),
    [
        (50.0, 5, 50),
        (16.0, 1.0, 16),
        (0.36, 0.01, 0.36),
        (1.0, 0.01, 1.0),
        (None, 1, None),
        (16, 1, 16),
    ],
)
def test_whole_number(value: Any, step: float, expected: Any) -> None:
    """Whole steps give an int, small steps keep the float."""
    result = _whole_number(value, step)
    assert result == expected
    # 50 == 50.0 in Python, so also check the type
    assert type(result) is type(expected)
