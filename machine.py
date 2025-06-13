"""
machine.py — управление state machine dryve D1 (CiA 402)

© 2025 Aliaksandr Nazaruk / MIT-license
"""

import time
import logging

from drivers.igus_scripts.exceptions import FaultState, OperationTimeout
from drivers.igus_scripts.od import ODKey
from drivers.igus_scripts.state_bits import (
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

    def __init__(self, sdo, poll_delay=1, timeout=5.0, parse_drive_state_fn=None):
        self.sdo = sdo
        self.poll_delay = poll_delay
        self.timeout = timeout
        from drivers.igus_scripts.state_bits import parse_drive_state as default_parser
        self._parse_drive_state = parse_drive_state_fn or default_parser

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

            current_state = self._parse_drive_state(statusword_val)
            if current_state == target_state:
                return
            time.sleep(self.poll_delay)

        raise OperationTimeout(f"Timeout waiting for state {target_state.name}")

    def fault_reset(self) -> None:
        """Сбрасывает fault, если есть."""
        self.set_mode(6)
        self.set_mode(1)
        sw = self._read_statusword()
        if not sw.fault:
            _LOGGER.debug("No fault to reset")
            return
        _LOGGER.info("Performing fault reset")
        self._write_controlword(controlword_for_state(DriveState.FAULT))
        time.sleep(self.poll_delay)
        self.wait_for_state(DriveState.SWITCH_ON_DISABLED)

    def shutdown(self) -> None:

        """Переходит в состояние Shutdown (готов к switch on)."""
        _LOGGER.info("Sending shutdown command")
        self._write_controlword(controlword_for_state(DriveState.READY_TO_SWITCH_ON))
        self.wait_for_state(DriveState.READY_TO_SWITCH_ON)
        # self.disable_voltage(
        
    def set_mode(self, mode, wait: bool = True):
        self.sdo.write(ODKey.MODE_OF_OPERATION, mode)  # Homing Mode
        time.sleep(1)

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

    with ModbusTcpTransport("192.168.1.230", debug=True) as transport:
        sdo = DryveSDO(transport)
        fsm = DriveStateMachine(sdo)
        fsm.initialize_drive()
        while True:
            try:
                fsm.shutdown()
                time.sleep(2)
                fsm.switch_on()
                time.sleep(2)
            except:
                try:
                    fsm.fault_reset()
                except:
                    print("error")

