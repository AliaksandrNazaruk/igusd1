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

        self._transport = None
        self._sdo = None
        self._fsm = None
        self._controller = None
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

    def _start_connection(self, retries=3, retry_delay=3.0):
        while True:
            try:
                # ------> ВАЖНО! Не with, а явное создание!
                self._transport = ModbusTcpTransport(self.ip_address, self.port)
                self._transport.connect()
                self._sdo = DryveSDO(self._transport)
                self._fsm = DriveStateMachine(self._sdo)
                self._controller = DryveController(self._sdo, self._fsm)
                self._controller.initialize()
                with self._status_lock:
                    self._connected = True
                    self._last_error = None
                return
            except Exception as e:
                with self._status_lock:
                    self._connected = False
                    self._last_error = str(e)
                    self._active = False
                try:
                    if self._transport:
                        self._transport.close()
                except Exception:
                    pass
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
            if self._transport:
                self._transport.close()
        except Exception:
            pass
        time.sleep(1)
        self._start_connection()

    def shutdown(self):
        self._stop_event.set()
        self._worker_thread.join(timeout=2)
        try:
            if self._transport:
                self._transport.close()
        except Exception:
            pass
        with self._status_lock:
            self._connected = False
            self._active = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()

    # ------------- PUBLIC API -------------
    def home(self, blocking=True):
        result = self._enqueue(self._controller.home, (), blocking=blocking)
        return result

    def move_to_position(self, target_position, velocity=2000, acceleration=2000, blocking=True):
        with self._status_lock:
            if not self._controller.is_homed:
                raise Exception("Movement impossible: Homing required first.")
        result = self._enqueue(
            self._controller.move_to_position,(target_position, velocity, acceleration),blocking=blocking,)
        return result

    def fault_reset(self, blocking=True):
        result = self._enqueue(self._controller.initialize(), (), blocking=blocking)
        return result

    # --- State getters ---


    def get_statusword(self):
        with self._status_lock:
            return self._controller.get_statusword()

    def get_status(self) -> Dict[str, Any]:
        self._controller.get_error()
        with self._status_lock:
            return {
                "position": self._controller.position,
                "homed": self._controller.is_homed,
                "active": self._controller.is_motion,
                "error_state": self._controller.error_state,
                "connected": True,
                "statusword": self._controller.statusword,
            }


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

# === Пример использования ===
if __name__ == "__main__":
    import logging

    logging.basicConfig(
        level=logging.DEBUG,  # или INFO для менее подробных логов
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    motor = IgusMotor("192.168.1.230", 502)
    position = 30000
        # motor.get_statusword()
        
    # motor.fault_reset()
    motor.home()

    while True:
        try:
            motor.move_to_position(5000)
            print(motor.get_status())
            motor.move_to_position(15000)
            print(motor.get_status())
        except:
            print(f"[Demo] Ошибка: ")
            # if e.args[0] == 'Drive reports FAULT bit set' or e.args[0] == 'Timeout waiting for state OPERATION_ENABLED':
            try:
                print(motor.get_status())
                motor._controller.initialize()
                
            except:
                print("error")
