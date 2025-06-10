"""
state_bits.py — константы битов Controlword и Statusword, helpers для dryve-D1

© 2025 Your-Company / MIT-license
"""

from enum import IntEnum


# Битовые маски Controlword (0x6040) — стандарт CiA 402
CW_SHUTDOWN            = 0x0006  # бит 1 и 2 установлены (0b0000_0110)
CW_SWITCH_ON           = 0x0007  # бит 0,1,2 (0b0000_0111)
CW_ENABLE_OPERATION    = 0x000F  # биты 0-3 (0b0000_1111)
CW_DISABLE_VOLTAGE     = 0x0000
CW_QUICK_STOP          = 0x0002
CW_FAULT_RESET         = 0x0080  # бит 7
CW_START_MOTION        = 0x001F  # запуск профилированного перемещения/гоминга


# Битовые маски Statusword (0x6041) — стандарт CiA 402
SW_READY_TO_SWITCH_ON  = 0x0001  # бит 0
SW_SWITCHED_ON         = 0x0002  # бит 1
SW_OPERATION_ENABLED   = 0x0004  # бит 2
SW_FAULT               = 0x0008  # бит 3
SW_VOLTAGE_ENABLED     = 0x0010  # бит 4
SW_QUICK_STOP          = 0x0020  # бит 5
SW_SWITCH_ON_DISABLED  = 0x0040  # бит 6
SW_WARNING             = 0x0080  # бит 7
SW_REMOTE              = 0x0200  # бит 9
SW_TARGET_REACHED      = 0x0400  # бит 10
SW_INTERNAL_LIMIT      = 0x0800  # бит 11
SW_OP_MODE_SPECIFIC    = 0x1000  # бит 12


class DriveState(IntEnum):
    """Класс состояний CiA 402 (состояния привода) — с описанием"""
    NOT_READY_TO_SWITCH_ON = 0
    SWITCH_ON_DISABLED = 1
    READY_TO_SWITCH_ON = 2
    SWITCHED_ON = 3
    OPERATION_ENABLED = 4
    QUICK_STOP_ACTIVE = 5
    FAULT_REACTION_ACTIVE = 6
    FAULT = 7


def parse_drive_state(statusword: int) -> DriveState:
    """Map *statusword* bits to a CiA‑402 drive state."""
    if (statusword & 0x004F) == 0x0000:
        return DriveState.NOT_READY_TO_SWITCH_ON
    if (statusword & 0x006F) == 0x0040:
        return DriveState.SWITCH_ON_DISABLED
    if (statusword & 0x006F) == 0x0021:
        return DriveState.READY_TO_SWITCH_ON
    if (statusword & 0x006F) == 0x0023:
        return DriveState.SWITCHED_ON
    if (statusword & 0x006F) == 0x0027:
        return DriveState.OPERATION_ENABLED
    if (statusword & 0x006F) == 0x0007:
        return DriveState.QUICK_STOP_ACTIVE
    if (statusword & 0x004F) == 0x000F:
        return DriveState.FAULT_REACTION_ACTIVE
    if (statusword & 0x004F) == 0x0008:
        return DriveState.FAULT
    return DriveState.NOT_READY_TO_SWITCH_ON


class Statusword:
    """Обертка вокруг statusword с удобным API булевых свойств"""

    __slots__ = ("value",)

    def __init__(self, value: int):
        self.value = value

    @property
    def ready_to_switch_on(self) -> bool:
        return bool(self.value & SW_READY_TO_SWITCH_ON)

    @property
    def switched_on(self) -> bool:
        return bool(self.value & SW_SWITCHED_ON)

    @property
    def operation_enabled(self) -> bool:
        return bool(self.value & SW_OPERATION_ENABLED)

    @property
    def fault(self) -> bool:
        return bool(self.value & SW_FAULT)

    @property
    def voltage_enabled(self) -> bool:
        return bool(self.value & SW_VOLTAGE_ENABLED)

    @property
    def quick_stop(self) -> bool:
        return bool(self.value & SW_QUICK_STOP)

    @property
    def switch_on_disabled(self) -> bool:
        return bool(self.value & SW_SWITCH_ON_DISABLED)

    @property
    def warning(self) -> bool:
        return bool(self.value & SW_WARNING)

    @property
    def remote(self) -> bool:
        return bool(self.value & SW_REMOTE)

    @property
    def target_reached(self) -> bool:
        return bool(self.value & SW_TARGET_REACHED)

    @property
    def internal_limit(self) -> bool:
        return bool(self.value & SW_INTERNAL_LIMIT)

    @property
    def op_mode_specific(self) -> bool:
        return bool(self.value & SW_OP_MODE_SPECIFIC)

    def __repr__(self):
        flags = []
        if self.ready_to_switch_on:
            flags.append("ReadyToSwitchOn")
        if self.switched_on:
            flags.append("SwitchedOn")
        if self.operation_enabled:
            flags.append("OperationEnabled")
        if self.fault:
            flags.append("Fault")
        if self.voltage_enabled:
            flags.append("VoltageEnabled")
        if self.quick_stop:
            flags.append("QuickStop")
        if self.switch_on_disabled:
            flags.append("SwitchOnDisabled")
        if self.warning:
            flags.append("Warning")
        if self.remote:
            flags.append("Remote")
        if self.target_reached:
            flags.append("TargetReached")
        if self.internal_limit:
            flags.append("InternalLimit")
        if self.op_mode_specific:
            flags.append("OpModeSpecific")
        return f"<Statusword {'|'.join(flags)}>"


def controlword_for_state(state: DriveState) -> int:
    """
    Вернуть соответствующий Controlword для перехода в заданное состояние.
    """
    mapping = {
        DriveState.NOT_READY_TO_SWITCH_ON: 0x0000,
        DriveState.SWITCH_ON_DISABLED: CW_DISABLE_VOLTAGE,
        DriveState.READY_TO_SWITCH_ON: CW_SHUTDOWN,
        DriveState.SWITCHED_ON: CW_SWITCH_ON,
        DriveState.OPERATION_ENABLED: CW_ENABLE_OPERATION,
        DriveState.QUICK_STOP_ACTIVE: CW_QUICK_STOP,
        DriveState.FAULT: CW_FAULT_RESET,
    }
    return mapping.get(state, 0x0000)
