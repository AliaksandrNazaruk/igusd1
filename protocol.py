"""
protocol.py — универсальный SDO-протокол для dryve-D1, работающий поверх transport.py и packet.py

© 2025 Aliaksandr Nazaruk / MIT-license
"""

import time
from typing import Any

from drivers.igus_scripts.exceptions import (
    DryveError,
    AccessViolation,
    ObjectNotFound,
    ModbusException,
)
from drivers.igus_scripts.od import ODKey, OD_MAP, AccessType
from drivers.igus_scripts.codec import unpack_value
from drivers.igus_scripts.packet import ModbusPacketBuilder, ModbusPacketParser


class DryveSDO:
    """
    Абстракция для чтения и записи объектов Object Dictionary (SDO) dryve D1.
    """

    def __init__(self, transport):
        self.transport = transport
        self._max_attempts = 3

    def read(self, od_key: ODKey) -> Any:
        """
        Считать значение объекта OD с декодированием и проверкой прав доступа.
        """
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
                # payload содержит данные в конце, длина равна meta["length"]
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
        """
        Записать значение в объект OD с упаковкой и проверкой прав.
        """
        if od_key not in OD_MAP:
            raise ObjectNotFound(f"OD key {od_key} is not defined")

        meta = OD_MAP[od_key]
        if meta["access"] not in (AccessType.RW, AccessType.WO):
            raise AccessViolation(f"Object {od_key} is not writable")

        for attempt in range(1, self._max_attempts + 1):
            try:
                pdu = ModbusPacketBuilder.build_write_request(od_key, value)
                tid, resp = self.transport.send_request(pdu)
                # для записи payload может быть пустым или содержать подтверждение
                ModbusPacketParser.parse_response(resp,tid,expected_index=meta["index"],expected_subindex=meta["subindex"],expected_length=None,)
                return
            except ModbusException:
                if attempt == self._max_attempts:
                    raise
                time.sleep(0.1)
            except DryveError:
                raise
        raise DryveError(f"Failed to write {od_key}")

