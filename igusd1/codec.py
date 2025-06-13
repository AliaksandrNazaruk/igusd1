"""
codec.py — packing and unpacking of dryve D1 values according to the Object
Dictionary specification.

© 2025 Aliaksandr Nazaruk / MIT-license
"""

import struct
from typing import Any

from .od import DataType


class CodecError(Exception):
    pass


def pack_value(value: Any, dtype: DataType, scale: float = 1) -> bytes:
    """Pack ``value`` into bytes using ``dtype`` and optional ``scale``.

    ``value`` may be ``int`` or ``float``.  ``scale`` is applied as
    ``value * scale`` before storing in the device.
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
    """Unpack ``data`` according to ``dtype`` and optional ``scale``.

    Returns ``float`` or ``int`` depending on ``dtype``.
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
