import socket
import struct
import threading

MODBUS_PORT = 502

class FakeDriveState:
    def __init__(self):
        self.fault =False
        self.internal_limit =False
        self.op_mode_specific =False
        self.operation_enabled =False
        self.quick_stop =True
        self.ready_to_switch_on =True
        self.remote =True
        self.switch_on_disabled =False
        self.switched_on =False
        self.target_reached =True
        self.value = 33
        self.voltage_enabled =False
        self.warning = 0
        self.position = 0
        self.velocity = 0
        self.homed = 0
    def emulator(self,list):
        if list == [0, 0, 0, 0, 0, 13, 0, 43, 13, 0, 0, 0, 96, 65, 0, 0, 0, 0, 2]:
            return [0, 0, 0, 0, 0, 15, 0, 43, 13, 0, 0, 0, 96, 65, 0, 0, 0, 0, 2, self.value, 6]
        
        if list == [0, 0, 0, 0, 0, 15, 0, 43, 13, 1, 0, 0, 96, 64, 0, 0, 0, 0, 2, 6, 0]:
            self.value = 33
            return [0, 0, 0, 0, 0, 13, 0, 43, 13, 1, 0, 0, 96, 64, 0, 0, 0, 0, 0]
        
        if list == [0, 0, 0, 0, 0, 15, 0, 43, 13, 1, 0, 0, 96, 64, 0, 0, 0, 0, 2, 128, 0]:
            self.value = 39
            return [0, 0, 0, 0, 0, 15, 0, 43, 13, 1, 0, 0, 96, 64, 0, 0, 0, 0, 2, 39, 6]

        if list == [0, 0, 0, 0, 0, 15, 0, 43, 13, 1, 0, 0, 96, 64, 0, 0, 0, 0, 2, 7, 0]:
            self.value = 35
            return [0, 0, 0, 0, 0, 13, 0, 43, 13, 1, 0, 0, 96, 64, 0, 0, 0, 0, 0]
        
        if list == [0, 0, 0, 0, 0, 15, 0, 43, 13, 1, 0, 0, 96, 64, 0, 0, 0, 0, 2, 15, 0]:
            self.value = 39
            return [0, 0, 0, 0, 0, 13, 0, 43, 13, 1, 0, 0, 96, 64, 0, 0, 0, 0, 0]
        
        if list == [0, 0, 0, 0, 0, 13, 0, 43, 13, 0, 0, 0, 96, 100, 0, 0, 0, 0, 4]:
            return [0, 0, 0, 0, 0, 17, 0, 43, 13, 0, 0, 0, 96, 100, 0, 0, 0, 0, 4, self.position, 0, 0, 0]
        
        if list == [0, 0, 0, 0, 0, 13, 0, 43, 13, 0, 0, 0, 96, 108, 0, 0, 0, 0, 4]:
            return [0, 0, 0, 0, 0, 17, 0, 43, 13, 0, 0, 0, 96, 108, 0, 0, 0, 0, 4, self.velocity, 0, 0, 0]
        
        if list == [0, 0, 0, 0, 0, 13, 0, 43, 13, 0, 0, 0, 16, 1, 0, 0, 0, 0, 1]:
            return [0, 0, 0, 0, 0, 11, 0, 171, 255, 0, 6, 13, 206, 0, 0, 2, 6]
        
        if list == [0, 0, 0, 0, 0, 14, 0, 43, 13, 1, 0, 0, 96, 96, 0, 0, 0, 0, 1, 6]:
            return [0, 0, 0, 0, 0, 15, 0, 43, 13, 0, 0, 0, 96, 96, 0, 0, 0, 0, 2, self.value, 6]

        if list == [0, 0, 0, 0, 0, 14, 0, 43, 13, 1, 0, 0, 96, 96, 0, 0, 0, 0, 1, 1]:
            return [0, 0, 0, 0, 0, 15, 0, 43, 13, 0, 0, 0, 96, 96, 0, 0, 0, 0, 2, self.value, 6]
        
        if list == [0, 0, 0, 0, 0, 13, 0, 43, 13, 0, 0, 0, 32, 20, 0, 0, 0, 0, 2]:
            return [0, 0, 0, 0, 0, 17, 0, 43, 13, 0, 0, 0, 32, 20, 0, 0, 0, 0, 2, self.homed, 0, 0, 0]
        
fakeDrive = FakeDriveState()
timer = 0
def handle_client(conn, state: FakeDriveState):
    global timer
    try:
        while True:
            timer = timer+1
            if timer == 20:
                timer = 0
                fakeDrive.value = fakeDrive.value | 0x08  # Устанавливаем бит 3

            mbap = list(conn.recv(24))
            if not mbap:
                break
            tid = mbap[1]
            mbap[1]=0
            response = fakeDrive.emulator(mbap)
            response[1] = tid
            array = bytes(response)
            conn.send(array)
    except Exception as e:
        print(f"Client error: {e}")
    finally:
        conn.close()

def main():
    state = FakeDriveState()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", MODBUS_PORT))
    s.listen(5)
    print(f"Emulator started at 0.0.0.0:{MODBUS_PORT}")
    while True:
        conn, addr = s.accept()
        threading.Thread(target=handle_client, args=(conn, state), daemon=True).start()

if __name__ == "__main__":
    main()
