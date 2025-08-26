import socket
import struct
import threading
import time
import json
import os
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

MODBUS_PORT = 502
HTTP_PORT = 8001
import time
import threading

class ClientRegistry:
    def __init__(self):
        self.lock = threading.Lock()
        self.clients = {}  # {id: {'type': 'modbus'/'ws'/'http', 'address': str, 'status': 'online'/'offline', ...}}

    def update(self, client_id, **kwargs):
        with self.lock:
            self.clients.setdefault(client_id, {})
            self.clients[client_id].update(kwargs)
            self.clients[client_id]['last_seen'] = time.time()

    def remove(self, client_id):
        with self.lock:
            if client_id in self.clients:
                self.clients[client_id]['status'] = 'offline'
                self.clients[client_id]['last_seen'] = time.time()

    def all(self):
        with self.lock:
            # Считаем "offline", если давно не обновлялся
            now = time.time()
            out = []
            for cid, info in self.clients.items():
                status = info.get('status', 'offline')
                if status == 'online' and now - info['last_seen'] > 5:
                    status = 'offline'
                out.append({
                    'id': cid,
                    'type': info.get('type', 'unknown'),
                    'address': info.get('address', ''),
                    'status': status,
                    'last_seen': info['last_seen']
                })
            return out

CLIENTS = ClientRegistry()

class FakeDriveState:
    def __init__(self):
        # Statusword bits
        self.rswon = 1    # Ready to switch on
        self.swon = 0     # Switched on
        self.eo = 0       # Operation enabled
        self.fault = 0    # Fault
        self.ve = 0       # Voltage enabled
        self.qs = 1       # Quick stop
        self.swod = 0     # Switch on disabled
        self.warn = 0     # Warning
        self.na = 0       # Not used
        self.re = 1       # Remote
        self.tr = 1       # Target reached
        self.ila = 0      # Internal limit active
        self.oms = 0      # OpModeSpecific
        # Эмуляция других OD
        self.position = 0
        self.target_position = 0
        self.velocity = 0
        self.acceleration = 0
        self.homed = 0
        self.mode = 1
        self.is_moving = False
        self.emergency_active = False
        self._task_lock = threading.Lock()

        self._move_thread = None  # сохраним поток для прерывания

    def set_statusword(self, status_bytes):
        """Установить статусворд по байтам [lsb, msb]."""
        sw = status_bytes[0] | (status_bytes[1] << 8)
        self.rswon = (sw >> 0) & 1
        self.swon  = (sw >> 1) & 1
        self.eo    = (sw >> 2) & 1
        self.fault = (sw >> 3) & 1
        self.ve    = (sw >> 4) & 1
        self.qs    = (sw >> 5) & 1
        self.swod  = (sw >> 6) & 1
        self.warn  = (sw >> 7) & 1
        self.na    = (sw >> 8) & 1
        self.re    = (sw >> 9) & 1
        self.tr    = (sw >> 10) & 1
        self.ila   = (sw >> 11) & 1
        self.oms   = (sw >> 12) & 1

    def make_statusword(self):
        value = (
            (self.rswon & 1) << 0  |
            (self.swon & 1)  << 1  |
            (self.eo & 1)    << 2  |
            (self.fault & 1) << 3  |
            (self.ve & 1)    << 4  |
            (self.qs & 1)    << 5  |
            (self.swod & 1)  << 6  |
            (self.warn & 1)  << 7  |
            (self.na & 1)    << 8  |
            (self.re & 1)    << 9  |
            (self.tr & 1)    << 10 |
            (self.ila & 1)   << 11 |
            (self.oms & 1)   << 12
        )
        return value
    
    def move_to(self):
        if self.position == self.target_position:
            self.is_moving = False
            self.tr = 1
            return

        # если сейчас аварийный стоп – игнорируем
        if self.emergency_active:
            return

        # пытаемся занять лок
        if not self._task_lock.acquire(blocking=False):
            # другая задача уже выполняется
            return

        self.is_moving = True
        self.tr = 0

        def run():
            try:
                self._move_simulation()
            finally:
                self._task_lock.release()  # освободить лок

        t = threading.Thread(target=run, daemon=True)
        self._move_thread = t
        t.start()


    def _move_simulation(self):
        start_pos = self.position
        end_pos = self.target_position
        duration = 5.0
        steps = 1000
        step_time = duration / steps
        for i in range(steps):
            if self.emergency_active:  # остановка
                break
            self.position = int(start_pos + (end_pos - start_pos) * (i + 1) / steps)
            time.sleep(step_time)
        self.velocity = 0
        self.acceleration = 0
        self.tr = 1
        self.is_moving = False

    def emergency_stop(self, active: bool):
        self.emergency_active = active
        if active:
            # Останавливаем движение
            self.is_moving = False
            self.velocity = 0
            # Сбрасываем рабочие биты
            self.eo = 0
            self.swon = 0
            self.ve = 0
            self.fault = 1  # в аварийном состоянии
            self.tr = 0
        else:
            # Сбрасываем fault, но оставляем состояние FAULT
            # Пока пользователь не пошлёт 0x80 (Fault reset)
            self.fault = 1
    def do_home(self):
        if self.emergency_active:
            return

        if not self._task_lock.acquire(blocking=False):
            return

        self.is_moving = True
        self.tr = 0

        def run():
            try:
                self._home_simulation()
            finally:
                self._task_lock.release()

        threading.Thread(target=run, daemon=True).start()

    def _home_simulation(self):
        duration = 5.0
        steps = 100
        step_time = duration / steps
        for _ in range(steps):
            time.sleep(step_time)
        self.position = 0
        self.homed = 1
        self.tr = 1
        self.is_moving = False
        self.rswon = 1
        self.swon = 1
        self.eo = 1
        self.ve = 1

    def sdo_read(self, index, subindex):
        idx = index[1] | (index[0] << 8)
        if idx == 0x6041:  # Statusword
            sw = self.make_statusword()
            return struct.pack('<H', sw)
        if idx == 0x2014:  # Statusword
            return bytes([self.homed, 0])
        if idx == 0x6064:  # Position (int32)
            return struct.pack('<i', self.position)
        if idx == 0x606C:  # Velocity (int32)
            return struct.pack('<i', self.velocity)
        if idx == 0x6083:  # Velocity (int32)
            return struct.pack('<i', self.acceleration)
        if idx == 0x6098:  # Homing status (uint8)
            return bytes([self.homed])
        return bytes([0, 0])

    def sdo_write(self, index, subindex, value):
        idx = index[1] | (index[0] << 8)
        if self.emergency_active:
            return
        if idx == 0x6040:  # Controlword — команда
            if value == 0x80:  # Fault Reset
                self.fault = 0
                self.is_moving = False
                self.velocity = 0
                # Statusword: только rswon = 1, остальные 0
                self.rswon = 1; self.swon = self.eo = self.ve = self.tr = self.warn = 0
            elif value == 0x08:  # FAULT
                self.fault = 1
                self.is_moving = False
                self.velocity = 0
                self.eo = self.swon = self.ve = 0
            elif value == 0x06:  # Shutdown
                self.rswon = 1
                self.qs = 1         # <--- ВАЖНО!
                self.swon = self.eo = self.ve = self.tr = 0
                self.fault = 0

            elif value == 0x07:  # Switch On
                self.rswon = 1
                self.swon = 1
                self.qs = 1         # <--- ВАЖНО!
                self.eo = self.ve = self.tr = 0
                self.fault = 0
            elif value == 0x0F:  # Enable operation
                self.rswon = 1
                self.swon = 1
                self.eo = 1
                self.qs = 1         # <--- ВАЖНО!
                self.ve = 1
                self.tr = 1 if not self.is_moving else 0
                self.fault = 0
            # Shutdown
            elif value == 0x00:
                self.eo = 0
                self.swon = 0
                self.ve = 0

            elif value == 31:
                self.tr = 0
                if self.mode == 6:
                    self.do_home()
                if self.mode == 1:
                    self.move_to()
        elif idx == 0x6060:  # Mode of Operation
            self.mode = value
        elif idx == 0x607A:  # Target position
            self.target_position = int(value)
        elif idx == 0x6081:  # Target position
            self.velocity = int(value)
        elif idx == 0x6083:  # Target position
            self.acceleration = int(value)
        elif idx == 0x6098:  # Homed
            self.homed = value

def parse_modbus_request(data):
    if len(data) < 19:
        return None
    tid = data[1]
    cmd = data[9]
    index = data[12:14]
    subindex = data[14]
    length = data[18]
    if cmd == 0:  # SDO READ
        return ("read", tid, index, subindex, None, length)
    if cmd == 1:  # SDO WRITE
        if length == 4:
            value = struct.unpack("<I", bytes(data[19:23]))[0]
        elif length == 2:
            value = struct.unpack("<H", bytes(data[19:21]))[0]
        elif length == 1:
            value = data[19]
        else:
            value = 0
        return ("write", tid, index, subindex, value, length)
    return None

def make_sdo_response(tid, index, subindex, value_bytes, read=True):
    length = len(value_bytes)
    mbap = [0, tid, 0, 0, 0, 13+length, 0, 43, 13, 0, 0, 0, index[0], index[1], 0, 0, 0, 0, length]
    mbap.extend(value_bytes)
    return mbap

fakeDrive = FakeDriveState()


class EmulatorHTTPRequestHandler(SimpleHTTPRequestHandler):
    """Serve static files and stream drive state via SSE."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.dirname(__file__), **kwargs)

    def log_message(self, format, *args):
        # reduce noise
        pass

    def do_GET(self):
        if self.path == '/clients':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(json.dumps(CLIENTS.all()).encode('utf-8'))
            return
        if self.path == '/events':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            try:
                while True:

                    result = {
                        'position': fakeDrive.position,
                        'target_position': fakeDrive.target_position,
                        'velocity': fakeDrive.velocity,
                        'acceleration': fakeDrive.acceleration,
                        'homed': fakeDrive.homed,
                        'mode': fakeDrive.mode,
                        'is_moving': fakeDrive.is_moving,
                        'emergency_active': fakeDrive.emergency_active,
                        'rswon': fakeDrive.rswon,
                        'swon': fakeDrive.swon,
                        'eo': fakeDrive.eo,
                        'fault': fakeDrive.fault,
                        've': fakeDrive.ve,
                        'qs': fakeDrive.qs,
                        'swod': fakeDrive.swod,
                        'warn': fakeDrive.warn,
                        'na': fakeDrive.na,
                        're': fakeDrive.re,
                        'tr': fakeDrive.tr,
                        'ila': fakeDrive.ila,
                        'oms': fakeDrive.oms
                    }
                    data = json.dumps(result)

                    self.wfile.write(f'data: {data}\n\n'.encode('utf-8'))
                    self.wfile.flush()
                    time.sleep(0.05)
            except Exception:
                pass
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == '/emergency':
            # length = int(self.headers.get('Content-Length', 0))
            # body = self.rfile.read(length).decode() if length > 0 else ''
            # try:
            #     payload = json.loads(body) if body else {}
            #     state = payload.get("active", True)
            # except Exception:
            #     state = True  # по умолчанию включаем
            fakeDrive.emergency_stop(not fakeDrive.emergency_active)
            self.send_response(200)
            self.end_headers()


def start_http_server():
    handler = EmulatorHTTPRequestHandler
    server = ThreadingHTTPServer(('0.0.0.0', HTTP_PORT), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f'HTTP server started at http://0.0.0.0:{HTTP_PORT}')

import threading

client_counter = 0  # глобальный счётчик для присвоения уникальных id
modbus_client_lock = threading.Lock()
current_modbus_client = None  # хранит адрес текущего клиента (host, port)

def http_handle_client(conn, state: FakeDriveState):
    global current_modbus_client
    client_addr = conn.getpeername()
    client_id = f"modbus:{client_addr[0]}:{client_addr[1]}"

    # === Только один клиент ===
    acquired = modbus_client_lock.acquire(blocking=False)
    if not acquired:
        # Уже есть соединение — отправляем ошибку и закрываем
        try:
            # Можно отправить кастомное сообщение об ошибке (по TCP — текст, либо Modbus exception, если хочется заморочиться)
            msg = b"Modbus server busy: only one client allowed\n"
            conn.send(msg)
        except Exception:
            pass
        conn.close()
        print(f"[Modbus] Refused second connection from {client_addr} — already in use.")
        return
    current_modbus_client = client_addr
    CLIENTS.update(client_id, type='modbus', address=f"{client_addr[0]}:{client_addr[1]}", status='online')

    try:
        while True:
            try:
                data = conn.recv(24)
            except ConnectionResetError:
                print(f"[Modbus] Client forcibly closed connection ({client_addr})")
                break

            if not data:
                break
            CLIENTS.update(client_id, status='online')
            req = parse_modbus_request(list(data))
            if not req:
                continue
            op, tid, index, subindex, value, _ = req
            if op == "read":
                val_bytes = fakeDrive.sdo_read(index, subindex)
                resp = make_sdo_response(tid, index, subindex, list(val_bytes))
            elif op == "write":
                fakeDrive.sdo_write(index, subindex, value)
                sw = fakeDrive.make_statusword()
                lsb = sw & 0xFF
                msb = (sw >> 8) & 0xFF
                pair = [lsb, msb]
                resp = make_sdo_response(tid, index, subindex, pair)
            else:
                resp = [0]*24
            resp[1] = tid
            conn.send(bytes(resp))
    finally:
        conn.close()
        CLIENTS.remove(client_id)
        # Освобождаем lock — можно принимать следующего клиента!
        modbus_client_lock.release()
        current_modbus_client = None
        print(f"[Modbus] Disconnected client {client_addr}, slot freed.")


# import random
# import threading
# import time
# import random
# import sys
# from contextlib import suppress

# def http_handle_client(conn, state: FakeDriveState):
#     try:
#         while True:
#             data = conn.recv(24)
#             if not data:
#                 break
#             req = parse_modbus_request(list(data))
#             if not req:
#                 continue

#             # ВСТАВЛЯЕМ АНОМАЛИИ
#             chaos = random.random()
#             if chaos < 0.05:
#                 print("[SERVER CHAOS] Не отвечаем (timeout)...")
#                 time.sleep(5)
#                 continue
#             if chaos < 0.10:
#                 print("[SERVER CHAOS] Закрываем соединение (connection drop)...")
#                 conn.close()
#                 return
#             if chaos < 0.15:
#                 print("[SERVER CHAOS] Отвечаем битым статусвордом...")
#                 resp = [random.randint(0,255) for _ in range(24)]
#                 conn.send(bytes(resp))
#                 continue
#             if chaos < 0.20:
#                 print("[SERVER CHAOS] Короткий ответ (обрыв пакета)...")
#                 resp = [0] * random.randint(5, 12)
#                 conn.send(bytes(resp))
#                 continue
#             if chaos < 0.25:
#                 print("[SERVER CHAOS] Задержка 2с перед ответом")
#                 time.sleep(2)

#             op, tid, index, subindex, value, _ = req
#             if op == "read":
#                 val_bytes = fakeDrive.sdo_read(index, subindex)
#                 resp = make_sdo_response(tid, index, subindex, list(val_bytes))
#             elif op == "write":
#                 fakeDrive.sdo_write(index, subindex, value)
#                 sw = fakeDrive.make_statusword()
#                 lsb = sw & 0xFF
#                 msb = (sw >> 8) & 0xFF
#                 pair = [lsb, msb]
#                 resp = make_sdo_response(tid, index, subindex, pair)
#             else:
#                 resp = [0]*24
#             resp[1] = tid
#             conn.send(bytes(resp))
#     except Exception as e:
#         print(f"Client error: {e}")
#     finally:
#         with suppress(Exception):  # не упадёт если уже закрыто
#             conn.close()


import asyncio
import websockets
import socket
import threading

async def ws_handler(websocket):
    print("Client connected")
    try:
        while True:
            try:
                # Ждём сообщение максимум 1 сек — если не пришло, просто идём дальше (делаем heartbeat)
                msg = await asyncio.wait_for(websocket.recv(), timeout=1)
                # Пришло сообщение — можешь его обработать, если нужно
            except asyncio.TimeoutError:
                # За 1 секунду ничего не пришло — отправим heartbeat
                await websocket.send(b'\x00')
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")


def start_modbus_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", MODBUS_PORT))
    s.listen(5)
    print(f"Emulator started at 0.0.0.0:{MODBUS_PORT}")
    while True:
        conn, addr = s.accept()
        threading.Thread(target=http_handle_client, args=(conn, fakeDrive), daemon=True).start()

async def main():
    # Стартуем WebSocket серверы (запускаются и живут всё время!)
    servers = await asyncio.gather(
        websockets.serve(ws_handler, "0.0.0.0", 10000),
        websockets.serve(ws_handler, "0.0.0.0", 9999),
        websockets.serve(ws_handler, "0.0.0.0", 9998),
        websockets.serve(ws_handler, "0.0.0.0", 9997),
    )
    print("All WebSocket servers started")

    # Запускаем HTTP и Modbus серверы в отдельных потоках
    threading.Thread(target=start_http_server, daemon=True).start()
    threading.Thread(target=start_modbus_server, daemon=True).start()

    # Держим event loop активным
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())