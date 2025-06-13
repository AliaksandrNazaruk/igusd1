"""
packet.py — формирование и парсинг Modbus TCP telegram для dryve D1

© 2025 Your-Company / MIT-license
"""

import struct
from typing import Tuple

from drivers.igus_scripts.exceptions import TransactionMismatch, ModbusException, AccessViolation
from drivers.igus_scripts.od import ODKey, OD_MAP, AccessType
from drivers.igus_scripts.codec import pack_value


class ModbusPacketBuilder:
    @staticmethod
    def build_read_request(od_key: "ODKey") -> bytes:
        obj = OD_MAP[od_key]
        if obj["access"] == AccessType.WO:
            raise AccessViolation(f"Object {od_key} is write-only")
        pdu = bytes([
            0x2B,                  # Function
            0x0D,                  # MEI Type
            0x00,                  # RW=0 (Read)
            0x00, 0x00,            # Reserved 3 bytes
            (obj["index"] >> 8) & 0xFF,   # Index high
            obj["index"] & 0xFF,          # Index low
            obj["subindex"],       # Subindex
            0x00, 0x00, 0x00, # Reserved 4 bytes
            obj["length"],         # Length
        ])
        return pdu

    @staticmethod
    def build_write_request(
        od_key: "ODKey",
        value: object,
    ) -> bytes:
        obj = OD_MAP[od_key]
        if obj["access"] == AccessType.RO:
            raise AccessViolation(f"Object {od_key} is read-only")

        packed_data = pack_value(value, obj["dtype"], obj.get("scale", 1))
        length = obj["length"]
        if len(packed_data) != length:
            raise ValueError(
                f"Packed data for {od_key} has length {len(packed_data)}, expected {length}"
            )
        header = bytes([
            0x2B,                  # Function
            0x0D,                  # MEI Type
            0x01,                  # RW=1 (Write)
            0x00, 0x00,      # Reserved 3 bytes
            (obj["index"] >> 8) & 0xFF,   # Index high
            obj["index"] & 0xFF,          # Index low
            obj["subindex"],       # Subindex
            0x00, 0x00, 0x00, # Reserved 4 bytes
            length,                # Length
        ])
        return header + packed_data



class ModbusPacketParser:
    """
    Универсальный парсер ответа Modbus TCP с проверкой transaction ID и exception.
    """

    @staticmethod
    def parse_response(
        response: bytes,
        expected_tid: int,
        *,
        expected_index = None,
        expected_subindex = None,
        expected_length = None,
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
            # raise ModbusException(f"Modbus Exception func=0x{func_code:x}, code=0x{exc_code:x}")

        if expected_index is not None:
            if len(payload) < 10:
                raise ModbusException("Response too short for index check")
            index = struct.unpack(">H", payload[5:7])[0]

            subindex = payload[7]
            length_byte = payload[11]
            # ---- Исправление: сравнивай с little-endian значением
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
