# SPDX-License-Identifier: AGPL-3.0-only
"""Synthetic Veazy frames and transport; never a hardware test."""

import asyncio


def status_frame(*, target=180, mode=0, boost=15, superboost=30,
                 current_raw=0x8000, battery=73, flags=0x2A, length=20):
    frame = bytearray(20)
    frame[0] = 1
    frame[2:4] = current_raw.to_bytes(2, "little")
    frame[4:6] = int(target * 10).to_bytes(2, "little")
    frame[6:9] = bytes([boost, superboost, battery])
    frame[11] = mode
    frame[13] = 1
    frame[14] = flags
    frame[16] = 1
    return bytes(frame[:length])


class FakeTransport:
    def __init__(self):
        self.writes = []
        self.connected = False
        self.notify = None
        self.disconnected_callback = None
        self.target = 180
        self.mode = 0
        self.boost = 15
        self.superboost = 30
        self.brightness = 9
        self.vibration = True
        self.boost_timeout_disabled = False
        self.flags = 0x2A
        self.permanent_bluetooth = True
        self.firmware_flags = 1
        self.ignore_mutations = False
        self.drop_status = False
        self.delay = 0
        self.active = 0
        self.max_active = 0
        self.scan_count = 0
        self.connect_count = 0
        self.fail_mutation = False

    async def scan(self):
        self.scan_count += 1
        return [{"id": "fake-veazy", "name": "S&B VZ test"}]

    async def connect(self, device_id, notify, disconnected):
        self.connect_count += 1
        self.connected = True
        self.notify = notify
        self.disconnected_callback = disconnected

    async def disconnect(self):
        self.connected = False

    async def write(self, frame):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.writes.append(frame)
        try:
            await asyncio.sleep(self.delay)
            if not self.connected:
                raise RuntimeError("Not connected")
            command, mask = frame[:2]
            mutation = mask != 0
            if mutation:
                if self.fail_mutation:
                    raise TimeoutError("Ambiguous GATT write timeout")
                if self.ignore_mutations:
                    return
                if command == 1:
                    if mask & 0x02:
                        self.target = int.from_bytes(frame[4:6], "little") / 10
                    if mask & 0x04:
                        self.boost = frame[6]
                    if mask & 0x08:
                        self.superboost = frame[7]
                    if mask & 0x20:
                        self.mode = frame[11]
                    if mask & 0x80:
                        self.flags = (self.flags & ~frame[15]) | (frame[14] & frame[15])
                        if frame[17] & 1:
                            self.permanent_bluetooth = bool(frame[16] & 1)
                if command == 6:
                    if mask & 1:
                        self.brightness = frame[2]
                    if mask & 8:
                        self.vibration = bool(frame[5])
                    if mask & 16:
                        self.boost_timeout_disabled = bool(frame[6])
                return
            if command == 1:
                if self.drop_status:
                    return
                data = bytearray(status_frame(target=self.target, mode=self.mode,
                    boost=self.boost, superboost=self.superboost, flags=self.flags))
                data[16] = int(self.permanent_bluetooth)
            elif command == 2:
                data = bytearray(20)
                data[0:2] = bytes([2, self.firmware_flags])
                data[2:8] = b"V01.23"
                data[11:17] = b"V00.05"
            elif command == 6:
                data = bytes([6, 0, self.brightness, 0, 0,
                              int(self.vibration), int(self.boost_timeout_disabled)])
            elif command == 3:
                data = bytes([3, 0x12, 4])
            else:
                data = bytearray(20)
                data[0] = command
            self.notify(bytes(data))
        finally:
            self.active -= 1

    @property
    def mutations(self):
        return [frame for frame in self.writes if frame[1] != 0]
