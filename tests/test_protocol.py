# SPDX-License-Identifier: AGPL-3.0-only
import unittest

from omarchy_veazy import protocol as p
from tests.helpers import status_frame


class ProtocolTests(unittest.TestCase):
    def test_observed_veazy_status_frame(self):
        # Passive hardware sample; contains no device address or serial number.
        command, data = p.decode(bytes.fromhex("0100008034080f0f0e000000000182000000"))
        self.assertEqual(command, p.Command.STATUS)
        self.assertEqual(data["battery_percent"], 14)
        self.assertTrue(data["charging"])
        self.assertEqual(data["target_temperature_c"], 210)
        self.assertEqual(data["heater_mode"], 0)
        self.assertEqual(data["current_temperature_raw"], 0x8000)
        self.assertIsNone(data["current_temperature_c"])

    def test_known_byte_vectors(self):
        self.assertEqual(p.set_target(185).hex(), "010200003a070000000000000000000000000000")
        self.assertEqual(p.set_heater_mode(3), bytes([1, 0x20] + [0] * 9 + [3] + [0] * 8))
        self.assertEqual(p.set_offset("boost", 15)[1:8], bytes([4, 0, 0, 0, 0, 15, 0]))
        self.assertEqual(p.set_offset("superboost", 30)[1:8], bytes([8, 0, 0, 0, 0, 0, 30]))
        self.assertEqual(p.read_request(6), b"\x06" + b"\0" * 6)
        self.assertEqual(p.find_device(), b"\x0d\x01" + b"\0" * 18)

    def test_settings_write_masks_and_inversion(self):
        current = p.set_setting("charge_current_optimization", True)
        self.assertEqual((current[1], current[14], current[15]), (0x80, 8, 8))
        voltage = p.set_setting("charge_voltage_limit", False)
        self.assertEqual((voltage[14], voltage[15]), (0, 0x20))
        visual = p.set_setting("boost_visualization", True)
        self.assertEqual((visual[14], visual[15]), (0, 0x40))
        self.assertEqual(p.set_setting("brightness", 7), bytes([6, 1, 7, 0, 0, 0, 0]))
        self.assertEqual(p.set_setting("vibration", True), bytes([6, 8, 0, 0, 0, 1, 0]))
        self.assertEqual(p.set_setting("boost_timeout_disabled", True), bytes([6, 16, 0, 0, 0, 0, 1]))
        permanent = p.set_setting("permanent_bluetooth", False)
        self.assertEqual((permanent[1], permanent[16], permanent[17]), (0x80, 0, 1))

    def test_range_and_type_validation(self):
        for value in (True, False, 39, 211, 180.5, float("nan"), float("inf"), "180", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                p.set_target(value)
        for name, value in (("brightness", 0), ("brightness", 10), ("vibration", 1),
                            ("factory_reset", True), ("eco_charging", True)):
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                p.set_setting(name, value)
        for value in (-1, 4, True, 1.0):
            with self.assertRaises(ValueError):
                p.set_heater_mode(value)
        for value in (0, 100, True):
            with self.assertRaises(ValueError):
                p.set_offset("boost", value)

    def test_status_sentinel_optional_and_invalid_values(self):
        _, data = p.decode(status_frame(length=15))
        self.assertIsNone(data["current_temperature_c"])
        self.assertEqual(data["current_temperature_raw"], 0x8000)
        self.assertIsNone(data["permanent_bluetooth"])
        self.assertEqual(data["target_temperature_c"], 180)
        self.assertTrue(data["charging"])
        self.assertTrue(data["boost_visualization"])
        _, data = p.decode(status_frame(current_raw=1854, battery=255, mode=255, target=300))
        self.assertEqual(data["current_temperature_c"], 185.4)
        self.assertIsNone(data["battery_percent"])
        self.assertIsNone(data["heater_mode"])
        self.assertIsNone(data["target_temperature_c"])
        self.assertIsNone(p.decode(status_frame(current_raw=3001))[1]["current_temperature_c"])
        self.assertEqual(p.decode(status_frame(current_raw=3000))[1]["current_temperature_c"], 300)

    def test_corrupt_short_and_unknown_frames(self):
        for command, length in p.MIN_LENGTHS.items():
            for size in range(length):
                frame = bytes([command] + [0] * (size - 1)) if size else b""
                with self.subTest(command=command, size=size):
                    self.assertIsNone(p.decode(frame))
        for frame in (b"\xff" * 20, b"\x01" * 513, None, "not bytes"):
            self.assertIsNone(p.decode(frame))

    def test_firmware_flags_and_other_fields(self):
        for flags, valid in ((1, True), (0, False), (0x11, False), (0x21, False)):
            frame = bytes([2, flags]) + b"V01.23" + b"\0" * 3 + b"V00.01" + b"\0" * 3
            self.assertEqual(p.decode(frame)[1]["application_valid"], valid)
        data = p.decode(bytes([4, 0x56, 0x34, 0x12, 0xCC, 0xBB, 0xAA]) + b"\0" * 13)[1]
        self.assertEqual(data["heater_runtime_minutes"], 0x123456)
        self.assertEqual(data["charging_time_minutes"], 0xAABBCC)
        frame = bytearray(18)
        frame[0] = 5
        frame[9:15] = b"123456"
        frame[15:17] = b"VZ"
        self.assertEqual(p.decode(frame)[1], {"serial_number": "VZ123456", "color_index": None})

    def test_effective_target_semantics(self):
        data = {"target_temperature_c": 180, "heater_mode": 2,
                "boost_offset_c": 15, "superboost_offset_c": 30}
        self.assertEqual(p.effective_target(data), 195)
        self.assertEqual(p.effective_target(data, heater_mode=3), 210)
        self.assertIsNone(p.effective_target(data, heater_mode=None))
        self.assertIsNone(p.effective_target(data, boost_offset_c=None))
