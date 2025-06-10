"""
exceptions.py  –  Common exceptions for the dryve-d1 driver
© 2025  Your-Company / MIT-license

This module defines a *single* inheritance tree for all errors that can
occur inside the driver.  Import it everywhere instead of raising raw
RuntimeError / ValueError, so upper layers can reliably distinguish
transport-level failures, protocol violations and logical state errors.
"""

from __future__ import annotations
import typing as _t


class DryveError(Exception):
    """Base-class for **any** error raised by the dryve-d1 stack."""
    #: Optional numeric code (Modbus except-code, igus error ID …)
    code: int | None = None

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


# ────────────────────────────────
# Transport layer
# ────────────────────────────────
class TransportError(DryveError):
    """Low-level socket/TCP problem (timeout, broken pipe, DNS, etc.)."""

class ConnectionLost(TransportError):
    """The socket closed unexpectedly during an operation."""

class ConnectionTimeout(TransportError):
    """Timed-out while connecting or waiting for data."""


# ────────────────────────────────
# Protocol layer
# ────────────────────────────────
class ProtocolError(DryveError):
    """Malformed or unexpected Modbus/SDO frame."""

class TransactionMismatch(ProtocolError):
    """Transaction-ID in response does not match request."""

class ModbusException(ProtocolError):
    """
    Remote side returned *Modbus exception code* (function | 0x80).
    `code` attribute holds the Modbus exception number.
    """

class AccessViolation(ProtocolError):
    """
    Attempt to write a read-only OD object, or read a write-only one.
    """

class ObjectNotFound(ProtocolError):
    """Requested OD index/subindex is not supported by the device."""


# ────────────────────────────────
# State-machine / logic
# ────────────────────────────────
class StateError(DryveError):
    """Illegal or unexpected CiA-402 state transition."""

class FaultState(StateError):
    """Drive reports *FAULT* bit set in Statusword."""

class OperationTimeout(StateError):
    """Timed-out while waiting for drive to reach the requested state."""

class TargetNotReached(StateError):
    """Motion command finished without `TargetReached` bit in Statusword."""


# ────────────────────────────────
# Helpers
# ────────────────────────────────
_exc_map: dict[int, type[DryveError]] = {
    0x01: ModbusException,  # ILLEGAL FUNCTION
    0x02: ModbusException,  # ILLEGAL DATA ADDRESS
    0x03: ModbusException,  # ILLEGAL DATA VALUE
    0x04: ModbusException,  # SLAVE DEVICE FAILURE
    # … extend as required
}


def from_modbus_exception(code: int, detail: str | None = None) -> DryveError:
    """
    Convert numeric Modbus exception `code` to a concrete exception class.
    """
    cls: type[DryveError] = _exc_map.get(code, ModbusException)
    msg = f"Modbus exception 0x{code:02X}"
    if detail:
        msg += f": {detail}"
    return cls(msg, code=code)


__all__: _t.Sequence[str] = [
    "DryveError",
    "TransportError",
    "ConnectionLost",
    "ConnectionTimeout",
    "ProtocolError",
    "TransactionMismatch",
    "ModbusException",
    "AccessViolation",
    "ObjectNotFound",
    "StateError",
    "FaultState",
    "OperationTimeout",
    "TargetNotReached",
    "from_modbus_exception",
]
