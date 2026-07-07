"""Tests for the exception hierarchy."""

import pytest

from empire_core.exceptions import (
    CommandError,
    ConnectionClosedError,
    EmpireError,
    EmpireTimeoutError,
    NetworkError,
)


def test_timeout_error_subclasses_builtin():
    # Callers writing `except TimeoutError` (the builtin) must catch it too.
    assert issubclass(EmpireTimeoutError, TimeoutError)
    assert issubclass(EmpireTimeoutError, EmpireError)

    with pytest.raises(TimeoutError):
        raise EmpireTimeoutError("timed out")


def test_connection_closed_is_network_error():
    assert issubclass(ConnectionClosedError, NetworkError)


def test_command_error_carries_code_and_command():
    err = CommandError("gam", 21)
    assert err.code == 21
    assert err.command == "gam"
    assert "21" in str(err)
    assert "gam" in str(err)
