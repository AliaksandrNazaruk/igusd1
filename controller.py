"""
controller.py — high level API for the igus dryve D1 drive integrating the state
machine, SDO layer and diagnostics.

© 2025 Aliaksandr Nazaruk / MIT-license
"""

import time
import logging
from dataclasses import dataclass, field
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/../.."))

from drivers.igus_scripts.protocol import DryveSDO
from drivers.igus_scripts.machine import DriveStateMachine
from drivers.igus_scripts.od import ODKey
from drivers.igus_scripts.state_bits import Statusword, CW_START_MOTION, DriveState, SW_OP_MODE_SPECIFIC, parse_drive_state

_LOGGER = logging.getLogger(__name__)


@dataclass
class DriveStatus:
    """Cached drive status snapshot."""
    position: int = 0
    velocity: int = 0
    acceleration: int = 0 
    statusword: int = 0
    error: bool = False
    is_homed: bool = False
    is_motion: bool = False
    updated_at: float = field(default_factory=time.time)

class DryveController:
    """High level API for controlling the dryve D1.

    All commands validate the state first and may raise exceptions.
    """

    def __init__(self, sdo: DryveSDO, fsm: DriveStateMachine):
        self.sdo = sdo
        self.fsm = fsm
        self.status = DriveStatus()
        self._is_motion = False
        try:
            transport = self.sdo.transport
            if getattr(transport, "_heartbeat_callback", None) is None:
                transport._heartbeat_callback = self.update_status
        except AttributeError:
            pass

    def close(self):
        print("[DryveController] close() called")
        try:
            # Only perform operations that are safe here:
            # stop heartbeat, clear references, shut down cleanly,
            # but avoid additional hardware queries.
            # For example:
            # self.sdo.close()  # if SDO exposes a close() method
            # self.fsm.stop_drive()  # if you are sure the hardware is online
            pass
        except Exception as e:
            print(f"Exception in close(): {e}")
            _LOGGER.error(f"Exception in close(): {e}")

    def __enter__(self):
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print("[DryveController] __exit__ called")
        try:
            self.close()
        except Exception as e:
            print(f"Exception in __exit__: {e}")
            _LOGGER.error(f"Exception in __exit__: {e}")
        # Do not suppress exceptions unless explicitly required

    def __del__(self):
        """Attempt graceful shutdown when the object is deleted."""
        print("[DryveController] __del__ called")
        try:
            self.close()
        except Exception as e:
            # Destructor should avoid raising, so only log a warning
            _LOGGER.warning(f"Exception during controller destruction: {e}")

    def update_status(self) -> DriveStatus:
        """Read drive status and update the cached dataclass."""
        pos = self.get_actual_position()
        vel = self.get_actual_velocity()
        acc = self.get_actual_acceleration()
        sw = self.get_statusword()
        err = self.get_error()
        hom = self.get_homing_status()
        
        self.status = DriveStatus(
            position=pos,
            velocity=vel,
            acceleration=acc,
            statusword=sw,
            error=err,
            is_homed=hom,
            is_motion = self._is_motion,
            updated_at=time.time(),
        )
        return self.status

    def initialize(self):
        """Safely initialize the drive: clear faults and enter Operation Enabled state."""
        sw = Statusword(self.get_statusword())
        self.fsm.initialize_drive()
        self.update_status()

    def move_to_position(self, position_mm: int, velocity_mm_s: int = 2000, acceleration_mm_s: int = 2000):
        """Move to an absolute position using *Profile Position Mode*.

        :param position_mm: target position in millimetres
        :param velocity_mm_s: optional velocity in mm/s
        :param wait: unused, kept for API compatibility
        :param tolerance_mm: allowed position error in mm
        """
        try:
            _LOGGER.info(f"Move to position {position_mm:.3f} mm")
            self.fsm.enable_operation()
            self.sdo.write(ODKey.MODE_OF_OPERATION, 1)
            time.sleep(1)
            self.sdo.write(ODKey.PROFILE_VELOCITY, velocity_mm_s)
            self.sdo.write(ODKey.PROFILE_ACCELERATION, acceleration_mm_s)
            self.sdo.write(ODKey.TARGET_POSITION, position_mm)
            self.sdo.write(ODKey.CONTROLWORD, CW_START_MOTION)
            self.wait_motion_complete()
        finally:
            self.update_status()

    def home(self):
        """Start the homing sequence (mode 6 of CiA‑402)."""
        try:
            _LOGGER.info("Starting homing sequence")
            self.fsm.enable_operation()
            self.sdo.write(ODKey.MODE_OF_OPERATION, 6)
            time.sleep(1)
            self.sdo.write(ODKey.CONTROLWORD, CW_START_MOTION)
            time.sleep(1)
            self.wait_motion_complete()
        finally:
            self.update_status()

    def wait_motion_complete(self):
        """Wait until motion completes (typically by monitoring TargetReached or position 0)."""
        self._is_motion = True
        positions = []
        timer = 0
        _LOGGER.info("Waiting for motion complete")
        try:
            sw = Statusword(self.get_statusword())
            while not sw.target_reached:
                time.sleep(1)
                timer = timer + 1
                if timer>150:
                    raise TimeoutError("Timeout during motion")
                if sw.fault:
                    status = self.sdo.read(ODKey.STATUSWORD)
                    _LOGGER.info(f"FAULT DETECTED! STATUSWORD=0x{status:04X}")
                    raise RuntimeError("Fault detected during move")
                sw = Statusword(self.get_statusword())
                positions.append(self.get_actual_position())
                if len(positions) > 5:
                    positions.pop(0)
                    if all(abs(p - positions[0]) < 0.01 for p in positions):
                        _LOGGER.warning("motion stuck: position unchanged for %s seconds", 5)
                        raise TimeoutError(f"motion stuck (no position change for {5} sec)")
        finally:
            self._is_motion = False
            self.update_status()
            
    def stop(self):
        """Perform a quick stop and disable the drive."""
        _LOGGER.info("STOP requested")
        self.fsm.quick_stop()
        self.update_status()

    def emergency_shutdown(self):
        """Emergency shutdown — immediately disable power."""
        _LOGGER.critical("EMERGENCY SHUTDOWN!")
        self.fsm.disable_voltage()
        self.update_status()

    def get_actual_position(self) -> int:
        """Return the current position."""
        return self.sdo.read(ODKey.ACTUAL_POSITION)
    
    def get_homing_status(self) -> bool:
        """Return homing completion flag."""
        return bool(self.sdo.read(ODKey.HOMING_STATUS))
    
    def get_actual_velocity(self) -> int:
        """Return current velocity."""
        return self.sdo.read(ODKey.ACTUAL_VELOCITY)
    
    def get_actual_acceleration(self) -> int:
        return self.sdo.read(ODKey.PROFILE_ACCELERATION)
    
    def get_statusword(self) -> int:
        """Read the statusword directly from the drive via SDO."""
        return self.sdo.read(ODKey.STATUSWORD)

    def get_error(self) -> bool:
        """Return the latest value of the error register."""
        sw = Statusword(self.get_statusword())
        self.status.error = sw.fault
        return sw.fault
    

    @property
    def position(self) -> int:
        """Last known position in mm."""
        return self.status.position
    
    @property
    def velocity(self) -> int:
        """Last measured velocity in mm/s."""
        return self.status.velocity
    
    @property
    def acceleration(self) -> int:
        """Last measured acceleration in mm/s²."""
        return self.status.acceleration
    
    @property
    def statusword(self) -> int:
        """Last read statusword value."""
        return self.status.statusword
    
    @property
    def is_homed(self) -> bool:
        """True if homing completed (bit 12 of statusword)."""
        return self.status.is_homed
    @property

    def is_motion(self) -> bool:
        """True while motion command is in progress."""
        return self.status.is_motion
    
    @property
    def error_state(self) -> bool:
        """Latest error register state."""
        return self.status.error


# if __name__ == "__main__":
#     from transport import ModbusTcpTransport
#     from protocol import DryveSDO
#     from machine import DriveStateMachine
#     import threading
#     print("Stress test restart loop")
#     n = 0
#     while True:
#         n = n+1
#         print(f"Cycle: {n}")
#         while True:
#             with ModbusTcpTransport("127.0.0.1", debug=True) as transport:
#                 sdo = DryveSDO(transport)
#                 fsm = DriveStateMachine(sdo)
#                 with DryveController(sdo, fsm) as ctrl:
#                     try:
#                         ctrl.get_actual_position()
#                     except:
#                         print("Remaining threads:", threading.enumerate())
#                         break
