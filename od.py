"""
od.py — Object Dictionary (OD) описание для dryve-D1

© 2025 Your-Company / MIT-license
"""

from enum import Enum


class AccessType(str, Enum):
    RO = "ro"
    RW = "rw"
    WO = "wo"
    CONST = "const"


class DataType(str, Enum):
    UINT8 = "uint8"
    INT8 = "int8"
    UINT16 = "uint16"
    INT16 = "int16"
    UINT32 = "uint32"
    INT32 = "int32"
    FLOAT32 = "float32"
    # Можно расширять при необходимости


class ODKey(str, Enum):
    CONTROLWORD = "controlword"
    STATUSWORD = "statusword"
    MODE_OF_OPERATION = "mode_of_operation"
    MODE_OF_OPERATION_DISPLAY = "mode_of_operation_display"
    TARGET_POSITION = "target_position"
    TARGET_VELOCITY = "target_velocity"
    ACTUAL_POSITION = "actual_position"
    ACTUAL_VELOCITY = "actual_velocity"
    ERROR_REGISTER = "error_register"
    PREDEFINED_ERROR_FIELD = "predefined_error_field"
    STORE_PARAMETERS = "store_parameters"
    # Добавлять по необходимости


OD_MAP = {
    ODKey.CONTROLWORD: {
        "index": 0x6040,
        "subindex": 0,
        "length": 2,
        "access": AccessType.RW,
        "dtype": DataType.UINT16,
        "scale": 1,
    },
    ODKey.STATUSWORD: {
        "index": 0x6041,
        "subindex": 0,
        "length": 2,
        "access": AccessType.RO,
        "dtype": DataType.UINT16,
        "scale": 1,
    },
    ODKey.MODE_OF_OPERATION: {
        "index": 0x6060,
        "subindex": 0,
        "length": 1,
        "access": AccessType.RW,
        "dtype": DataType.INT8,
        "scale": 1,
    },
    ODKey.MODE_OF_OPERATION_DISPLAY: {
        "index": 0x6061,
        "subindex": 0,
        "length": 1,
        "access": AccessType.RO,
        "dtype": DataType.INT8,
        "scale": 1,
    },
    ODKey.TARGET_POSITION: {
        "index": 0x607A,
        "subindex": 0,
        "length": 4,
        "access": AccessType.RW,
        "dtype": DataType.INT32,
        "scale": 100,  # scale according to manua (e.g. 0.01 mm units)
    },
    ODKey.TARGET_VELOCITY: {
        "index": 0x60FF,
        "subindex": 0,
        "length": 4,
        "access": AccessType.RW,
        "dtype": DataType.INT32,
        "scale": 1000,  # scale for velocity mm/s
    },
    ODKey.ACTUAL_POSITION: {
        "index": 0x6064,
        "subindex": 0,
        "length": 4,
        "access": AccessType.RO,
        "dtype": DataType.INT32,
        "scale": 100,
    },
    ODKey.ACTUAL_VELOCITY: {
        "index": 0x606C,
        "subindex": 0,
        "length": 4,
        "access": AccessType.RO,
        "dtype": DataType.INT32,
        "scale": 1000,
    },
    ODKey.ERROR_REGISTER: {
        "index": 0x1001,
        "subindex": 0,
        "length": 1,
        "access": AccessType.RO,
        "dtype": DataType.UINT8,
        "scale": 1,
    },
    ODKey.PREDEFINED_ERROR_FIELD: {
        "index": 0x1003,
        "subindex": 0,
        "length": 8,  # количество ошибок в списке, зависит от subindex 1..8
        "access": AccessType.RO,
        "dtype": DataType.UINT32,
        "scale": 1,
    },
    ODKey.STORE_PARAMETERS: {
        "index": 0x1010,
        "subindex": 1,
        "length": 4,
        "access": AccessType.RW,
        "dtype": DataType.UINT32,
        "scale": 1,
    },
    # Добавлять новые по мере необходимости...
}

