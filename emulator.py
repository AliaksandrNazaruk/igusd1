"""
emulator.py — simple Modbus TCP server emulating a minimal subset of the
Igus dryve D1 controller. It allows testing the driver code without real hardware.

© 2025 Your-Company / MIT-license
"""

from __future__ import annotations

import socket
import struct
import threading
import time

MODBUS_PORT = 502


class MotorState:
    """A very small model of the drive's state."""

    def __init__(self) -> None:
        self.position = 0
        self.velocity = 0
        self.target_position = 0
        self.status_word = 0x0006  # Shutdown by default
        self.operation_mode = 1  # 1 = Profile Position
        self.is_moving = False
        self._move_thread: threading.Thread | None = None

    def move_to(self, pos: int, vel: int) -> None:
        if self.is_moving:
            return
        self.target_position = pos
        self.velocity = vel
        self.is_moving = True
        self._move_thread = threading.Thread(target=self._do_move, daemon=True)
        self._move_thread.start()

    def _do_move(self) -> None:
        duration = abs(self.target_position - self.position) / max(abs(self.velocity), 1)
        steps = int(duration * 10)
        delta = (self.target_position - self.position) / max(steps, 1)
        for _ in range(steps):
            self.position += delta
            self.status_word = 0x001F  # moving
            time.sleep(0.1)
        self.position = self.target_position
        self.status_word = 0x0027  # arrived, operation enabled
        self.is_moving = False


class IgusD1Emulator:
    """Minimal Modbus TCP emulator for the dryve D1 controller."""

    def __init__(self, host: str = "0.0.0.0", port: int = MODBUS_PORT) -> None:
        self.state = MotorState()
        self.host = host
        self.port = port
        self._server_sock: socket.socket | None = None
        self._running = False

    def start(self) -> None:
        """Run the emulator server loop."""
        self._running = True
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, self.port))
        self._server_sock.listen(5)
        print(f"Emulator started at {self.host}:{self.port}")
        while self._running:
            try:
                client, addr = self._server_sock.accept()
            except OSError:
                break
            print(f"Client: {addr}")
            threading.Thread(target=self.handle_client, args=(client,), daemon=True).start()

    def stop(self) -> None:
        """Stop the emulator and close the socket."""
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._server_sock.close()
            self._server_sock = None

    def handle_client(self, client: socket.socket) -> None:
        """Handle a single client connection."""
        try:
            while self._running:
                mbap = self._recv_exact(client, 7)
                if not mbap:
                    break
                tid, pid, length, uid = struct.unpack(">HHHB", mbap)
                pdu = self._recv_exact(client, length - 1)
                if not pdu:
                    break
                response_pdu = self.handle_pdu(pdu)
                resp_mbap = struct.pack(">HHHB", tid, 0, len(response_pdu) + 1, 0)
                client.sendall(resp_mbap + response_pdu)
        except Exception as e:
            print(f"Client handler error: {e}")
        finally:
            client.close()

    # ----------------------------------------------------------
    def _recv_exact(self, sock: socket.socket, n: int) -> bytes | None:
        data = b""
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def _modbus_exception(self, func_code: int, exc_code: int) -> bytes:
        return bytes([func_code | 0x80, exc_code])

    def _build_response(self, req_pdu: bytes, data: bytes) -> bytes:
        header = req_pdu[:8]
        reserved = b"\x00\x00\x00"
        length_byte = len(data).to_bytes(1, "big")
        return header + reserved + length_byte + data

    def _handle_controlword(self, ctrl: int) -> None:
        if (ctrl & 0x000F) == 0x000F:
            self.state.status_word = 0x0027  # operation enabled + arrived
            if not self.state.is_moving:
                self.state.move_to(self.state.target_position, self.state.velocity)
        elif (ctrl & 0x0006) == 0x0006:
            self.state.status_word = 0x0006  # shutdown
            self.state.is_moving = False
        else:
            self.state.status_word = ctrl & 0xFFFF

    def handle_pdu(self, pdu: bytes) -> bytes:
        """Process a Modbus MEI 0x0D request PDU."""
        if len(pdu) < 13:
            return self._modbus_exception(pdu[0] if pdu else 0x2B, 0x03)
        if pdu[0] != 0x2B or pdu[1] != 0x0D:
            return self._modbus_exception(pdu[0], 0x01)

        rw = pdu[2]
        obj_idx = (pdu[5] << 8) | pdu[6]
        sub_idx = pdu[7]
        length = pdu[12]

        if length > 8:
            return self._modbus_exception(pdu[0], 0x03)

        if rw == 0:
            if obj_idx == 0x6041:
                data = self.state.status_word.to_bytes(2, "little")
                return self._build_response(pdu, data)
            if obj_idx == 0x6064:
                data = int(self.state.position).to_bytes(4, "little", signed=True)
                return self._build_response(pdu, data)
            if obj_idx == 0x606C:
                data = int(self.state.velocity).to_bytes(4, "little", signed=True)
                return self._build_response(pdu, data)
            return self._modbus_exception(pdu[0], 0x02)

        if rw == 1:
            expected_length = 13 + length
            if len(pdu) < expected_length:
                return self._modbus_exception(pdu[0], 0x03)

            data_bytes = pdu[13 : 13 + length]
            if obj_idx == 0x6040:
                ctrl = int.from_bytes(data_bytes, "little")
                self._handle_controlword(ctrl)
                return self._build_response(pdu, data_bytes)
            if obj_idx == 0x607A:
                pos = int.from_bytes(data_bytes, "little", signed=True)
                self.state.target_position = pos
                return self._build_response(pdu, data_bytes)
            if obj_idx == 0x6081:
                vel = int.from_bytes(data_bytes, "little", signed=True)
                self.state.velocity = vel
                return self._build_response(pdu, data_bytes)
            return self._modbus_exception(pdu[0], 0x02)

        return self._modbus_exception(pdu[0], 0x01)


if __name__ == "__main__":
    emu = IgusD1Emulator()
    try:
        emu.start()
    except KeyboardInterrupt:
        emu.stop()
