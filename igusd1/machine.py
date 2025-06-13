"""
machine.py — control of the dryve D1 state machine (CiA‑402).

© 2025 Aliaksandr Nazaruk / MIT-license
"""

import time
import logging

from .exceptions import FaultState, OperationTimeout
from .od import ODKey
from .state_bits import (
    DriveState,
    parse_drive_state,
    Statusword,
    controlword_for_state,
)

_LOGGER = logging.getLogger(__name__)


class DriveStateMachine:
    """Helper class to operate the dryve D1 CiA‑402 state machine.

    Requires a ``DryveSDO`` object to access Controlword/Statusword.
    """

    def __init__(self, sdo, poll_delay=1, timeout=5.0, parse_drive_state_fn=None):
        self.sdo = sdo
        self.poll_delay = poll_delay
        self.timeout = timeout
        from .state_bits import parse_drive_state as default_parser
        self._parse_drive_state = parse_drive_state_fn or default_parser

    def _read_statusword(self) -> Statusword:
        val = self.sdo.read(ODKey.STATUSWORD)
        return Statusword(val)

    def _write_controlword(self, cw_value: int) -> None:
        self.sdo.write(ODKey.CONTROLWORD, cw_value)

    def wait_for_state(self, target_state: DriveState) -> None:
        """Wait until the drive reaches ``target_state``.

        Raises :class:`OperationTimeout` if the timeout expires or
        :class:`FaultState` if a fault is detected.
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
        """Perform fault reset if required."""
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

        """Enter the ``Shutdown`` state (ready to switch on)."""
        _LOGGER.info("Sending shutdown command")
        self._write_controlword(controlword_for_state(DriveState.READY_TO_SWITCH_ON))
        self.wait_for_state(DriveState.READY_TO_SWITCH_ON)
        # self.disable_voltage(
        
    def set_mode(self, mode, wait: bool = True):
        self.sdo.write(ODKey.MODE_OF_OPERATION, mode)  # Homing Mode
        time.sleep(1)

    def switch_on(self) -> None:
        """Transition to ``Switch On`` state."""
        _LOGGER.info("Sending switch-on command")
        self._write_controlword(controlword_for_state(DriveState.SWITCHED_ON))
        self.wait_for_state(DriveState.SWITCHED_ON)

    def enable_operation(self) -> None:
        """Enable operation (``Operation Enabled`` state)."""
        _LOGGER.info("Enabling operation")
        self._write_controlword(controlword_for_state(DriveState.OPERATION_ENABLED))
        self.wait_for_state(DriveState.OPERATION_ENABLED)

    def disable_voltage(self) -> None:
        """Disable voltage (``Switch On Disabled``)."""
        _LOGGER.info("Disabling voltage")
        self._write_controlword(controlword_for_state(DriveState.SWITCH_ON_DISABLED))
        self.wait_for_state(DriveState.SWITCH_ON_DISABLED)

    def quick_stop(self) -> None:
        """Perform a quick stop."""
        _LOGGER.info("Executing quick stop")
        self._write_controlword(controlword_for_state(DriveState.QUICK_STOP_ACTIVE))
        self.wait_for_state(DriveState.QUICK_STOP_ACTIVE)

    def initialize_drive(self) -> None:
        """Standard start-up sequence.

        If a fault is present, perform a reset, then run shutdown,
        switch on and finally enable operation.
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
        """Stop and disable the drive (enter ``SWITCH_ON_DISABLED``)."""
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

