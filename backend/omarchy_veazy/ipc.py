# SPDX-License-Identifier: AGPL-3.0-only
"""Bounded JSON Lines protocol. stdout contains protocol messages only."""

import asyncio
import json
import os
import re
import sys

from . import protocol as p
from .errors import VeazyError, safe_message

VERSION = 1
MAX_LINE_BYTES = 4096
MAX_PENDING = 16
ARGUMENTS = {"scan": set(), "connect": {"device_id"}, "disconnect": set(),
             "status": set(), "set_target": {"value"}, "set_heater_mode": {"mode"},
             "set_offset": {"kind", "value"}, "set_setting": {"name", "value"},
             "diagnose": set(), "find_device": set()}


def _unique_pairs(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("Duplicate JSON property")
        data[key] = value
    return data


def parse_request(raw):
    if len(raw) > MAX_LINE_BYTES:
        raise ValueError("IPC line exceeds 4096 bytes")
    data = json.loads(raw, object_pairs_hook=_unique_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite JSON number")))
    if not isinstance(data, dict) or set(data) != {"version", "id", "command", "args"}:
        raise ValueError("Expected version, id, command and args")
    if type(data["version"]) is not int or data["version"] != VERSION:
        raise ValueError("Unsupported IPC version")
    if not isinstance(data["id"], str) or re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", data["id"]) is None:
        raise ValueError("Invalid request id")
    command = data["command"]
    if not isinstance(command, str) or command not in ARGUMENTS:
        raise ValueError("Unsupported command")
    args = data["args"]
    if not isinstance(args, dict) or set(args) != ARGUMENTS[command]:
        raise ValueError("Unexpected command arguments")
    if command == "connect":
        value = args["device_id"]
        if not isinstance(value, str) or not 1 <= len(value) <= 128 or not value.isprintable():
            raise ValueError("Invalid device id")
    elif command == "set_target":
        p.set_target(args["value"])
    elif command == "set_heater_mode":
        p.set_heater_mode(args["mode"])
    elif command == "set_offset":
        p.set_offset(args["kind"], args["value"])
    elif command == "set_setting":
        p.set_setting(args["name"], args["value"])
    return data


class Worker:
    def __init__(self, transport, output=None):
        from .controller import Controller
        self.output = output or sys.stdout
        self.session = os.environ.get("OMARCHY_VEAZY_WORKER_SESSION", "")[:64]
        self.controller = Controller(transport, self.event)
        self.tasks = set()
        self.ids = set()

    def send(self, payload):
        # Single event loop: writes cannot interleave halfway through messages.
        self.output.write(json.dumps({"version": VERSION, "session": self.session} | payload, ensure_ascii=True,
                                     allow_nan=False, separators=(",", ":")) + "\n")
        self.output.flush()

    def event(self, event, data):
        self.send({"event": event, "data": data})

    def error(self, request_id, code, message):
        self.send({"id": request_id, "ok": False,
                   "error": {"code": code, "message": safe_message(message)}})

    async def dispatch(self, request):
        request_id = request["id"]
        try:
            result = await self.controller.execute(request["command"], request["args"])
            self.send({"id": request_id, "ok": True, "result": result})
        except asyncio.CancelledError:
            self.error(request_id, "session_cancelled", "Command cancelled; it will not be replayed")
        except VeazyError as error:
            self.error(request_id, error.code, error)
        except (ValueError, KeyError, TypeError) as error:
            self.error(request_id, "invalid_request", error)
        except Exception as error:
            print(f"Veazy backend error: {type(error).__name__}: {safe_message(error)}", file=sys.stderr)
            self.error(request_id, "bluetooth_error", error)
        finally:
            self.ids.discard(request_id)

    def submit(self, raw):
        try:
            request = parse_request(raw)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            self.error(None, "invalid_request", "Malformed or unsupported JSONL request")
            return
        request_id = request["id"]
        if request_id in self.ids:
            self.error(request_id, "duplicate_id", "Request id is already pending")
            return
        if len(self.tasks) >= MAX_PENDING and request["command"] != "disconnect":
            self.error(request_id, "queue_full", "Too many pending requests")
            return
        self.ids.add(request_id)
        task = asyncio.create_task(self.dispatch(request))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def consume(self, reader):
        """Read in bounded chunks; discard an overlong line without buffering it."""
        pending = bytearray()
        overlong = False
        while chunk := await reader.read(4096):
            for piece_index, piece in enumerate(chunk.split(b"\n")):
                if piece_index:
                    if overlong:
                        self.error(None, "line_too_long", "IPC line exceeds 4096 bytes")
                    elif pending:
                        self.submit(bytes(pending))
                    pending.clear()
                    overlong = False
                if not overlong:
                    if len(pending) + len(piece) > MAX_LINE_BYTES:
                        pending.clear()
                        overlong = True
                    else:
                        pending.extend(piece)
            # Give disconnect and outstanding operations a turn between chunks.
            await asyncio.sleep(0)
        if overlong:
            self.error(None, "line_too_long", "IPC line exceeds 4096 bytes")
        elif pending:
            self.submit(bytes(pending))

    async def run(self):
        self.controller._state("disconnected")
        self.controller._snapshot()
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader(limit=MAX_LINE_BYTES * 2)
        protocol = asyncio.StreamReaderProtocol(reader)
        stdin_transport, _ = await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)
        try:
            await self.consume(reader)
            if self.tasks:
                # EOF means shell unloaded the plugin: cancel work, never drain
                # queued heating commands after the owning UI disappears.
                for task in tuple(self.tasks):
                    task.cancel()
                await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
        finally:
            stdin_transport.close()
            for task in tuple(self.tasks):
                task.cancel()
            if self.tasks:
                await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
            await self.controller.close()
