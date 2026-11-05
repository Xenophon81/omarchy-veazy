# SPDX-License-Identifier: AGPL-3.0-only
import asyncio
import io
import json
import unittest

from omarchy_veazy.ipc import Worker, parse_request
from tests.helpers import FakeTransport


def request(command="status", args=None, **changes):
    return json.dumps({"version": 1, "id": "test-1", "command": command,
                       "args": args or {}} | changes).encode()


class IPCValidationTests(unittest.TestCase):
    def test_valid_commands(self):
        for command, args in (("status", {}), ("scan", {}), ("disconnect", {}),
                              ("connect", {"device_id": "test-device"}),
                              ("set_target", {"value": 185}),
                              ("set_heater_mode", {"mode": 0}),
                              ("set_offset", {"kind": "boost", "value": 15}),
                              ("set_setting", {"name": "brightness", "value": 9}),
                              ("diagnose", {}), ("find_device", {})):
            self.assertEqual(parse_request(request(command, args))["command"], command)

    def test_reject_invalid_envelopes(self):
        for raw in (b"not-json", b"\xff", b"[]", b"{}", b"x" * 4097,
                    request(version=True), request(version=2), request(id=""),
                    request(id=1), request(id="bad\n"), request(command="factory_reset"),
                    request(extra="field"), request("status", {"extra": True}),
                    b'{"version":1,"version":1,"id":"1","command":"status","args":{}}'):
            with self.subTest(raw=raw[:120]), self.assertRaises((ValueError, UnicodeError)):
                parse_request(raw)

    def test_reject_invalid_argument_types_and_ranges(self):
        for command, args in (("set_target", {"value": True}),
                              ("set_target", {"value": float("nan")}),
                              ("set_target", {"value": float("inf")}),
                              ("set_target", {"value": 180.5}),
                              ("set_target", {"value": 211}),
                              ("set_heater_mode", {"mode": True}),
                              ("set_offset", {"kind": "both", "value": 10}),
                              ("set_setting", {"name": "factory_reset", "value": True}),
                              ("set_setting", {"name": "eco_charging", "value": True}),
                              ("set_setting", {"name": "vibration", "value": 1}),
                              ("connect", {"device_id": "bad\n"})):
            with self.subTest(command=command, args=args), self.assertRaises(ValueError):
                parse_request(request(command, args))


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.transport = FakeTransport()
        self.output = io.StringIO()
        self.worker = Worker(self.transport, self.output)

    async def asyncTearDown(self):
        await self.worker.controller.close()

    def messages(self):
        return [json.loads(line) for line in self.output.getvalue().splitlines()]

    async def drain(self):
        if self.worker.tasks:
            await asyncio.gather(*tuple(self.worker.tasks))

    async def test_status_has_no_bluetooth_side_effects(self):
        self.worker.submit(request())
        await self.drain()
        replies = [m for m in self.messages() if m.get("id") == "test-1"]
        self.assertTrue(replies[0]["ok"])
        self.assertIsNone(replies[0]["result"]["heater_mode"])
        self.assertTrue(replies[0]["result"]["stale"])
        self.assertEqual(self.transport.writes, [])
        self.assertEqual(self.transport.scan_count, 0)
        self.assertEqual(self.transport.connect_count, 0)

    async def test_malformed_request_and_duplicate_id_do_not_dispatch(self):
        self.worker.submit(b"bad-json")
        self.worker.submit(request())
        self.worker.submit(request())
        await self.drain()
        errors = [m["error"]["code"] for m in self.messages() if m.get("ok") is False]
        self.assertEqual(errors, ["invalid_request", "duplicate_id"])
        self.assertEqual(self.transport.writes, [])

    async def test_bounded_line_parser_recovers_after_oversize(self):
        reader = asyncio.StreamReader()
        reader.feed_data(b"x" * 12000 + b"\n" + request() + b"\n")
        reader.feed_eof()
        await self.worker.consume(reader)
        await self.drain()
        messages = self.messages()
        self.assertEqual(messages[0]["error"]["code"], "line_too_long")
        self.assertTrue(any(m.get("id") == "test-1" and m.get("ok") for m in messages))

    async def test_missing_dependency_worker_survives(self):
        from unittest.mock import patch
        from omarchy_veazy.errors import VeazyError
        from omarchy_veazy.transport import BleakTransport
        self.worker.controller.transport = BleakTransport()
        with patch("omarchy_veazy.transport._bleak", side_effect=VeazyError("missing_dependency", "Bleak missing")):
            self.worker.submit(request("scan", id="scan"))
            await self.drain()
        self.worker.submit(request(id="after-error"))
        await self.drain()
        messages = self.messages()
        self.assertTrue(any(m.get("id") == "scan" and m["error"]["code"] == "missing_dependency"
                            for m in messages))
        self.assertTrue(any(m.get("id") == "after-error" and m.get("ok") for m in messages))
