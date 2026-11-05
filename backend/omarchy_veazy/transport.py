# SPDX-License-Identifier: AGPL-3.0-only
"""Bleak/BlueZ adapter. Importing this module never starts Bluetooth.

Bleak API reference: https://bleak.readthedocs.io/en/latest/api/client.html
and https://bleak.readthedocs.io/en/latest/api/scanner.html (2026-11-05).
Discovery/model definitions: Reactive Volcano App by Tristan Teufel,
commit 9d773eff709d721e0e79b403ac2258ba5a851d6c,
src/provider/BluetoothProvider.tsx and src/utils/uuids.ts.
"""

import asyncio
import re

from .errors import VeazyError
from .protocol import CONTROL_UUID, SERVICE_UUID


def _bleak():
    try:
        from bleak import BleakClient, BleakScanner
    except ImportError as error:
        raise VeazyError("missing_dependency",
                         "Bleak is not installed in the selected Python environment; "
                         "follow README.md dependency setup.") from error
    return BleakClient, BleakScanner


def clean_name(value):
    return "".join(c for c in str(value or "") if c.isprintable())[:96]


def is_veazy_name(value):
    # Upstream distinguishes Veazy S&B VZ from Venty S&B VY. This remains a
    # name-based check plus GATT validation, not cryptographic identification.
    return bool(re.search(r"S&B VZ", value or "", flags=re.IGNORECASE))


class BleakTransport:
    def __init__(self):
        self.candidates = {}
        self.client = None
        self.characteristic = None
        self.response = None

    async def scan(self):
        _, scanner_type = _bleak()
        self.candidates.clear()

        def found(device, advertisement):
            name = clean_name(advertisement.local_name or device.name)
            services = {str(x).lower() for x in advertisement.service_uuids}
            if (name.startswith(("STORZ&BICKEL", "Storz&Bickel", "S&B"))
                    or SERVICE_UUID in services):
                # Bound retained candidates as well as device-provided strings.
                if len(self.candidates) < 64 or device.address in self.candidates:
                    self.candidates[device.address] = (device, name)

        async with scanner_type(detection_callback=found):
            await asyncio.sleep(6)
        return [{"id": key, "name": value[1] or key}
                for key, value in self.candidates.items()]

    async def connect(self, device_id, notify, disconnected):
        client_type, _ = _bleak()
        if self.client is not None:
            await self.disconnect()
        if device_id not in self.candidates:
            raise VeazyError("unknown_device", "Select a device from the latest scan first")
        device, advertised_name = self.candidates[device_id]
        if not is_veazy_name(advertised_name):
            raise VeazyError("unsupported_model", "Selected device is not identified as S&B VZ (Veazy)")
        # Pass BLEDevice, never an address string that triggers implicit scanning.
        def on_disconnected(client):
            if self.client is client:
                self.client = None
                self.characteristic = None
                self.response = None
                disconnected()

        client = client_type(device, disconnected_callback=on_disconnected, pair=False)
        self.client = client
        try:
            async with asyncio.timeout(25):
                await client.connect()
            name = clean_name(getattr(client, "name", advertised_name))
            if not is_veazy_name(name):
                raise VeazyError("unsupported_model", "Connected device name does not identify a Veazy")
            service = client.services.get_service(SERVICE_UUID)
            characteristic = service.get_characteristic(CONTROL_UUID) if service else None
            if characteristic is None:
                raise VeazyError("invalid_gatt", "Veazy control characteristic is missing")
            properties = set(characteristic.properties)
            if "notify" not in properties or not properties.intersection({"write", "write-without-response"}):
                raise VeazyError("invalid_gatt", "Veazy characteristic must support notifications and writes")
            self.characteristic = characteristic
            # Explicit mode derived from actual GATT properties. Never assume
            # a Web Bluetooth write maps to a particular BlueZ write procedure.
            self.response = "write" in properties
            await client.start_notify(characteristic, lambda _sender, data: notify(bytes(data)))
        except BaseException:
            await self.disconnect()
            raise

    async def write(self, frame):
        if self.client is None or self.characteristic is None or not self.client.is_connected:
            raise VeazyError("disconnected", "Bluetooth connection is not available")
        await self.client.write_gatt_char(self.characteristic, frame, response=self.response)

    async def disconnect(self):
        client = self.client
        self.client = None
        self.characteristic = None
        self.response = None
        if client is not None:
            # Disconnect also tears down notifications. Cleanup is attempted
            # even after a partial connect; no reconnect or pairing is initiated.
            try:
                async with asyncio.timeout(5):
                    await client.disconnect()
            except Exception:
                pass
