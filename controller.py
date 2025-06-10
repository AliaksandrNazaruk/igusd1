"""
controller.py — High-level API для dryve D1 (igus), объединяющий state machine, SDO, диагностику.

© 2025 Your-Company / MIT-license
"""

import time
import logging

from protocol import DryveSDO
from machine import DriveStateMachine
from od import ODKey
from state_bits import Statusword

_LOGGER = logging.getLogger(__name__)


class DryveController:
    """
    High-level API для управления dryve D1.
    Все команды безопасно проверяют состояния и могут поднимать исключения.
    """

    def __init__(self, sdo: DryveSDO, fsm: DriveStateMachine):
        self.sdo = sdo
        self.fsm = fsm

    def initialize(self):
        """
        Безопасная инициализация привода: сброс fault, переход в Operation Enabled.
        """
        self.fsm.initialize_drive()

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

        # Дёргаем Controlword для старта движения (0x3F/0x0F) — опционально по конкретной реализации

        if wait:
            self.wait_until_target_reached(target=position_mm, tolerance=tolerance_mm)

    def wait_until_target_reached(self, target: float = None, tolerance: float = 0.1, timeout: float = 10.0):
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
                pos = self.get_actual_position()
                if abs(pos - target) <= tolerance:
                    _LOGGER.info(f"Target reached (pos): {pos:.3f} mm ≈ {target:.3f} mm")
                    return
            time.sleep(0.05)
        raise TimeoutError("Timeout waiting for target position reached")

    def home(self, wait: bool = True):
        """
        Запуск гоминга (режим homing, стандартный режим 6 для CiA 402).
        """
        _LOGGER.info("Starting homing sequence")
        self.fsm.enable_operation()
        self.sdo.write(ODKey.MODE_OF_OPERATION, 6)  # Homing Mode
        # Homing method можно настроить через другие OD, если требуется

        # Запуск гоминга — выставляем бит Homing Start в Controlword (обычно бит 4)
        cw = self.sdo.read(ODKey.CONTROLWORD)
        self.sdo.write(ODKey.CONTROLWORD, cw | 0x0010)  # Установить бит 4 (Homing Start)
        time.sleep(0.1)

        if wait:
            self.wait_homing_complete()

    def wait_homing_complete(self, timeout: float = 20.0):
        """
        Ждёт завершения гоминга (обычно по специальному биту или достижению позиции 0).
        """
        _LOGGER.info("Waiting for homing complete")
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.sdo.read(ODKey.STATUSWORD)
            sw = Statusword(status)
            if sw.fault:
                raise RuntimeError("Fault detected during homing")
            if sw.target_reached:
                _LOGGER.info("Homing complete (TargetReached)")
                return
            time.sleep(0.05)
        raise TimeoutError("Timeout during homing")

    def stop(self):
        """
        Быстрая остановка и выключение привода.
        """
        _LOGGER.info("STOP requested")
        self.fsm.quick_stop()

    def emergency_shutdown(self):
        """
        Эмердженси — сразу выключает напряжение.
        """
        _LOGGER.critical("EMERGENCY SHUTDOWN!")
        self.fsm.disable_voltage()

    def get_actual_position(self) -> float:
        """Чтение текущей позиции в мм."""
        return self.sdo.read(ODKey.ACTUAL_POSITION)

    def get_actual_velocity(self) -> float:
        """Чтение текущей скорости в мм/с."""
        return self.sdo.read(ODKey.ACTUAL_VELOCITY)

    def get_statusword(self) -> int:
        """Чтение statusword (сырое значение)."""
        return self.sdo.read(ODKey.STATUSWORD)

    def get_error_register(self) -> int:
        """Чтение регистра ошибок."""
        return self.sdo.read(ODKey.ERROR_REGISTER)

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
