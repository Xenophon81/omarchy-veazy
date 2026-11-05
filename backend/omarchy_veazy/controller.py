# SPDX-License-Identifier: AGPL-3.0-only
"""Session-bound connection manager, serialized I/O, and mutation confirmation.

Read initialization order/poll interval derive from Reactive Volcano App by
Tristan Teufel, src/devices/ventyVeazy/driver.ts, upstream commit
9d773eff709d721e0e79b403ac2258ba5a851d6c. Queue/generation/confirmation guards
are new native implementation; no transaction ids are invented on the wire.
"""

import asyncio
from contextlib import suppress
import time

from . import protocol as p
from .errors import VeazyError, safe_message

SNAPSHOT_FIELDS = (
    "target_temperature_c", "current_temperature_c", "boost_offset_c",
    "superboost_offset_c", "heater_mode", "battery_percent", "charging",
    "setpoint_reached", "firmware_version", "serial_number", "brightness",
    "vibration", "charge_current_optimization", "charge_voltage_limit",
    "boost_visualization", "boost_timeout_disabled", "permanent_bluetooth",
    "heater_runtime_minutes", "charging_time_minutes", "analysis_code",
    "analysis_category", "application_valid",
)


class Controller:
    def __init__(self, transport, emit, *, request_timeout=4.0, poll_interval=0.5):
        self.transport = transport
        self.emit = emit
        self.request_timeout = request_timeout
        self.poll_interval = poll_interval
        self.state = "disconnected"
        self.generation = 0
        self.data = {key: None for key in SNAPSHOT_FIELDS}
        self.selected_device_id = None
        self.devices = []
        self.status_time = None
        self.confirmation = "unknown"
        self.pending_command = None
        self.session_uncertain = False
        self._command_lock = asyncio.Lock()
        self._lifecycle_lock = asyncio.Lock()
        self._io_lock = asyncio.Lock()
        self._tasks = set()
        self._waiters = {}
        self._poll_task = None

    def _state(self, state):
        self.state = state
        self.emit("state", {"state": state, "busy": self.pending_command is not None
                           or state in ("scanning", "connecting", "initializing", "disconnecting")})

    def snapshot(self):
        age = (time.monotonic() - self.status_time) if self.status_time is not None else None
        stale = age is None or age > 2 or self.state != "ready" or self.session_uncertain
        return self.data | {
            "stale": stale,
            "status_age_ms": round(age * 1000) if age is not None else None,
            "confirmation": self.confirmation,
            "pending_command": self.pending_command,
            "session_uncertain": self.session_uncertain,
            "effective_target_temperature_c": p.effective_target(self.data),
            "capabilities": {"settings": [key for key in p.SETTINGS if self.data.get(key) is not None],
                             "heating": self.data.get("application_valid") is True},
        }

    def _snapshot(self):
        self.emit("snapshot", self.snapshot())

    def _invalidate(self):
        self.data = {key: None for key in SNAPSHOT_FIELDS}
        self.status_time = None
        self.confirmation = "unknown"
        self.pending_command = None
        self._snapshot()

    def _check_generation(self, generation):
        if generation != self.generation:
            raise VeazyError("session_changed", "Command belongs to an expired Bluetooth session")

    def _require_ready(self, *, allow_uncertain=False):
        if self.state != "ready" or self.data.get("application_valid") is not True:
            raise VeazyError("not_ready", "Veazy is not connected in a valid application mode")
        if self.session_uncertain and not allow_uncertain:
            raise VeazyError("uncertain_session", "Response stream is uncertain; disconnect and reconnect before changing settings or heating")

    def _mark_uncertain(self):
        # Responses have only an opcode, no wire transaction id. Once a read
        # times out or a GATT operation has an ambiguous outcome, a late reply
        # could satisfy any later same-opcode request. No subsequent read or
        # unsolicited notification may restore mutation authority this session.
        was_uncertain = self.session_uncertain
        self.session_uncertain = True
        self.confirmation = "unknown"
        self._snapshot()
        if not was_uncertain:
            self.emit("error", {"code": "uncertain_session", "message": "Response stream is uncertain; disconnect and reconnect. Heater off remains best effort."})

    def _notification(self, frame, generation):
        if generation != self.generation:
            return
        decoded = p.decode(frame)
        if decoded is None:
            return
        command, data = decoded
        self.data.update(data)
        if command == p.Command.STATUS:
            self.status_time = time.monotonic()
        waiter = self._waiters.get(command)
        if waiter is not None and not waiter.done():
            waiter.set_result(data.copy())
        if command == p.Command.FIRMWARE and data["application_valid"] is not True and self.state == "ready":
            self._state("error")
            self.emit("error", {"code": "invalid_application", "message": "Device firmware is not in valid application mode"})
        self._snapshot()

    def _link_lost(self, generation):
        if generation != self.generation:
            return
        # Invalidate immediately, before another pending command can write.
        self.generation += 1
        for task in tuple(self._tasks):
            task.cancel()
        if self._poll_task:
            self._poll_task.cancel()
        self._state("disconnected")
        self._invalidate()
        self.emit("error", {"code": "connection_lost", "message": "Bluetooth connection lost; heater state is unknown"})

    async def _write(self, frame, generation):
        self._check_generation(generation)
        try:
            async with asyncio.timeout(self.request_timeout):
                await self.transport.write(frame)
        except Exception:
            if generation == self.generation:
                self._mark_uncertain()
            raise
        self._check_generation(generation)

    async def _request_locked(self, command, generation):
        self._check_generation(generation)
        future = asyncio.get_running_loop().create_future()
        self._waiters[command] = future
        try:
            await self._write(p.read_request(command), generation)
            async with asyncio.timeout(self.request_timeout):
                result = await future
            self._check_generation(generation)
            return result
        except TimeoutError as error:
            self._mark_uncertain()
            raise VeazyError("read_timeout", f"No response for command 0x{command:02x}; disconnect and reconnect before further changes") from error
        except Exception:
            self._mark_uncertain()
            raise
        finally:
            if self._waiters.get(command) is future:
                self._waiters.pop(command, None)
            if not future.done():
                future.cancel()

    async def _request(self, command, generation):
        async with self._io_lock:
            return await self._request_locked(command, generation)

    async def _scan(self):
        if self.state not in ("disconnected", "error"):
            raise VeazyError("busy", "Disconnect before scanning")
        self._state("scanning")
        try:
            self.devices = await self.transport.scan()
        except Exception:
            self._state("disconnected")
            raise
        self._state("disconnected")
        self.emit("devices", {"devices": self.devices, "selected_device_id": self.selected_device_id})
        return {"devices": self.devices}

    async def _connect(self, device_id):
        if self.state not in ("disconnected", "error"):
            raise VeazyError("busy", "Disconnect before connecting")
        if not any(device["id"] == device_id for device in self.devices):
            raise VeazyError("unknown_device", "Select a device from the latest scan first")
        self.generation += 1
        generation = self.generation
        self.session_uncertain = False
        self._invalidate()
        self.selected_device_id = device_id
        self._state("connecting")
        try:
            await self.transport.connect(device_id,
                lambda frame: self._notification(frame, generation),
                lambda: self._link_lost(generation))
            self._check_generation(generation)
            self._state("initializing")
            await self._request(p.Command.FIRMWARE, generation)
            if self.data.get("application_valid") is not True:
                raise VeazyError("invalid_application", "Veazy firmware application is invalid or in bootloader mode")
            # Only documented read requests; no settings or heater writes.
            for command in (p.Command.ADVERTISING_INFO, p.Command.STATUS,
                            p.Command.EXTENDED_DATA, p.Command.DEVICE_DATA,
                            p.Command.BRIGHTNESS_VIBRATION):
                try:
                    await self._request(command, generation)
                except VeazyError as error:
                    if command == p.Command.STATUS:
                        raise
                    self.emit("error", {"code": error.code, "message": safe_message(error)})
            self._check_generation(generation)
            self._state("ready")
            self.confirmation = "unknown" if self.session_uncertain else "confirmed"
            self._snapshot()
            self._poll_task = asyncio.create_task(self._poll(generation))
            return {"connected": True, "device_id": device_id}
        except BaseException:
            if self.generation == generation:
                self.generation += 1
                self._state("error")
                self._invalidate()
            await self.transport.disconnect()
            raise

    async def _disconnect(self):
        async with self._lifecycle_lock:
            return await self._disconnect_locked()

    async def _disconnect_locked(self):
        self.generation += 1
        current = asyncio.current_task()
        pending = [task for task in tuple(self._tasks) if task is not current]
        if self._poll_task is not None and self._poll_task is not current:
            pending.append(self._poll_task)
        for task in pending:
            task.cancel()
        for future in self._waiters.values():
            if not future.done():
                future.cancel()
        self._waiters.clear()
        self._state("disconnecting")
        self._invalidate()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        await self.transport.disconnect()
        self._poll_task = None
        self._state("disconnected")
        return {"disconnected": True}

    async def _poll(self, generation):
        count = 0
        try:
            while generation == self.generation and self.state == "ready":
                await asyncio.sleep(self.poll_interval)
                if self._command_lock.locked() or self._io_lock.locked():
                    continue
                count += 1
                command = p.Command.EXTENDED_DATA if count % 30 == 0 else p.Command.STATUS
                try:
                    await self._request(command, generation)
                except VeazyError as error:
                    self.emit("error", {"code": error.code, "message": safe_message(error)})
                    self._snapshot()
                except Exception as error:
                    self.emit("error", {"code": "bluetooth_error", "message": safe_message(error)})
                    self._snapshot()
        except asyncio.CancelledError:
            pass

    async def _fresh_status(self, generation, *, allow_off=False):
        self._require_ready(allow_uncertain=allow_off)
        if self.session_uncertain and allow_off:
            return
        try:
            await self._request(p.Command.STATUS, generation)
        except VeazyError:
            if not allow_off:
                raise VeazyError("unknown_status", "Fresh device status could not be established; disconnect and reconnect before further changes")
        self._check_generation(generation)
        self._require_ready(allow_uncertain=allow_off)
        if not allow_off and self.data.get("heater_mode") not in (0, 1, 2, 3):
            raise VeazyError("unknown_status", "A confirmed current heater mode is required")

    def _guard_effective(self, **changes):
        # A new target/offset still needs a known current mode, even if heater
        # is off; this prevents stale-mode increases while boost is active.
        effective = p.effective_target(self.data, **changes)
        if effective is None:
            raise VeazyError("unknown_status", "Confirmed target, offsets and heater mode are required")
        if effective > 210:
            raise VeazyError("effective_limit", "Effective target above 210 C is blocked until hardware validation")

    async def _mutate(self, name, frame, expected, read_command, generation):
        self.pending_command = name
        self.confirmation = "pending"
        self._state(self.state)
        self._snapshot()
        try:
            async with self._io_lock:
                heater_off = expected.get("heater_mode") == 0
                self._require_ready(allow_uncertain=heater_off)
                if any(key in expected for key in ("target_temperature_c", "boost_offset_c",
                                                    "superboost_offset_c", "heater_mode")):
                    if expected.get("heater_mode") != 0:
                        if self.data.get("heater_mode") not in (0, 1, 2, 3):
                            raise VeazyError("unknown_status", "Current heater mode became unknown before write")
                        self._guard_effective(**expected)
                try:
                    # Never retry a mutation, including ambiguous write errors.
                    await self._write(frame, generation)
                except Exception:
                    self._mark_uncertain()
                    # Reconcile status without replaying the command. Even a
                    # matching snapshot cannot turn an ambiguous write into ACK.
                    with suppress(Exception):
                        await self._request_locked(read_command, generation)
                    raise VeazyError("write_uncertain", "Write outcome is unknown; disconnect and reconnect before changing settings or heating")
                if self.session_uncertain:
                    # Absolute off is the only mutation allowed in an uncertain
                    # session. A late reply cannot confirm its physical result.
                    self.confirmation = "unknown"
                    return {"confirmation": "unknown", "reason": "reconnect_required",
                            "message": "Heater-off command was sent once but its result is unconfirmed; disconnect and reconnect to read status."}
                deadline = time.monotonic() + self.request_timeout
                while True:
                    self._require_ready()
                    observed = await self._request_locked(read_command, generation)
                    self._require_ready()
                    if all(observed.get(key) == value for key, value in expected.items()):
                        self.confirmation = "confirmed"
                        return {"confirmation": "confirmed", "observed": expected}
                    if time.monotonic() >= deadline:
                        self._mark_uncertain()
                        raise VeazyError("confirmation_timeout", "Device has not confirmed the requested value; command was not retried. Disconnect and reconnect before further changes.")
                    await asyncio.sleep(0.1)
        except BaseException:
            self.confirmation = "unknown"
            raise
        finally:
            self.pending_command = None
            self._state(self.state)
            self._snapshot()

    async def _dispatch(self, command, args, generation):
        if command == "scan":
            return await self._scan()
        if command == "connect":
            return await self._connect(args["device_id"])
        if command == "status":
            self._snapshot()
            self._state(self.state)
            return self.snapshot()
        self._require_ready(allow_uncertain=command == "set_heater_mode" and args.get("mode") == 0)
        if command == "diagnose":
            return await self._request(p.Command.ANALYSIS, generation)
        if command == "find_device":
            async with self._io_lock:
                await self._write(p.find_device(), generation)
            return {"confirmation": "unknown"}
        if command == "set_target":
            frame = p.set_target(args["value"])
            await self._fresh_status(generation)
            self._guard_effective(target_temperature_c=args["value"])
            return await self._mutate(command, frame, {"target_temperature_c": args["value"]}, p.Command.STATUS, generation)
        if command == "set_heater_mode":
            frame = p.set_heater_mode(args["mode"])
            await self._fresh_status(generation, allow_off=args["mode"] == 0)
            if args["mode"] != 0:
                self._guard_effective(heater_mode=args["mode"])
            return await self._mutate(command, frame, {"heater_mode": args["mode"]}, p.Command.STATUS, generation)
        if command == "set_offset":
            frame = p.set_offset(args["kind"], args["value"])
            key = args["kind"] + "_offset_c"
            await self._fresh_status(generation)
            self._guard_effective(**{key: args["value"]})
            return await self._mutate(command, frame, {key: args["value"]}, p.Command.STATUS, generation)
        if command == "set_setting":
            name, value = args["name"], args["value"]
            frame = p.set_setting(name, value)
            if self.data.get(name) is None:
                raise VeazyError("unsupported_setting", "This setting has not been reported by this device")
            read = p.Command.BRIGHTNESS_VIBRATION if name in p.SHORT_SETTINGS else p.Command.STATUS
            return await self._mutate(command, frame, {name: value}, read, generation)
        raise VeazyError("unknown_command", "Unsupported command")

    async def execute(self, command, args):
        task = asyncio.current_task()
        self._tasks.add(task)
        generation = self.generation
        try:
            if command == "disconnect":
                return await self._disconnect()
            async with self._command_lock:
                self._check_generation(generation)
                return await self._dispatch(command, args, generation)
        finally:
            self._tasks.discard(task)

    async def close(self):
        await self._disconnect()
