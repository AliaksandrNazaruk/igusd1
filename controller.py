"""
controller.py — High-level API для dryve D1 (igus), объединяющий state machine, SDO, диагностику.

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
    """
    High-level API для управления dryve D1.
    Все команды безопасно проверяют состояния и могут поднимать исключения.
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
            # Здесь только то, что безопасно. 
            # Остановить heartbeat, обнулить ссылки, корректно завершить работу,
            # Но НЕ опрашивай лишний раз hardware!
            # Например:
            # self.sdo.close()  # если есть у SDO метод закрытия
            # self.fsm.stop_drive() # если уверен, что железо онлайн
            pass
        except Exception as e:
            print(f"Exception in close(): {e}")
            _LOGGER.error(f"Exception in close(): {e}")

    def __enter__(self):
        """
        Вход в контекстный менеджер.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print("[DryveController] __exit__ called")
        try:
            self.close()
        except Exception as e:
            print(f"Exception in __exit__: {e}")
            _LOGGER.error(f"Exception in __exit__: {e}")
        # Не подавлять исключение, если только специально не нужно

    def __del__(self):
        """
        На всякий случай, если объект удаляется — попытаться корректно завершить работу.
        """
        print("[DryveController] __del__ called")
        try:
            self.close()
        except Exception as e:
            # Деструктор — избегаем аварий, поэтому только warning
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
        """
        Безопасная инициализация привода: сброс fault, переход в Operation Enabled.
        """
        sw = Statusword(self.get_statusword())
        self.fsm.initialize_drive()
        self.update_status()

    def move_to_position(self, position_mm: int, velocity_mm_s: int = 2000, acceleration_mm_s: int = 2000):
        """
        Команда движения в позицию (Profile Position Mode).
        :param position_mm: целевая позиция (мм, float)
        :param velocity_mm_s: (опционально) скорость (мм/с)
        :param wait: ждать ли достижения цели
        :param tolerance_mm: допустимая ошибка по положению (мм)
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
        """
        Запуск гоминга (режим homing, стандартный режим 6 для CiA 402).
        """
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
        """
        Ждёт завершения гоминга (обычно по специальному биту или достижению позиции 0).
        """
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
        """
        Быстрая остановка и выключение привода.
        """
        _LOGGER.info("STOP requested")
        self.fsm.quick_stop()
        self.update_status()

    def emergency_shutdown(self):
        """
        Эмердженси — сразу выключает напряжение.
        """
        _LOGGER.critical("EMERGENCY SHUTDOWN!")
        self.fsm.disable_voltage()
        self.update_status()

    def get_actual_position(self) -> int:
        """Возврат кешированной позиции."""
        return self.sdo.read(ODKey.ACTUAL_POSITION)
    
    def get_homing_status(self) -> bool:
        """Возврат кешированной позиции."""
        return bool(self.sdo.read(ODKey.HOMING_STATUS))
    
    def get_actual_velocity(self) -> int:
        """Возврат кешированной скорости."""
        return self.sdo.read(ODKey.ACTUAL_VELOCITY)
    
    def get_actual_acceleration(self) -> int:
        return self.sdo.read(ODKey.PROFILE_ACCELERATION)
    
    def get_statusword(self) -> int:
        """Читает statusword непосредственно с драйва (SDO)."""
        return self.sdo.read(ODKey.STATUSWORD)

    def get_error(self) -> bool:
        """Возврат последнего значения error register."""
        sw = Statusword(self.get_statusword())
        self.status.error = sw.fault
        return sw.fault
    

    @property
    def position(self) -> int:
        """Последнее известное положение в мм."""
        return self.status.position
    
    @property
    def velocity(self) -> int:
        """Последняя измеренная скорость мм/с."""
        return self.status.velocity
    
    @property
    def acceleration(self) -> int:
        """Последняя измеренная скорость мм/с."""
        return self.status.acceleration
    
    @property
    def statusword(self) -> int:
        """Последняя измеренная скорость мм/с."""
        return self.status.statusword
    
    @property
    def is_homed(self) -> bool:
        """Флаг завершенного гоминга (bit 12 statusword)."""
        return self.status.is_homed
    @property

    def is_motion(self) -> bool:
        """Флаг завершенного гоминга (bit 12 statusword)."""
        return self.status.is_motion
    
    @property
    def error_state(self) -> bool:
        """Последний прочитанный error register."""
        return self.status.error


# if __name__ == "__main__":
#     from transport import ModbusTcpTransport
#     from protocol import DryveSDO
#     from machine import DriveStateMachine
#     import threading
#     print("Нагрузочный пезапуск в цикле")
#     n = 0
#     while True:
#         n = n+1
#         print("Цикл: " +str(n))
#         while True:
#             with ModbusTcpTransport("127.0.0.1", debug=True) as transport:
#                 sdo = DryveSDO(transport)
#                 fsm = DriveStateMachine(sdo)
#                 with DryveController(sdo, fsm) as ctrl:
#                     try:
#                         ctrl.get_actual_position()
#                     except:
#                         print("Оставшиеся потоки:", threading.enumerate())
#                         break
