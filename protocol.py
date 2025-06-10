"""
protocol.py — универсальный SDO-протокол для dryve-D1, работающий поверх transport.py и packet.py

© 2025 Your-Company / MIT-license
"""

import time
from typing import Any

from exceptions import (
    DryveError,
    AccessViolation,
    ObjectNotFound,
    ModbusException,
)
from od import ODKey, OD_MAP, AccessType
from codec import pack_value, unpack_value
from packet import ModbusPacketBuilder, ModbusPacketParser


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
                resp = self.transport.send_request(pdu)
                tid = self.transport._transaction_id
                _, payload = ModbusPacketParser.parse_response(
                    resp,
                    tid,
                    expected_index=meta["index"],
                    expected_subindex=meta["subindex"],
                    expected_length=meta["length"],
                )
                # payload содержит данные в конце, длина равна meta["length"]
                data_bytes = payload[-meta["length"] :]
                value = unpack_value(data_bytes, meta["dtype"], meta.get("scale", 1))
                return value
            except ModbusException as e:
                if attempt == self._max_attempts:
                    raise
                time.sleep(0.1)
            except DryveError as e:
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
                resp = self.transport.send_request(pdu)
                tid = self.transport._transaction_id
                # для записи payload может быть пустым или содержать подтверждение
                ModbusPacketParser.parse_response(
                    resp,
                    tid,
                    expected_index=meta["index"],
                    expected_subindex=meta["subindex"],
                    expected_length=meta["length"],
                )
                return
            except ModbusException as e:
                if attempt == self._max_attempts:
                    raise
                time.sleep(0.1)
            except DryveError as e:
                raise
        raise DryveError(f"Failed to write {od_key}")

    def store_parameters(self) -> None:
        """
        Специальная команда записи в объект Store Parameters (0x1010, subindex=1),
        для сохранения конфигурации в энергонезависимой памяти.
        """
        store_key = ODKey.STORE_PARAMETERS
        value = 0x65766173  # 'evas' в hex, согласно мануалу
        self.write(store_key, value)
