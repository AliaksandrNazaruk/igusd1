"""
codec.py — упаковка и распаковка значений dryve-d1 по OD спецификации

© 2025 Your-Company / MIT-license
"""

import struct
from typing import Any

from drivers.igus_scripts.od import DataType


class CodecError(Exception):
    pass


def pack_value(value: Any, dtype: DataType, scale: float = 1) -> bytes:
    """
    Преобразует value в байты с учётом типа данных и масштаба.
    value — число (int, float)
    dtype — тип из od.DataType
    scale — коэффициент масштабирования (value * scale → хранится в устройстве)
    """
    scaled_val = value * scale if scale != 1 else value

    if dtype == DataType.UINT8:
        return struct.pack("<B", int(scaled_val))
    elif dtype == DataType.INT8:
        return struct.pack("<b", int(scaled_val))
    elif dtype == DataType.UINT16:
        return struct.pack("<H", int(scaled_val))
    elif dtype == DataType.INT16:
        return struct.pack("<h", int(scaled_val))
    elif dtype == DataType.UINT32:
        return struct.pack("<I", int(scaled_val))
    elif dtype == DataType.INT32:
        return struct.pack("<i", int(scaled_val))
    elif dtype == DataType.FLOAT32:
        return struct.pack("<f", float(scaled_val))
    else:
        raise CodecError(f"Unsupported dtype for packing: {dtype}")


def unpack_value(data: bytes, dtype: DataType, scale: float = 1) -> Any:
    """
    Распаковывает байты data в значение с учётом типа и масштаба.
    Возвращает float или int, в зависимости от dtype.
    """
    if dtype == DataType.UINT8:
        val = struct.unpack("<B", data)[0]
    elif dtype == DataType.INT8:
        val = struct.unpack("<b", data)[0]
    elif dtype == DataType.UINT16:
        val = struct.unpack("<H", data)[0]
    elif dtype == DataType.INT16:
        val = struct.unpack("<h", data)[0]
    elif dtype == DataType.UINT32:
        val = struct.unpack("<I", data)[0]
    elif dtype == DataType.INT32:
        val = struct.unpack("<i", data)[0]
    elif dtype == DataType.FLOAT32:
        val = struct.unpack("<f", data)[0]
    else:
        raise CodecError(f"Unsupported dtype for unpacking: {dtype}")

    if scale != 1:
        return val / scale
    return val
