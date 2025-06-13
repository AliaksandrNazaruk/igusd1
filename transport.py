"""
transport.py — надежный, отказоустойчивый Modbus TCP клиент с поддержкой reconnect,
heartbeat, thread-safe и extensible logging.

© 2025 Your-Company / MIT-license

Важность: отвечает за стабильный, безошибочный обмен с приводом dryve D1.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/../.."))

import struct
import socket
import threading
import time
import logging
from typing import Optional, Callable

from drivers.igus_scripts.exceptions import TransportError, ConnectionLost, ConnectionTimeout


_LOGGER = logging.getLogger(__name__)


class ModbusTcpTransport:
    """
    Надежный Modbus TCP транспорт с автоматическим reconnect и heartbeat.

    Особенности:
      - потокобезопасен (Lock)
      - авто-переподключение при ошибках
      - поддержка таймаутов
      - heartbeat для удержания соединения живым
      - контекстный менеджер (with)
    """

    def __init__(
        self,
        ip: str,
        port: int = 502,
        timeout: float = 2.0,
        max_retries: int = 3,
        reconnect_delay: float = 1.0,
        unit_id: int = 0,
        debug: bool = False,
        heartbeat_interval: Optional[float] = 2.0,
        heartbeat_callback: Optional[Callable[[], None]] = None,
    ):
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.max_retries = max_retries
        self.reconnect_delay = reconnect_delay
        self.unit_id = unit_id
        self.debug = debug

        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._transaction_id = 0

        # Heartbeat
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_callback = heartbeat_callback
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_stop_event = threading.Event()

    def connect(self) -> None:
        """Установить TCP соединение."""
        self.close()  # Закрыть старое, если есть
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect((self.ip, self.port))
        except (socket.timeout, OSError) as ex:
            _LOGGER.error(f"Connection to {self.ip}:{self.port} failed: {ex}")
            sock.close()
            raise ConnectionTimeout(f"Could not connect to {self.ip}:{self.port}") from ex

        self._sock = sock
        self._transaction_id = 0
        if self.debug:
            _LOGGER.debug(f"[transport] Connected to {self.ip}:{self.port}")

    def close(self) -> None:
        """Закрыть сокет и остановить heartbeat."""
        self.stop_heartbeat()
        if self._sock:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._sock.close()
            self._sock = None
            if self.debug:
                _LOGGER.debug(f"[transport] Closed connection to {self.ip}:{self.port}")

    def __enter__(self):
        self.connect()
        if self._heartbeat_interval:
            self.start_heartbeat()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _next_transaction_id(self) -> int:
        self._transaction_id = (self._transaction_id + 1) & 0xFFFF
        return self._transaction_id

    def _sendall(self, data: bytes) -> None:
        """Обертка с защитой от разрыва."""
        if not self._sock:
            raise ConnectionLost("Socket is closed")

        try:
            self._sock.sendall(data)
        except (BrokenPipeError, ConnectionResetError, OSError) as ex:
            self._sock.close()
            self._sock = None
            raise ConnectionLost("Connection lost during send") from ex

    def _recv_exact(self, n: int) -> bytes:
        """Читать ровно n байт, или бросать ошибку."""
        if not self._sock:
            raise ConnectionLost("Socket is closed")

        buf = b""
        while len(buf) < n:
            try:
                chunk = self._sock.recv(n - len(buf))
            except socket.timeout as ex:
                raise ConnectionTimeout("Timeout during recv") from ex
            if not chunk:
                self._sock.close()
                self._sock = None
                raise ConnectionLost("Connection lost during recv")
            buf += chunk
        return buf

    def send_request(self, pdu: bytes) -> tuple[int, bytes]:
        """
        Отправить Modbus PDU (без MBAP) и получить ответ.

        Возвращает кортеж ``(transaction_id, response_bytes)``. Метод потокобезопасен,
        выполняет автоматический reconnect и повторяет запрос при ошибках.
        """
        
        with self._lock:
            last_exception = None
            for attempt in range(1, self.max_retries + 1):
                try:
                    if self._sock is None:
                        self.connect()

                    tid = self._next_transaction_id()
                    length = len(pdu) + 1  # +1 unit_id
                    header = struct.pack(">HHHB", tid, 0, length, self.unit_id)
                    packet = header + pdu
                    
                    if self.debug:
                        _LOGGER.debug(f"[TX {tid:#06x}] {packet.hex(' ')}")
                    # print(list(packet))
                    self._sendall(packet)

                    mbap = self._recv_exact(7)
                    if len(mbap) != 7:
                        raise TransportError(f"MBAP header too short: got {len(mbap)} bytes")
                    resp_tid, protocol, resp_len, unit_id = struct.unpack(">HHHB", mbap)
                    if resp_tid != tid:
                        raise TransportError(f"Transaction ID mismatch: sent {tid}, received {resp_tid}")

                    payload_len = resp_len - 1
                    payload = self._recv_exact(payload_len)
                    if len(payload) != payload_len:
                        raise TransportError(f"Payload length mismatch: expected {payload_len}, got {len(payload)}")


                    full_resp = mbap + payload
                    # print(list(full_resp))
                    if self.debug:
                        _LOGGER.debug(f"[RX {resp_tid:#06x}] {full_resp.hex(' ')}")

                    return tid, full_resp

                except (ConnectionLost, ConnectionTimeout, TransportError, socket.error) as ex:
                    last_exception = ex
                    _LOGGER.warning(f"[attempt {attempt}/{self.max_retries}] Transport error: {ex}. Reconnecting...")
                    self.close()
                    time.sleep(self.reconnect_delay)

            raise TransportError(f"Failed after {self.max_retries} retries") from last_exception

    # ================= Heartbeat ===============

    def start_heartbeat(self) -> None:
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return  # Уже запущен

        self._heartbeat_stop_event.clear()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

        if self.debug:
            _LOGGER.debug(f"[heartbeat] Started heartbeat thread with interval {self._heartbeat_interval}s")

    def stop_heartbeat(self) -> None:
        """Остановить heartbeat-поток."""
        if self._heartbeat_thread:
            self._heartbeat_stop_event.set()
            self._heartbeat_thread.join(timeout=2)
            self._heartbeat_thread = None
            self._heartbeat_stop_event.clear()

            if self.debug:
                _LOGGER.debug("[heartbeat] Stopped heartbeat thread")

    def _heartbeat_loop(self) -> None:
        """Фоновый loop для heartbeat."""
        while not self._heartbeat_stop_event.is_set():
            try:
                # if self._heartbeat_callback:
                #     self._heartbeat_callback()
                # else:
                    # По умолчанию — отправить чтение statusword (0x6041)
                    pdu = self._default_heartbeat_pdu()
                    # ignore response tuple
                    self.send_request(pdu)
            except Exception as e:
                _LOGGER.warning(f"[heartbeat] Exception in heartbeat: {e}")
            self._heartbeat_stop_event.wait(self._heartbeat_interval or 2.0)
        print("[heartbeat] Gracefully exited heartbeat loop")

    def _default_heartbeat_pdu(self) -> bytes:
        """PDU для опроса statusword, сформированный через PacketBuilder."""
        from packet import ModbusPacketBuilder
        from od import ODKey

        return ModbusPacketBuilder.build_read_request(ODKey.STATUSWORD)


# import time

# def dummy_callback():
#     print("[heartbeat] ping")

# with ModbusTcpTransport("127.0.0.1", debug=True, heartbeat_interval=0.1, heartbeat_callback=dummy_callback) as tr:
#     time.sleep(2)   # Даем heartbeat поработать

# print("Вышли из контекста — heartbeat должен остановиться!")
# time.sleep(1)
