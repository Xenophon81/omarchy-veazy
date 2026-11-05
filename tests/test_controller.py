# SPDX-License-Identifier: AGPL-3.0-only
import asyncio
import unittest

from omarchy_veazy.controller import Controller
from omarchy_veazy.errors import VeazyError
from tests.helpers import FakeTransport, status_frame


class ControllerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.transport = FakeTransport()
        self.events = []
        self.controller = Controller(self.transport, lambda event, data: self.events.append((event, data)),
                                     request_timeout=0.12, poll_interval=0.02)

    async def asyncTearDown(self):
        await self.controller.close()

    async def connect(self):
        await self.controller.execute("scan", {})
        await self.controller.execute("connect", {"device_id": "fake-veazy"})

    async def test_start_scan_connect_poll_are_read_only(self):
        self.assertEqual(self.transport.scan_count, 0)
        self.assertEqual(self.transport.connect_count, 0)
        self.assertEqual(self.transport.writes, [])
        await self.connect()
        self.assertEqual([frame[0] for frame in self.transport.writes], [2, 0x1D, 1, 4, 5, 6])
        await asyncio.sleep(0.07)
        self.assertGreater(len(self.transport.writes), 6)
        self.assertEqual(self.transport.mutations, [])
        self.assertEqual(self.controller.state, "ready")
        self.assertFalse(self.controller.snapshot()["stale"])
        self.assertIsNone(self.controller.snapshot()["current_temperature_c"])

    async def test_selected_device_and_valid_application_required(self):
        with self.assertRaises(VeazyError) as caught:
            await self.controller.execute("connect", {"device_id": "unknown"})
        self.assertEqual(caught.exception.code, "unknown_device")
        self.transport.firmware_flags = 0x11
        with self.assertRaises(VeazyError) as caught:
            await self.connect()
        self.assertEqual(caught.exception.code, "invalid_application")
        self.assertEqual(self.transport.mutations, [])
        self.assertFalse(self.transport.connected)

    async def test_explicit_mutations_and_confirmation(self):
        await self.connect()
        result = await self.controller.execute("set_target", {"value": 185})
        self.assertEqual(result["confirmation"], "confirmed")
        self.assertEqual(self.transport.mode, 0)
        await self.controller.execute("set_heater_mode", {"mode": 2})
        self.assertEqual(self.transport.mode, 2)
        self.assertEqual(self.controller.snapshot()["effective_target_temperature_c"], 200)
        await self.controller.execute("set_heater_mode", {"mode": 0})
        self.assertEqual(self.transport.mode, 0)
        self.assertEqual(len(self.transport.mutations), 3)
        self.assertTrue(any(event == "snapshot" and data["confirmation"] == "pending"
                            for event, data in self.events))

    async def test_effective_guard_all_heating_mutations(self):
        await self.connect()
        await self.controller.execute("set_heater_mode", {"mode": 2})
        count = len(self.transport.mutations)
        for command, args in (("set_target", {"value": 200}),
                              ("set_offset", {"kind": "boost", "value": 40})):
            with self.subTest(command=command), self.assertRaises(VeazyError) as caught:
                await self.controller.execute(command, args)
            self.assertEqual(caught.exception.code, "effective_limit")
        self.transport.target = 190
        with self.assertRaises(VeazyError) as caught:
            await self.controller.execute("set_heater_mode", {"mode": 3})
        self.assertEqual(caught.exception.code, "effective_limit")
        self.assertEqual(len(self.transport.mutations), count)

    async def test_unknown_status_blocks_increase_but_off_is_available(self):
        await self.connect()
        self.transport.mode = 255
        for command, args in (("set_target", {"value": 190}),
                              ("set_heater_mode", {"mode": 1}),
                              ("set_heater_mode", {"mode": 2}),
                              ("set_offset", {"kind": "boost", "value": 20})):
            with self.subTest(command=command), self.assertRaises(VeazyError) as caught:
                await self.controller.execute(command, args)
            self.assertEqual(caught.exception.code, "unknown_status")
        self.assertEqual(self.transport.mutations, [])
        result = await self.controller.execute("set_heater_mode", {"mode": 0})
        self.assertEqual(result["confirmation"], "confirmed")

    async def test_mutation_not_confirmed_by_gatt_success(self):
        await self.connect()
        self.transport.ignore_mutations = True
        with self.assertRaises(VeazyError) as caught:
            await self.controller.execute("set_target", {"value": 190})
        self.assertEqual(caught.exception.code, "confirmation_timeout")
        self.assertEqual(len(self.transport.mutations), 1)
        self.assertEqual(self.controller.confirmation, "unknown")
        self.assertEqual(self.controller.data["target_temperature_c"], 180)
        self.assertTrue(self.controller.session_uncertain)

    async def test_ambiguous_write_reconciles_without_retry(self):
        await self.connect()
        self.transport.fail_mutation = True
        with self.assertRaises(VeazyError) as caught:
            await self.controller.execute("set_target", {"value": 190})
        self.assertEqual(caught.exception.code, "write_uncertain")
        self.assertEqual(len(self.transport.mutations), 1)
        self.assertEqual(self.transport.writes[-1][1], 0)
        self.assertEqual(self.controller.confirmation, "unknown")
        self.assertTrue(self.controller.session_uncertain)
        self.assertTrue(self.controller.snapshot()["stale"])
        with self.assertRaises(VeazyError) as caught:
            await self.controller.execute("set_heater_mode", {"mode": 1})
        self.assertEqual(caught.exception.code, "uncertain_session")

    async def test_settings_and_diagnosis(self):
        await self.connect()
        for name, value in (("brightness", 4), ("vibration", False),
                            ("boost_timeout_disabled", True),
                            ("charge_current_optimization", False),
                            ("charge_voltage_limit", False),
                            ("boost_visualization", False),
                            ("permanent_bluetooth", False)):
            result = await self.controller.execute("set_setting", {"name": name, "value": value})
            self.assertEqual(result["confirmation"], "confirmed")
            self.assertEqual(self.controller.data[name], value)
        count = len(self.transport.mutations)
        result = await self.controller.execute("diagnose", {})
        self.assertEqual(result, {"analysis_code": 0x12, "analysis_category": 4})
        self.assertEqual(len(self.transport.mutations), count)

    async def test_serialized_io_and_expired_queue(self):
        await self.connect()
        self.transport.delay = 0.03
        first = asyncio.create_task(self.controller.execute("set_target", {"value": 185}))
        second = asyncio.create_task(self.controller.execute("set_heater_mode", {"mode": 1}))
        await asyncio.sleep(0.01)
        await self.controller.execute("disconnect", {})
        await asyncio.gather(first, second, return_exceptions=True)
        self.assertEqual(self.transport.max_active, 1)
        self.assertEqual(self.transport.mutations, [])
        await self.connect()
        self.assertEqual(self.transport.mutations, [])

    async def test_concurrent_commands_are_serialized_with_polling(self):
        await self.connect()
        self.transport.delay = 0.005
        await asyncio.gather(
            self.controller.execute("set_target", {"value": 185}),
            self.controller.execute("set_heater_mode", {"mode": 1}))
        self.assertEqual(self.transport.max_active, 1)
        self.assertEqual(self.transport.target, 185)
        self.assertEqual(self.transport.mode, 1)
        self.assertEqual(len(self.transport.mutations), 2)

    async def test_disconnect_lost_link_and_old_notifications_unknown(self):
        await self.connect()
        old_notify = self.transport.notify
        self.transport.disconnected_callback()
        self.assertEqual(self.controller.state, "disconnected")
        self.assertTrue(self.controller.snapshot()["stale"])
        self.assertIsNone(self.controller.data["heater_mode"])
        old_notify(status_frame(mode=1))
        self.assertIsNone(self.controller.data["heater_mode"])
        with self.assertRaises(VeazyError):
            await self.controller.execute("set_heater_mode", {"mode": 1})

    async def test_off_still_written_when_status_read_times_out(self):
        await self.connect()
        self.transport.drop_status = True
        result = await self.controller.execute("set_heater_mode", {"mode": 0})
        self.assertEqual(result["confirmation"], "unknown")
        self.assertTrue(self.controller.session_uncertain)
        self.assertEqual(len(self.transport.mutations), 1)
        self.assertEqual(self.transport.mutations[0][11], 0)

    async def test_no_replay_after_reconnect(self):
        await self.connect()
        await self.controller.execute("set_heater_mode", {"mode": 1})
        await self.controller.execute("disconnect", {})
        self.assertIsNone(self.controller.data["heater_mode"])
        count = len(self.transport.mutations)
        await self.controller.execute("connect", {"device_id": "fake-veazy"})
        self.assertEqual(len(self.transport.mutations), count)

    async def test_last_moment_firmware_or_mode_change_blocks_write(self):
        await self.connect()
        original_emit = self.controller.emit
        injected = False

        def emit(event, data):
            nonlocal injected
            original_emit(event, data)
            if not injected and event == "snapshot" and data.get("pending_command"):
                injected = True
                self.transport.notify(status_frame(mode=2, target=180, boost=30))

        self.controller.emit = emit
        with self.assertRaises(VeazyError) as caught:
            await self.controller.execute("set_target", {"value": 190})
        self.assertEqual(caught.exception.code, "effective_limit")
        self.assertEqual(self.transport.mutations, [])

        injected = False

        def invalidate_firmware(event, data):
            nonlocal injected
            original_emit(event, data)
            if not injected and event == "snapshot" and data.get("pending_command"):
                injected = True
                self.transport.notify(bytes([2, 0x11]) + b"\0" * 18)

        self.controller.emit = invalidate_firmware
        with self.assertRaises(VeazyError) as caught:
            await self.controller.execute("set_heater_mode", {"mode": 1})
        self.assertEqual(caught.exception.code, "not_ready")
        self.assertEqual(self.transport.mutations, [])

    async def test_late_response_never_restores_mutation_authority(self):
        class LateResponseTransport(FakeTransport):
            armed = False
            reads = 0

            async def write(self, frame):
                if self.armed and frame[0] == 1 and frame[1] == 0:
                    self.reads += 1
                    self.writes.append(frame)
                    if self.reads == 1:
                        # Capture old OFF status; deliver it after its request
                        # has already timed out and the device entered boost.
                        asyncio.get_running_loop().call_later(0.045, self.notify,
                                                               status_frame(mode=0, target=180))
                    return
                await super().write(frame)

        await self.controller.close()
        self.transport = LateResponseTransport()
        self.controller = Controller(self.transport, lambda event, data: self.events.append((event, data)),
                                     request_timeout=0.03, poll_interval=100)
        await self.connect()
        self.transport.armed = True
        with self.assertRaises(VeazyError) as caught:
            await self.controller._request(1, self.controller.generation)
        self.assertEqual(caught.exception.code, "read_timeout")
        self.transport.mode = 2
        for command, args in (("set_target", {"value": 200}),
                              ("set_heater_mode", {"mode": 1}),
                              ("set_setting", {"name": "brightness", "value": 5})):
            with self.subTest(command=command), self.assertRaises(VeazyError) as caught:
                await self.controller.execute(command, args)
            self.assertEqual(caught.exception.code, "uncertain_session")
        await asyncio.sleep(0.03)
        # The late notification is displayed as stale; it cannot clear poison.
        self.assertEqual(self.controller.data["heater_mode"], 0)
        self.assertTrue(self.controller.snapshot()["stale"])
        self.assertEqual(self.controller.confirmation, "unknown")
        with self.assertRaises(VeazyError):
            await self.controller.execute("set_target", {"value": 200})
        self.assertEqual(self.transport.mutations, [])
        result = await self.controller.execute("set_heater_mode", {"mode": 0})
        self.assertEqual(result["confirmation"], "unknown")
        self.assertEqual(len(self.transport.mutations), 1)
        self.transport.notify(status_frame(mode=0))
        self.assertEqual(self.controller.confirmation, "unknown")
        self.assertTrue(self.controller.snapshot()["stale"])
        await self.controller.execute("disconnect", {})
        self.transport.armed = False
        await self.controller.execute("connect", {"device_id": "fake-veazy"})
        self.assertFalse(self.controller.session_uncertain)
        self.assertFalse(self.controller.snapshot()["stale"])
        self.assertEqual(len(self.transport.mutations), 1)

    async def test_new_connect_waits_for_disconnect_cleanup(self):
        await self.connect()
        original_disconnect = self.transport.disconnect
        started = asyncio.Event()
        released = asyncio.Event()

        async def delayed_disconnect():
            started.set()
            await released.wait()
            await original_disconnect()

        self.transport.disconnect = delayed_disconnect
        disconnect = asyncio.create_task(self.controller.execute("disconnect", {}))
        await started.wait()
        self.assertEqual(self.controller.state, "disconnecting")
        for command, args in (("connect", {"device_id": "fake-veazy"}), ("scan", {})):
            with self.subTest(command=command), self.assertRaises(VeazyError) as caught:
                await self.controller.execute(command, args)
            self.assertEqual(caught.exception.code, "busy")
        released.set()
        await disconnect
        await self.controller.execute("connect", {"device_id": "fake-veazy"})
        self.assertTrue(self.transport.connected)
        self.assertEqual(self.transport.connect_count, 2)
