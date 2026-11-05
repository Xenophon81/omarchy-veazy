# SPDX-License-Identifier: AGPL-3.0-only
"""Actual JSONL subprocess lifecycle tests; never issue scan/connect commands."""

import asyncio
import json
import os
from pathlib import Path
import sys
import unittest


class WorkerProcessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        backend = Path(__file__).resolve().parents[1] / "backend"
        self.process = await asyncio.create_subprocess_exec(
            sys.executable, "-u", "-m", "omarchy_veazy", cwd=backend,
            env=os.environ | {"PYTHONDONTWRITEBYTECODE": "1",
                              "OMARCHY_VEAZY_WORKER_SESSION": "offline-test-epoch"},
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)

    async def asyncTearDown(self):
        if self.process.returncode is None:
            self.process.terminate()
        await asyncio.wait_for(self.process.wait(), 3)

    async def line(self):
        raw = await asyncio.wait_for(self.process.stdout.readline(), 3)
        self.assertTrue(raw, "Worker stdout ended unexpectedly")
        data = json.loads(raw)
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["session"], "offline-test-epoch")
        return data

    async def startup(self):
        state, snapshot = await self.line(), await self.line()
        self.assertEqual(state, {"version": 1, "session": "offline-test-epoch",
                                 "event": "state", "data": {"state": "disconnected", "busy": False}})
        self.assertEqual(snapshot["event"], "snapshot")
        self.assertTrue(snapshot["data"]["stale"])
        self.assertIsNone(snapshot["data"]["application_valid"])
        self.assertIsNone(snapshot["data"]["heater_mode"])

    async def test_start_status_and_eof_without_bluetooth(self):
        await self.startup()
        self.process.stdin.write(b'{"version":1,"id":"status-1","command":"status","args":{}}\n')
        await self.process.stdin.drain()
        while True:
            message = await self.line()
            if message.get("event") == "state":
                self.assertEqual(message["data"]["state"], "disconnected")
            if message.get("id") == "status-1":
                self.assertTrue(message["ok"])
                self.assertIsNone(message["result"]["heater_mode"])
                break
        self.process.stdin.close()
        await asyncio.wait_for(self.process.wait(), 3)
        self.assertEqual(self.process.returncode, 0)
        self.assertEqual(await self.process.stderr.read(), b"")

    async def test_sigterm_exits_cleanly(self):
        await self.startup()
        self.process.terminate()
        await asyncio.wait_for(self.process.wait(), 3)
        self.assertEqual(self.process.returncode, 0)
        self.assertEqual(await self.process.stderr.read(), b"")
