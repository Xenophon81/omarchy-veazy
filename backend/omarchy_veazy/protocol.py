# SPDX-License-Identifier: AGPL-3.0-only
# Protocol port from Reactive Volcano App by Tristan Teufel.
# https://github.com/firsttris/reactive-volcano-app
# Upstream: 9d773eff709d721e0e79b403ac2258ba5a851d6c
# Sources: src/devices/ventyVeazy/protocol.ts and src/utils/uuids.ts.
# Changes: Python port, strict validation instead of clamping/rounding,
# nullable unsupported/invalid fields, temperature sentinel handling.
"""Pure Veazy codec. No Bluetooth, process, persistence, or UI dependencies."""

from enum import IntEnum

SERVICE_UUID = "00000000-5354-4f52-5a26-4249434b454c"
CONTROL_UUID = "00000001-5354-4f52-5a26-4249434b454c"


class Command(IntEnum):
    STATUS = 0x01
    FIRMWARE = 0x02
    ANALYSIS = 0x03
    EXTENDED_DATA = 0x04
    DEVICE_DATA = 0x05
    BRIGHTNESS_VIBRATION = 0x06
    FIND_MY_DEVICE = 0x0D
    ADVERTISING_INFO = 0x1D


MIN_LENGTHS = {Command.STATUS: 15, Command.FIRMWARE: 19, Command.ANALYSIS: 3,
               Command.EXTENDED_DATA: 20, Command.DEVICE_DATA: 18,
               Command.BRIGHTNESS_VIBRATION: 7, Command.ADVERTISING_INFO: 2}
STATUS_SETTINGS = {"charge_current_optimization": 0x08,
                   "charge_voltage_limit": 0x20, "boost_visualization": 0x40}
SHORT_SETTINGS = {"brightness": (0x01, 2), "vibration": (0x08, 5),
                  "boost_timeout_disabled": (0x10, 6)}
SETTINGS = frozenset((*STATUS_SETTINGS, *SHORT_SETTINGS, "permanent_bluetooth"))


def integer(value, low, high, label="value"):
    # bool is an int subclass; accepting it as temperature is an IPC mistake.
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be an integer in {low}..{high}")
    return value


def boolean(value):
    if type(value) is not bool:
        raise ValueError("value must be a boolean")
    return value


def _frame(command, fields=None, size=20):
    data = bytearray(size)
    data[0] = command
    for position, value in (fields or {}).items():
        data[position] = value
    return bytes(data)


def read_request(command):
    if command not in MIN_LENGTHS:
        raise ValueError("Unsupported read command")
    return _frame(command, size=7 if command == Command.BRIGHTNESS_VIBRATION else 20)


def set_target(value):
    raw = integer(value, 40, 210, "target") * 10
    return _frame(Command.STATUS, {1: 0x02, 4: raw & 0xFF, 5: raw >> 8})


def set_heater_mode(mode):
    return _frame(Command.STATUS, {1: 0x20, 11: integer(mode, 0, 3, "mode")})


def set_offset(kind, value):
    integer(value, 1, 99, "offset")
    if kind not in ("boost", "superboost"):
        raise ValueError("kind must be boost or superboost")
    return _frame(Command.STATUS, {1: 0x04 if kind == "boost" else 0x08,
                                   6 if kind == "boost" else 7: value})


def set_setting(name, value):
    if name not in SETTINGS:
        raise ValueError("Unsupported setting")
    if name == "brightness":
        integer(value, 1, 9, "brightness")
    else:
        boolean(value)
    if name in SHORT_SETTINGS:
        mask, position = SHORT_SETTINGS[name]
        return _frame(Command.BRIGHTNESS_VIBRATION,
                      {1: mask, position: int(value)}, size=7)
    if name == "permanent_bluetooth":
        return _frame(Command.STATUS, {1: 0x80, 16: int(value), 17: 1})
    bit = STATUS_SETTINGS[name]
    # The boost-visualization flag is inverted on Veazy specifically.
    enabled = not value if name == "boost_visualization" else value
    return _frame(Command.STATUS, {1: 0x80, 14: bit if enabled else 0, 15: bit})


def find_device():
    return _frame(Command.FIND_MY_DEVICE, {1: 1})


def _bounded(raw, low, high):
    return raw if low <= raw <= high else None


def _text(raw):
    # Device-supplied text is plain text, control characters removed.
    return "".join(c for c in raw.decode("utf-8", errors="replace").rstrip("\0")
                   if c.isprintable())[:64]


def decode(frame):
    """Return (opcode, flat snapshot fields), or None for corrupt/unknown data.

    Maximum response size is bounded independently of IPC. Individual invalid
    status values become unknown so an unsafe target/mode cannot pass guards.
    No response claims a transaction id: the wire has none.
    """
    if not isinstance(frame, (bytes, bytearray)) or not 1 <= len(frame) <= 512:
        return None
    command = frame[0]
    if command not in MIN_LENGTHS or len(frame) < MIN_LENGTHS[command]:
        return None
    if command == Command.STATUS:
        current = int.from_bytes(frame[2:4], "little")
        target = int.from_bytes(frame[4:6], "little")
        flags = frame[14]
        data = {
            "current_temperature_raw": current,
            "current_temperature_c": None if current == 0x8000 else
                (current / 10 if current <= 3000 else None),
            "target_temperature_c": target / 10 if 400 <= target <= 2100 else None,
            "boost_offset_c": _bounded(frame[6], 1, 99),
            "superboost_offset_c": _bounded(frame[7], 1, 99),
            "battery_percent": _bounded(frame[8], 0, 100),
            "auto_shutdown_timer": frame[9] + frame[10],
            "heater_mode": _bounded(frame[11], 0, 3),
            "charging": frame[13] > 0,
            "setpoint_reached": bool(flags & 0x02),
            "charge_current_optimization": bool(flags & 0x08),
            "charge_voltage_limit": bool(flags & 0x20),
            "boost_visualization": not bool(flags & 0x40),
            "permanent_bluetooth": bool(frame[16] & 1) if len(frame) >= 17 else None,
        }
    elif command == Command.FIRMWARE:
        flags = frame[1]
        data = {"firmware_flags": flags,
                "application_valid": bool(flags & 1) and not bool(flags & 0x30),
                "firmware_version": _text(frame[2:8]),
                "bootloader_version": _text(frame[11:17])}
    elif command == Command.EXTENDED_DATA:
        data = {"heater_runtime_minutes": int.from_bytes(frame[1:4], "little"),
                "charging_time_minutes": int.from_bytes(frame[4:7], "little")}
    elif command == Command.DEVICE_DATA:
        data = {"serial_number": _text(frame[15:17] + frame[9:15]),
                "color_index": frame[18] if len(frame) > 18 else None}
    elif command == Command.BRIGHTNESS_VIBRATION:
        data = {"brightness": _bounded(frame[2], 1, 9),
                "vibration": frame[5] != 0, "boost_timeout_disabled": frame[6] != 0}
    elif command == Command.ANALYSIS:
        data = {"analysis_code": frame[1], "analysis_category": frame[2]}
    else:
        data = {"find_device_active": bool(frame[1] & 0x10)}
    return command, data


def effective_target(snapshot, **changes):
    """Veazy upstream semantics: superboost uses its own offset, not both."""
    data = snapshot | changes
    mode = data.get("heater_mode")
    base = data.get("target_temperature_c")
    if mode not in (0, 1, 2, 3) or type(base) not in (int, float):
        return None
    offset = data.get("boost_offset_c" if mode == 2 else "superboost_offset_c")
    if mode in (2, 3):
        if type(offset) not in (int, float):
            return None
        base += offset
    return base
