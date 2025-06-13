"""
protocol.py — generic SDO protocol for the dryve D1 operating on top of
``transport.py`` and ``packet.py``.

© 2025 Aliaksandr Nazaruk / MIT-license
"""

import time
from typing import Any

from .exceptions import (
    DryveError,
    AccessViolation,
    ObjectNotFound,
    ModbusException,
)
from .od import ODKey, OD_MAP, AccessType
from .codec import unpack_value
from .packet import ModbusPacketBuilder, ModbusPacketParser


class DryveSDO:
    """Abstraction for reading and writing dryve D1 Object Dictionary entries."""

    def __init__(self, transport):
        self.transport = transport
        self._max_attempts = 3

    def read(self, od_key: ODKey) -> Any:
        """Read an OD object with decoding and access check."""
        if od_key not in OD_MAP:
            raise ObjectNotFound(f"OD key {od_key} is not defined")

        meta = OD_MAP[od_key]
        if meta["access"] not in (AccessType.RO, AccessType.RW):
            raise AccessViolation(f"Object {od_key} is not readable")

        for attempt in range(1, self._max_attempts + 1):
            try:
                pdu = ModbusPacketBuilder.build_read_request(od_key)
                tid, resp = self.transport.send_request(pdu)
                _, payload = ModbusPacketParser.parse_response(resp,tid,expected_index=meta["index"],expected_subindex=meta["subindex"],expected_length=meta["length"],)
                # payload contains data at the end, length equals meta["length"]
                data_bytes = payload[-meta["length"] :]
                value = unpack_value(data_bytes, meta["dtype"], meta.get("scale", 1))
                return value
            except ModbusException:
                if attempt == self._max_attempts:
                    raise
                time.sleep(0.1)
            except DryveError:
                raise
        raise DryveError(f"Failed to read {od_key}")

    def write(self, od_key: ODKey, value: Any) -> None:
        """Write a value to an OD object with packing and access check."""
        if od_key not in OD_MAP:
            raise ObjectNotFound(f"OD key {od_key} is not defined")

        meta = OD_MAP[od_key]
        if meta["access"] not in (AccessType.RW, AccessType.WO):
            raise AccessViolation(f"Object {od_key} is not writable")

        for attempt in range(1, self._max_attempts + 1):
            try:
                pdu = ModbusPacketBuilder.build_write_request(od_key, value)
                tid, resp = self.transport.send_request(pdu)
                # for writes the payload may be empty or contain confirmation
                ModbusPacketParser.parse_response(resp,tid,expected_index=meta["index"],expected_subindex=meta["subindex"],expected_length=None,)
                return
            except ModbusException:
                if attempt == self._max_attempts:
                    raise
                time.sleep(0.1)
            except DryveError:
                raise
        raise DryveError(f"Failed to write {od_key}")

