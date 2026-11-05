# SPDX-License-Identifier: AGPL-3.0-only
"""Run with python -u -m omarchy_veazy from the backend directory."""

import asyncio
import signal

from .ipc import Worker
from .transport import BleakTransport


async def main():
    task = asyncio.current_task()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, task.cancel)
    try:
        await Worker(BleakTransport()).run()
    except (asyncio.CancelledError, BrokenPipeError):
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, BrokenPipeError):
        pass
