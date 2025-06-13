# igusd1

Python driver for the **Igus dryve D1** controller.  The library implements the
full stack for Modbus TCP communication and drive control according to the
CiA‑402 profile.

## Features

- Reliable `ModbusTcpTransport` with automatic reconnection and heartbeat
  support.
- `DryveSDO` implementation for reading/writing Object Dictionary entries.
- `DriveStateMachine` for dealing with status and commands.
- High‑level `DryveController` and thread‑safe `IgusMotor` facade.
- `IgusD1Emulator` for local testing without physical hardware.
- Unified exception hierarchy in `exceptions.py`.

## Project structure

```
Application code
    ↓
DryveController        — controller.py
    ↓
DriveStateMachine      — machine.py → state_bits.py
    ↓
DryveSDO               — protocol.py → od.py
    ↓
ModbusPacketBuilder    — packet.py → codec.py
    ↓
ModbusTcpTransport     — transport.py
```

For more details see `driver_structure.txt`.

## Requirements

- Python 3.10 or newer

The driver depends only on the Python standard library, no extra packages are required.

To install the library from a local checkout run:

```bash
pip install .
```

## Usage example

```python
from igusd1 import IgusMotor

motor = IgusMotor("192.168.1.230")

# Homing
motor.home()

# Move back and forth
while True:
    motor.move_to_position(5000)
    print(motor.get_status())
    motor.move_to_position(15000)
    print(motor.get_status())
```

During development you can run the emulator:

```bash
python -m igusd1.emulator
```

It starts a small Modbus TCP server on port 502 so the code can be debugged without an actual dryve D1.

## License

The code is released under the MIT license (see file headers for details).

