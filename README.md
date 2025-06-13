# igusd1

Python-драйвер для контроллера **Igus dryve D1**. Библиотека реализует полный стек для обмена по Modbus TCP и управления приводом по профилю CiA‑402.

## Возможности

- Надёжный транспорт `ModbusTcpTransport` с автоматическим переподключением и heartbeat.
- Реализация SDO-протокола (`DryveSDO`) для чтения/записи объекта словаря устройства.
- Машина состояний привода (`DriveStateMachine`) для работы со статусом и командами.
- Высокоуровневый контроллер (`DryveController`) и потокобезопасный фасад `IgusMotor`.
- Эмулятор `IgusD1Emulator` для локального тестирования без реального оборудования.
- Единая иерархия исключений в `exceptions.py`.

## Структура проекта

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

Дополнительную информацию см. в `driver_structure.txt`.

## Требования

- Python 3.10 или новее

Установка зависимостей не требуется, библиотека использует только стандартную библиотеку Python.

## Пример использования

```python
from igus_motor import IgusMotor

motor = IgusMotor("192.168.1.230")

# Гоминг
motor.home()

# Перемещение между точками
while True:
    motor.move_to_position(5000)
    print(motor.get_status())
    motor.move_to_position(15000)
    print(motor.get_status())
```

Для разработки можно запустить эмулятор:

```bash
python emulator.py
```

Он поднимает небольшой сервер Modbus TCP на порту 502 и позволяет отлаживать код без реального dryve D1.

## Лицензия

Код распространяется под лицензией MIT (см. заголовки файлов).

