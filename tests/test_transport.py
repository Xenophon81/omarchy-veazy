# SPDX-License-Identifier: AGPL-3.0-only
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from omarchy_veazy.errors import VeazyError
from omarchy_veazy.protocol import CONTROL_UUID, SERVICE_UUID
from omarchy_veazy.transport import BleakTransport, clean_name, is_veazy_name


class SyntheticClient:
    """Bleak-shaped API double: no adapter or BlueZ access."""
    properties = {"write", "notify"}
    device_name = "S&B VZ test"
    service_present = True
    last = None

    def __init__(self, device, disconnected_callback, pair):
        self.__class__.last = self
        self.device = device
        self.name = self.device_name
        self.is_connected = False
        self.callback = disconnected_callback
        self.pair = pair
        self.written = []
        self.characteristic = SimpleNamespace(properties=self.properties)
        service = SimpleNamespace(get_characteristic=lambda uuid: self.characteristic if uuid == CONTROL_UUID else None)
        self.services = SimpleNamespace(get_service=lambda uuid: service if self.service_present and uuid == SERVICE_UUID else None)

    async def connect(self):
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False

    async def start_notify(self, characteristic, callback):
        self.notify = callback

    async def write_gatt_char(self, characteristic, frame, *, response):
        self.written.append((frame, response))


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.transport = BleakTransport()
        SyntheticClient.properties = {"notify", "write"}
        SyntheticClient.device_name = "S&B VZ test"
        SyntheticClient.service_present = True
        self.device = SimpleNamespace(address="test", name="S&B VZ test")
        self.transport.candidates["test"] = (self.device, "S&B VZ test")
        self.patcher = patch("omarchy_veazy.transport._bleak", return_value=(SyntheticClient, None))
        self.patcher.start()

    async def asyncTearDown(self):
        await self.transport.disconnect()
        self.patcher.stop()

    async def test_selected_object_no_implicit_scan_no_pair(self):
        await self.transport.connect("test", lambda data: None, lambda: None)
        self.assertIs(SyntheticClient.last.device, self.device)
        self.assertFalse(SyntheticClient.last.pair)
        await self.transport.write(b"test")
        self.assertEqual(SyntheticClient.last.written, [(b"test", True)])

    async def test_write_without_response_derived_from_properties(self):
        SyntheticClient.properties = {"notify", "write-without-response"}
        await self.transport.connect("test", lambda data: None, lambda: None)
        await self.transport.write(b"test")
        self.assertEqual(SyntheticClient.last.written, [(b"test", False)])

    async def test_reject_unknown_model_and_invalid_gatt(self):
        with self.assertRaises(VeazyError):
            await self.transport.connect("unknown", lambda data: None, lambda: None)
        self.transport.candidates["venty"] = (self.device, "S&B VY123456")
        with self.assertRaises(VeazyError) as caught:
            await self.transport.connect("venty", lambda data: None, lambda: None)
        self.assertEqual(caught.exception.code, "unsupported_model")
        for props in ({"write"}, {"notify"}, set()):
            SyntheticClient.properties = props
            with self.assertRaises(VeazyError) as caught:
                await self.transport.connect("test", lambda data: None, lambda: None)
            self.assertEqual(caught.exception.code, "invalid_gatt")
            self.assertFalse(SyntheticClient.last.is_connected)
        SyntheticClient.properties = {"write", "notify"}
        SyntheticClient.service_present = False
        with self.assertRaises(VeazyError) as caught:
            await self.transport.connect("test", lambda data: None, lambda: None)
        self.assertEqual(caught.exception.code, "invalid_gatt")

    async def test_connected_model_rechecked_and_text_bounded(self):
        SyntheticClient.device_name = "S&B VY123456"
        with self.assertRaises(VeazyError) as caught:
            await self.transport.connect("test", lambda data: None, lambda: None)
        self.assertEqual(caught.exception.code, "unsupported_model")
        self.assertFalse(SyntheticClient.last.is_connected)
        self.assertEqual(clean_name("S&B VZ\n\0"), "S&B VZ")
        self.assertEqual(len(clean_name("x" * 500)), 96)
        self.assertTrue(is_veazy_name("S&B VZ123"))
        self.assertFalse(is_veazy_name("S&B VY123"))

    async def test_link_loss_clears_transport_reference_and_notifies_once(self):
        lost = []
        await self.transport.connect("test", lambda data: None, lambda: lost.append(True))
        client = SyntheticClient.last
        client.is_connected = False
        client.callback(client)
        client.callback(client)
        self.assertIsNone(self.transport.client)
        self.assertIsNone(self.transport.characteristic)
        self.assertEqual(lost, [True])
