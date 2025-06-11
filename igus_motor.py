import threading
import queue
import time
from typing import Callable, Any, Optional, Dict
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/../.."))

from drivers.igus_scripts.transport import ModbusTcpTransport
from drivers.igus_scripts.protocol import DryveSDO
from drivers.igus_scripts.machine import DriveStateMachine
from drivers.igus_scripts.controller import DryveController

class IgusCommand:
    def __init__(self, func: Callable, args: tuple = (), kwargs: dict = None, result_queue: Optional[queue.Queue] = None):
        self.func = func
        self.args = args
        self.kwargs = kwargs or {}
        self.result_queue = result_queue

class IgusMotor:
    """
    Singleton-объект для dryve D1: работает через новый стек, но с совместимым API.
    """

    def __init__(self, ip_address: str, port: int = 502):
        self.ip_address = ip_address
        self.port = port

        self._cmd_queue = queue.Queue()
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._status_lock = threading.Lock()
        self._stop_event = threading.Event()

        # Внутренние состояния (кэш, не опрашивается лишний раз!)
        self._connected = False
        self._active = False
        self._position = 0.0
        self._homed = False
        self._last_error = None
        self._statusword = 0
        self._last_status = None
        self._controller = None

        self._start_connection()
        if self._connected:
            self._worker_thread.start()
        else:
            raise Exception(f"Failed to connect to {ip_address}:{port}: {self._last_error}")

    def _start_connection(self, retries=5, retry_delay=10.0):
        while True:
            try:
                self._transport = ModbusTcpTransport(self.ip_address, self.port)
                self._transport.connect()
                self._sdo = DryveSDO(self._transport)
                self._fsm = DriveStateMachine(self._sdo)
                self._controller = DryveController(self._sdo, self._fsm)
                # Первичная инициализация: safe enable
                self._controller.initialize()
                with self._status_lock:
                    self._connected = True
                    self._last_error = None
                    self._update_state(force=True)
                return
            except Exception as e:
                with self._status_lock:
                    self._connected = False
                    self._last_error = str(e)
                    self._active = False
                time.sleep(retry_delay)
        raise Exception(f"Failed to connect to {self.ip_address}:{self.port}: {self._last_error}")

    def _worker(self):
        while not self._stop_event.is_set():
            try:
                cmd: IgusCommand = self._cmd_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                result = cmd.func(*cmd.args, **cmd.kwargs)
                with self._status_lock:
                    self._update_state(force=True)
                    self._last_error = None
                if cmd.result_queue:
                    cmd.result_queue.put((True, result))
            except Exception as e:
                with self._status_lock:
                    self._last_error = str(e)
                    self._connected = False
                    self._active = False
                # server_logger.log_event('error', f'IgusMotor worker error: {e}')
                
                # self._reconnect()
                if cmd.result_queue:
                    cmd.result_queue.put((False, e))

    def _reconnect(self):
        try:
            self._transport.close()
        except Exception:
            pass
        time.sleep(1)
        self._start_connection()

    def shutdown(self):
        """Корректно завершить работу и поток."""
        self._stop_event.set()
        self._worker_thread.join(timeout=2)
        try:
            self._transport.close()
        except Exception:
            pass
        with self._status_lock:
            self._connected = False
            self._active = False

    # ------------- PUBLIC API -------------
    def home(self, blocking=True):
        result = self._enqueue(self._controller.home, (), blocking=blocking)
        with self._status_lock:
            self._update_state(force=True)  # << обнови после homing
        return result

    def move_to_position(self, target_position, velocity=5000, acceleration=1000, blocking=True):
        with self._status_lock:
            if not self._homed:
                raise Exception("Movement impossible: Homing required first.")
        result = self._enqueue(
            self._controller.move_to_position,
            (target_position, velocity, True),  # wait=True
            blocking=blocking,
        )
        with self._status_lock:
            self._update_state(force=True)  # << после движения
        return result

    def fault_reset(self, blocking=True):
        result = self._enqueue(self._controller.fsm.fault_reset, (), blocking=blocking)
        with self._status_lock:
            self._update_state(force=True)
        return result

    # --- State getters ---
    def get_position(self):
        with self._status_lock:
            return self._position

    def is_homed(self):
        with self._status_lock:
            return self._homed

    def is_active(self):
        with self._status_lock:
            return self._active

    def get_statusword(self):
        with self._status_lock:
            return self._statusword

    def get_error(self):
        with self._status_lock:
            return self._last_error

    def is_connected(self):
        with self._status_lock:
            return self._connected

    def get_status(self) -> Dict[str, Any]:
        with self._status_lock:
            return {
                "position": self._position,
                "homed": self._homed,
                "active": self._active,
                "last_error": self._last_error,
                "connected": self._connected,
                "statusword": self._statusword,
            }

    # --- Helpers ---
    def _update_state(self, force=False):
        try:
            self._position = self._controller.get_actual_position()
            if not self._homed or not self._active:
                self._statusword = self._controller.get_statusword()
            self._homed = self._controller.get_homing_status()
            in_motion = (self._statusword & 0x1F) == 0x1F  # или другое состояние движения
            fault = bool(self._statusword & 0x08)
            self._active = in_motion and not fault
        except Exception as e:
            self._last_error = str(e)

    def _enqueue(self, func, args, blocking=True):
        result_queue = queue.Queue(maxsize=1) if blocking else None
        cmd = IgusCommand(func, args, {}, result_queue)
        self._cmd_queue.put(cmd)
        if blocking:
            ok, result = result_queue.get()
            if ok:
                return result
            else:
                raise result
        return None

    # context manager support
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()

# === Пример использования ===
if __name__ == "__main__":
    import logging

    logging.basicConfig(
        level=logging.INFO,  # или INFO для менее подробных логов
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    motor = IgusMotor("127.0.0.1", 502)
    position = 30000
    
        # motor.get_statusword()
        # motor.fault_reset()
    # motor.home()

    while True:
        try:
            motor.move_to_position(5000, velocity=2000)
            motor.move_to_position(30000, velocity=2000)
        except:
            print(f"[Demo] Ошибка: ")
            # if e.args[0] == 'Drive reports FAULT bit set' or e.args[0] == 'Timeout waiting for state OPERATION_ENABLED':
            try:
                motor._controller.initialize()
            except:
                print("error")
