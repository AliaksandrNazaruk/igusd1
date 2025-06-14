import socket
import struct
import threading
import time
MODBUS_PORT = 502

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
        if self.is_moving or self.position == self.target_position:
            return  # Уже двигается или уже там
        self.is_moving = True
        self.tr = 0  # target_reached сбрасываем на время движения
        threading.Thread(target=self._move_simulation, daemon=True).start()

    def _move_simulation(self):
        start_pos = self.position
        end_pos = self.target_position
        duration = 10.0
        steps = 100
        step_time = duration / steps
        for i in range(steps):
            # Линейное движение, имитация
            self.position = int(start_pos + (end_pos - start_pos) * (i + 1) / steps)
            self.velocity = int((end_pos - start_pos) / duration)
            time.sleep(step_time)
        self.position = end_pos
        self.velocity = 0
        self.tr = 1  # target_reached
        self.is_moving = False

    def do_home(self):
        if self.is_moving:
            return
        self.is_moving = True
        self.tr = 0
        threading.Thread(target=self._home_simulation, daemon=True).start()

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
                self.swon = self.eo = self.ve = self.tr = 0
                self.fault = 0
            elif value == 0x07:  # Switch On
                self.rswon = 1
                self.swon = 1
                self.eo = self.ve = self.tr = 0
                self.fault = 0
            elif value == 0x0F:  # Enable operation
                self.rswon = 1
                self.swon = 1
                self.eo = 1
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

def handle_client(conn, state: FakeDriveState):
    try:
        while True:
            data = conn.recv(24)
            if not data:
                break
            req = parse_modbus_request(list(data))
            if not req:
                continue
            op, tid, index, subindex, value, _ = req
            if op == "read":
                val_bytes = fakeDrive.sdo_read(index, subindex)
                resp = make_sdo_response(tid, index, subindex, list(val_bytes))
            elif op == "write":
                fakeDrive.sdo_write(index, subindex, value)
                # echo-back current state (например statusword)
                sw = fakeDrive.make_statusword()
                lsb = sw & 0xFF         # младший байт (Least Significant Byte)
                msb = (sw >> 8) & 0xFF  # старший байт (Most Significant Byte)
                pair = [lsb, msb]
                resp = make_sdo_response(tid, index, subindex, pair)
            else:
                resp = [0]*24
            resp[1] = tid
            conn.send(bytes(resp))
    except Exception as e:
        print(f"Client error: {e}")
    finally:
        conn.close()

def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", MODBUS_PORT))
    s.listen(5)
    print(f"Emulator started at 0.0.0.0:{MODBUS_PORT}")
    while True:
        conn, addr = s.accept()
        threading.Thread(target=handle_client, args=(conn, fakeDrive), daemon=True).start()

if __name__ == "__main__":
    main()
