"""
controller.py — High-level API для dryve D1 (igus), объединяющий state machine, SDO, диагностику.

© 2025 Your-Company / MIT-license
"""

import time
import logging
from dataclasses import dataclass, field

from drivers.igus_scripts.protocol import DryveSDO
from drivers.igus_scripts.machine import DriveStateMachine
from drivers.igus_scripts.od import ODKey
from drivers.igus_scripts.state_bits import Statusword, CW_START_MOTION, DriveState, SW_OP_MODE_SPECIFIC, parse_drive_state

_LOGGER = logging.getLogger(__name__)


@dataclass
class DriveStatus:
    """Cached drive status snapshot."""

    position_mm: float = 0.0
    velocity_mm_s: float = 0.0
    statusword: int = 0
    error_register: int = 0
    state: bool = False
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
        try:
            transport = self.sdo.transport
            if getattr(transport, "_heartbeat_callback", None) is None:
                transport._heartbeat_callback = self.update_status
        except AttributeError:
            pass

    def update_status(self) -> DriveStatus:
        """Read drive status and update the cached dataclass."""
        pos = self.sdo.read(ODKey.ACTUAL_POSITION)
        vel = self.sdo.read(ODKey.ACTUAL_VELOCITY)
        sw = self.sdo.read(ODKey.STATUSWORD)
        # err = self.sdo.read(ODKey.ERROR_REGISTER)
        hom = bool(self.sdo.read(ODKey.HOMING_STATUS))
        st = parse_drive_state(sw)
        self.status = DriveStatus(
            position_mm=pos,
            velocity_mm_s=vel,
            statusword=sw,
            error_register=0,
            state=hom,
            updated_at=time.time(),
        )
        return self.status

    def initialize(self):
        """
        Безопасная инициализация привода: сброс fault, переход в Operation Enabled.
        """
        self.fsm.initialize_drive()
        self.update_status()

    def move_to_position(self, position_mm: float, velocity_mm_s: float = None, wait: bool = True, tolerance_mm: float = 0.1):
        """
        Команда движения в позицию (Profile Position Mode).
        :param position_mm: целевая позиция (мм, float)
        :param velocity_mm_s: (опционально) скорость (мм/с)
        :param wait: ждать ли достижения цели
        :param tolerance_mm: допустимая ошибка по положению (мм)
        """
        _LOGGER.info(f"Move to position {position_mm:.3f} mm")
        # Проверяем, что привод включён и готов
        self.fsm.enable_operation()

        # Устанавливаем режим Profile Position (обычно 1)
        self.sdo.write(ODKey.MODE_OF_OPERATION, 1)  # Profile Position Mode

        if velocity_mm_s is not None:
            self.sdo.write(ODKey.TARGET_VELOCITY, velocity_mm_s)

        self.sdo.write(ODKey.TARGET_POSITION, position_mm)

        # Стартуем движение согласно CiA-402: выставляем биты 0..4
        self.sdo.write(ODKey.CONTROLWORD, CW_START_MOTION)

        if wait:
            self.wait_until_target_reached(target=position_mm, tolerance=tolerance_mm)
        self.update_status()

    def wait_until_target_reached(self, target: float = None, tolerance: float = 0.1, timeout: float = 100.0):
        """
        Ожидает, пока TargetReached или позиция не окажется вблизи target (если задан).
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.sdo.read(ODKey.STATUSWORD)
            sw = Statusword(status)
            if sw.fault:
                raise RuntimeError("Fault detected during move")
            if sw.target_reached:
                _LOGGER.info("Target reached (bit)")
                return
            if target is not None:
                pos = self.position
                if abs(pos - target) <= tolerance:
                    _LOGGER.info(f"Target reached (pos): {pos:.3f} mm ≈ {target:.3f} mm")
                    return
            time.sleep(0.05)
        raise TimeoutError("Timeout waiting for target position reached")
    
    def set_mode(self, mode, wait: bool = True):
        self.sdo.write(ODKey.MODE_OF_OPERATION, mode)  # Homing Mode
        time.sleep(1)


    def home(self, wait: bool = True):
        """
        Запуск гоминга (режим homing, стандартный режим 6 для CiA 402).
        """
        _LOGGER.info("Starting homing sequence")
        self.fsm.enable_operation()
        self.sdo.write(ODKey.MODE_OF_OPERATION, 6)  # Homing Mode
        # Homing method можно настроить через другие OD, если требуется

        # Запуск гоминга — подаём команду 0x001F как в эталонной реализации
        self.sdo.write(ODKey.CONTROLWORD, CW_START_MOTION)
        time.sleep(0.1)

        if wait:
            self.wait_homing_complete()
        self.update_status()

    def wait_homing_complete(self, timeout: float = 100.0):
        """
        Ждёт завершения гоминга (обычно по специальному биту или достижению позиции 0).
        """
        _LOGGER.info("Waiting for homing complete")
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.sdo.read(ODKey.STATUSWORD)
            sw = Statusword(status)
            if sw.fault:
                _LOGGER.info(f"[DEBUG] FAULT DETECTED! STATUSWORD=0x{status:04X}")
                raise RuntimeError("Fault detected during move")
            if sw.target_reached:
                _LOGGER.info("Homing complete (TargetReached)")
                self.update_status()
                return
            time.sleep(0.05)
        raise TimeoutError("Timeout during homing")

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

    def get_actual_position(self) -> float:
        """Возврат кешированной позиции."""
        return self.status.position_mm
    
    def get_homing_status(self) -> bool:
        """Возврат кешированной позиции."""
        return self.status.state
    
    def get_actual_velocity(self) -> float:
        """Возврат кешированной скорости."""
        return self.status.velocity_mm_s

    def get_statusword(self) -> int:
        """Читает statusword непосредственно с драйва (SDO)."""
        return self.sdo.read(ODKey.STATUSWORD)


    def get_error_register(self) -> int:
        """Возврат последнего значения error register."""
        return self.status.error_register

    @property
    def position(self) -> float:
        """Последнее известное положение в мм."""
        return self.status.position_mm

    @property
    def velocity(self) -> float:
        """Последняя измеренная скорость мм/с."""
        return self.status.velocity_mm_s

    @property
    def state(self) -> DriveState:
        """Текущее состояние CiA-402 согласно кешу."""
        return self.status.state

    @property
    def is_homed(self) -> bool:
        """Флаг завершенного гоминга (bit 12 statusword)."""
        return bool(self.status.statusword & SW_OP_MODE_SPECIFIC)

    @property
    def error_code(self) -> int:
        """Последний прочитанный error register."""
        return self.status.error_register

    def get_predefined_error_field(self):
        """Чтение массива последних ошибок (если поддерживается устройством)."""
        return self.sdo.read(ODKey.PREDEFINED_ERROR_FIELD)

    def store_parameters(self):
        """
        Сохраняет параметры в энергонезависимой памяти (NVRAM).
        """
        _LOGGER.info("Store parameters to NVRAM")
        self.sdo.store_parameters()

    # Можно расширить методами "move_velocity", "jog", "set_profile", "diagnose" и т.д.
