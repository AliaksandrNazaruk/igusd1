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
    PROFILE_VELOCITY = "profile_velocity"
    PROFILE_ACCELERATION = "profile_acceleration"
    PROFILE_DECELERATION = "profile_deceleration"
    FEED_CONSTANT_FEED = "feed_constant_feed"
    FEED_CONSTANT_SHAFT_REVOLUTIONS = "feed_constant_shaft_revolutions"
    HOMING_METHOD = "homing_method"
    HOMING_SPEED_SEARCH_SWITCH = "homing_speed_search_switch"
    HOMING_SPEED_SEARCH_ZERO = "homing_speed_search_zero"
    HOMING_ACCELERATION = "homing_acceleration"
    DIGITAL_INPUTS = "digital_inputs"
    DIGITAL_OUTPUTS_PHYSICAL = "digital_outputs_physical"
    DIGITAL_OUTPUTS_BITMASK = "digital_outputs_bitmask"
    SUPPORTED_MODES = "supported_modes"
    POSITION_DEMAND = "position_demand"
    ERROR_REGISTER = "error_register"
    PREDEFINED_ERROR_FIELD = "predefined_error_field"
    STORE_PARAMETERS = "store_parameters"
    HOMING_STATUS = "homing_status"


OD_MAP = {
    ODKey.HOMING_STATUS: {
        "index": 0x2014,
        "subindex": 0,
        "length": 2,
        "access": AccessType.RO,
        "dtype": DataType.UINT16,
        "scale": 1,
    },
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
        "scale": 1,  # scale according to manua (e.g. 0.01 mm units)
    },
    ODKey.TARGET_VELOCITY: {
        "index": 0x60FF,
        "subindex": 0,
        "length": 4,
        "access": AccessType.RW,
        "dtype": DataType.INT32,
        "scale": 1,  # value * 100 according to manual
    },
    ODKey.ACTUAL_POSITION: {
        "index": 0x6064,
        "subindex": 0,
        "length": 4,
        "access": AccessType.RO,
        "dtype": DataType.INT32,
        "scale": 1,
    },
    ODKey.ACTUAL_VELOCITY: {
        "index": 0x606C,
        "subindex": 0,
        "length": 4,
        "access": AccessType.RO,
        "dtype": DataType.INT32,
        "scale": 100,
    },
    ODKey.PROFILE_VELOCITY: {
        "index": 0x6081,
        "subindex": 0,
        "length": 4,
        "access": AccessType.RW,
        "dtype": DataType.UINT32,
        "scale": 1,
    },
    ODKey.PROFILE_ACCELERATION: {
        "index": 0x6083,
        "subindex": 0,
        "length": 4,
        "access": AccessType.RW,
        "dtype": DataType.UINT32,
        "scale": 1,
    },
    ODKey.PROFILE_DECELERATION: {
        "index": 0x6084,
        "subindex": 0,
        "length": 4,
        "access": AccessType.RW,
        "dtype": DataType.UINT32,
        "scale": 1,
    },
    ODKey.FEED_CONSTANT_FEED: {
        "index": 0x6092,
        "subindex": 1,
        "length": 4,
        "access": AccessType.RW,
        "dtype": DataType.UINT32,
        "scale": 1,
    },
    ODKey.FEED_CONSTANT_SHAFT_REVOLUTIONS: {
        "index": 0x6092,
        "subindex": 2,
        "length": 4,
        "access": AccessType.RW,
        "dtype": DataType.UINT32,
        "scale": 1,
    },
    ODKey.HOMING_METHOD: {
        "index": 0x6098,
        "subindex": 0,
        "length": 1,
        "access": AccessType.RO,
        "dtype": DataType.INT8,
        "scale": 1,
    },
    ODKey.HOMING_SPEED_SEARCH_SWITCH: {
        "index": 0x6099,
        "subindex": 1,
        "length": 4,
        "access": AccessType.RW,
        "dtype": DataType.UINT32,
        "scale": 100,
    },
    ODKey.HOMING_SPEED_SEARCH_ZERO: {
        "index": 0x6099,
        "subindex": 2,
        "length": 4,
        "access": AccessType.RW,
        "dtype": DataType.UINT32,
        "scale": 100,
    },
    ODKey.HOMING_ACCELERATION: {
        "index": 0x609A,
        "subindex": 0,
        "length": 4,
        "access": AccessType.RW,
        "dtype": DataType.UINT32,
        "scale": 100,
    },
    ODKey.DIGITAL_INPUTS: {
        "index": 0x60FD,
        "subindex": 0,
        "length": 4,
        "access": AccessType.RO,
        "dtype": DataType.UINT32,
        "scale": 1,
    },
    ODKey.DIGITAL_OUTPUTS_PHYSICAL: {
        "index": 0x60FE,
        "subindex": 1,
        "length": 4,
        "access": AccessType.RW,
        "dtype": DataType.UINT32,
        "scale": 1,
    },
    ODKey.DIGITAL_OUTPUTS_BITMASK: {
        "index": 0x60FE,
        "subindex": 2,
        "length": 4,
        "access": AccessType.RW,
        "dtype": DataType.UINT32,
        "scale": 1,
    },
    ODKey.SUPPORTED_MODES: {
        "index": 0x6502,
        "subindex": 0,
        "length": 4,
        "access": AccessType.RO,
        "dtype": DataType.UINT32,
        "scale": 1,
    },
    ODKey.POSITION_DEMAND: {
        "index": 0x6063,
        "subindex": 0,
        "length": 4,
        "access": AccessType.RO,
        "dtype": DataType.INT32,
        "scale": 100,
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

