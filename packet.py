"""
packet.py — формирование и парсинг Modbus TCP telegram для dryve D1

© 2025 Your-Company / MIT-license
"""

import struct
from typing import Tuple

from exceptions import TransactionMismatch, ModbusException, AccessViolation
from od import ODKey, OD_MAP, AccessType
from codec import pack_value


class ModbusPacketBuilder:
    """
    Формирует Modbus PDU для чтения/записи объектов dryve D1 по протоколу MEI 0x0D, функция 0x2B.
    """
    @staticmethod
    def build_read_request(od_key: ODKey) -> bytes:
        obj = OD_MAP[od_key]
        if obj["access"] == AccessType.WO:
            raise AccessViolation(f"Object {od_key} is write-only")
        pdu = struct.pack(
            ">BBB3BHB3BB",
            0x2B,                # Function
            0x0D,                # MEI Type
            0x00,                # RW=0 (Read)
            0x00, 0x00, 0x00,    # Reserved 3 bytes
            obj["index"],        # Index (2 bytes)
            obj["subindex"],     # Subindex (1 byte)
            0x00, 0x00, 0x00,    # Reserved 3 bytes
            obj["length"],       # Length (1 byte)
        )
        return pdu


    @staticmethod
    def build_write_request(
        od_key: ODKey,
        value: object,
    ) -> bytes:
        """Формирует Modbus PDU для записи объекта OD с данным значением."""
        obj = OD_MAP[od_key]
        if obj["access"] == AccessType.RO:
            raise AccessViolation(f"Object {od_key} is read-only")

        packed_data = pack_value(value, obj["dtype"], obj.get("scale", 1))
        length = obj["length"]
        if len(packed_data) != length:
            raise ValueError(
                f"Packed data for {od_key} has length {len(packed_data)}, expected {length}"
            )
        # RW = 1 для записи
        header = struct.pack(
            ">BBB3BHB3BB",
            0x2B,  # Функция
            0x0D,  # MEI Type
            0x01,  # RW=1 (Write)
            0x00, 0x00, 0x00,  # Reserved
            obj["index"],
            obj["subindex"],
            0x00, 0x00, 0x00,  # Reserved
            length,
        )
        pdu = header + packed_data
        return pdu


class ModbusPacketParser:
    """
    Универсальный парсер ответа Modbus TCP с проверкой transaction ID и exception.
    """

    @staticmethod
    def parse_response(
        response: bytes,
        expected_tid: int,
        *,
        expected_index: int | None = None,
        expected_subindex: int | None = None,
        expected_length: int | None = None,
    ) -> Tuple[int, bytes]:
        """
        Парсит полный Modbus TCP ответ, проверяет TID и Modbus exception.

        :param response: полный пакет (MBAP header + PDU)
        :param expected_tid: ожидаемый transaction id
        :return: tuple (unit_id, payload)
        """
        if len(response) < 9:
            raise ModbusException("Response too short")

        # MBAP header: TransactionID(2), ProtocolID(2), Length(2), UnitID(1)
        tid, proto, length, unit_id = struct.unpack(">HHHB", response[:7])
        if proto != 0:
            raise ModbusException(f"Protocol ID mismatch: {proto}")
        if tid != expected_tid:
            raise TransactionMismatch(f"TID mismatch: expected {expected_tid}, got {tid}")

        # Проверяем длину
        if length != len(response) - 6:
            raise ModbusException(f"Length mismatch: expected {length}, actual {len(response)-6}")

        payload = response[7:]
        if len(payload) == 0:
            raise ModbusException("Empty payload")

        # Проверка Modbus exception: MSB функции == 1 (0x80 + func)
        func_code = payload[0]
        if func_code & 0x80:
            exc_code = payload[1]
            raise ModbusException(f"Modbus Exception func=0x{func_code:x}, code=0x{exc_code:x}")

        if expected_index is not None:
            if len(payload) < 13:
                raise ModbusException("Response too short for index check")
            index = struct.unpack(">H", payload[6:8])[0]
            subindex = payload[8]
            length_byte = payload[12]
            if index != expected_index:
                raise ModbusException(
                    f"Response index mismatch: expected 0x{expected_index:04X}, got 0x{index:04X}"
                )
            if expected_subindex is not None and subindex != expected_subindex:
                raise ModbusException(
                    f"Response subindex mismatch: expected {expected_subindex}, got {subindex}"
                )
            if expected_length is not None and length_byte != expected_length:
                raise ModbusException(
                    f"Response length mismatch: expected {expected_length}, got {length_byte}"
                )

        return unit_id, payload
