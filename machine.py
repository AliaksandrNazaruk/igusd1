"""
machine.py — управление state machine dryve D1 (CiA 402)

© 2025 Your-Company / MIT-license
"""

import time
import logging

from exceptions import FaultState, OperationTimeout
from od import ODKey
from state_bits import (
    DriveState,
    parse_drive_state,
    Statusword,
    controlword_for_state,
)

_LOGGER = logging.getLogger(__name__)


class DriveStateMachine:
    """
    Класс для управления state machine привода dryve D1.

    Требует объект DryveSDO для доступа к Controlword/Statusword.
    """

    def __init__(self, sdo, poll_delay=0.05, timeout=5.0):
        self.sdo = sdo
        self.poll_delay = poll_delay  # период опроса статуса
        self.timeout = timeout        # таймаут ожидания перехода

    def _read_statusword(self) -> Statusword:
        val = self.sdo.read(ODKey.STATUSWORD)
        return Statusword(val)

    def _write_controlword(self, cw_value: int) -> None:
        self.sdo.write(ODKey.CONTROLWORD, cw_value)

    def wait_for_state(self, target_state: DriveState) -> None:
        """
        Ожидает, пока привод перейдет в целевое состояние.

        Бросает OperationTimeout если таймаут вышел.
        Бросает FaultState если обнаружен fault.
        """
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            statusword_val = self.sdo.read(ODKey.STATUSWORD)
            sw = Statusword(statusword_val)
            if sw.fault:
                _LOGGER.error("Drive fault detected")
                raise FaultState("Drive reports FAULT bit set")

            current_state = parse_drive_state(statusword_val)
            if current_state == target_state:
                _LOGGER.debug(f"Reached target state: {target_state.name}")
                return
            time.sleep(self.poll_delay)

        raise OperationTimeout(f"Timeout waiting for state {target_state.name}")

    def fault_reset(self) -> None:
        """Сбрасывает fault, если есть."""
        sw = self._read_statusword()
        if not sw.fault:
            _LOGGER.debug("No fault to reset")
            return

        _LOGGER.info("Performing fault reset")
        # Для сброса выставляем бит 7 controlword (0x0080)
        self._write_controlword(controlword_for_state(DriveState.FAULT))
        time.sleep(self.poll_delay)
        self.wait_for_state(DriveState.SWITCH_ON_DISABLED)

    def shutdown(self) -> None:
        """Переходит в состояние Shutdown (готов к switch on)."""
        _LOGGER.info("Sending shutdown command")
        self._write_controlword(controlword_for_state(DriveState.READY_TO_SWITCH_ON))
        self.wait_for_state(DriveState.READY_TO_SWITCH_ON)

    def switch_on(self) -> None:
        """Переходит в состояние Switch On."""
        _LOGGER.info("Sending switch-on command")
        self._write_controlword(controlword_for_state(DriveState.SWITCHED_ON))
        self.wait_for_state(DriveState.SWITCHED_ON)

    def enable_operation(self) -> None:
        """Включает работу (operation enabled)."""
        _LOGGER.info("Enabling operation")
        self._write_controlword(controlword_for_state(DriveState.OPERATION_ENABLED))
        self.wait_for_state(DriveState.OPERATION_ENABLED)

    def disable_voltage(self) -> None:
        """Выключает питание (Switch On Disabled)."""
        _LOGGER.info("Disabling voltage")
        self._write_controlword(controlword_for_state(DriveState.SWITCH_ON_DISABLED))
        self.wait_for_state(DriveState.SWITCH_ON_DISABLED)

    def quick_stop(self) -> None:
        """Выполняет быстрый стоп."""
        _LOGGER.info("Executing quick stop")
        self._write_controlword(controlword_for_state(DriveState.QUICK_STOP_ACTIVE))
        self.wait_for_state(DriveState.QUICK_STOP_ACTIVE)

    def initialize_drive(self) -> None:
        """
        Стандартный запуск привода:
        Если fault — сброс, затем shutdown, switch on, enable operation.
        """
        _LOGGER.info("Initializing drive state machine")
        try:
            self.fault_reset()
        except FaultState:
            _LOGGER.warning("Fault present at start, tried reset")

        self.shutdown()
        self.switch_on()
        self.enable_operation()

    def stop_drive(self) -> None:
        """
        Остановить и отключить привод (переход в SWITCH_ON_DISABLED).
        """
        _LOGGER.info("Stopping drive")
        self.disable_voltage()

if __name__ == "__main__":
    from transport import ModbusTcpTransport
    from protocol import DryveSDO

    with ModbusTcpTransport("127.0.0.1", debug=True) as transport:
        sdo = DryveSDO(transport)
        fsm = DriveStateMachine(sdo)
        fsm.initialize_drive()
        # теперь привод в Operation Enabled
