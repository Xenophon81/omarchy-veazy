# Hardware observations

## 19 November 2026 — passive telemetry with the GNOME widget

The user reported that the Veazy was powered on, charging and displaying data in
the GNOME widget. With that existing connection, `scripts/check-device-readonly
--seconds 8` observed 14 new STATUS notifications and one cached STATUS sample.
The observer sent **zero GATT operations**; it did not scan or connect.

| Check | Observation |
| --- | --- |
| Notifications | `Notifying=true`; 14 new STATUS frames in eight seconds |
| Characteristic flags | `write-without-response`, `write`, `notify` |
| Battery | 32%, charging true; historical sample only |
| Base target | 210 °C |
| Boost / superboost offsets | 15 / 15 °C |
| Heater | Mode `0`, off; powered on does not mean heating |
| Measured temperature | Sentinel `0x8000`, decoded as unavailable |

This confirms live read telemetry alongside the user's GNOME widget on the
Ubuntu host. No target, heater or settings mutations were tested. Heating,
boost semantics and settings writes remain unvalidated on hardware, and the
conservative 210 °C effective-target limit remains in place. Device identifiers
are omitted.

## 5 November 2026 — first passive Veazy telemetry check

Environment: Omarchy `4.5.0-3`, Quickshell `0.3.2.r7.g2b4501a-1`, BlueZ `5.87`, Python `3.14.8`, Bleak `3.0.2`, dbus-fast `5.2.0`, Intel `MacBookPro15,2`.

The user connected their Veazy through the native panel and explicitly invited read-only testing. The observer used the existing BlueZ connection; it created no second Bleak client, performed no scan and sent no GATT operation. Device addresses and serial numbers are omitted.

| Check | Observation |
| --- | --- |
| BlueZ connection | `Connected=true`, `ServicesResolved=true` |
| Bonding | `Paired=false`; protocol telemetry works without bonding on this device |
| GATT service | Expected S&B service and exactly one expected control characteristic present |
| Characteristic flags | `write-without-response`, `write`, `notify` |
| Notifications | `Notifying=true`; repeated live responses observed |
| Eight-second sample | 15 STATUS frames, including one cached sample; one EXTENDED_DATA notification |
| Battery | Valid percentage in STATUS byte 8; charging flag reported true; also visible in the native panel |
| Temperature | Base target reported as 210 °C; current measurement sentinel `0x8000`, shown as unavailable |
| Heater | Mode `0`, off, in observed frames |
| Runtime | Heater-runtime and charging-time counters decoded from EXTENDED_DATA |

The observer sent **zero GATT requests**. Existing plugin polling requested status as usual. No target, offset, heater, charging, brightness, vibration or other setting was changed by the test.

This establishes native read telemetry on this particular device and adapter. It does not establish the behavior of heating/boost/settings writes, other firmware versions, battery calibration, factory reset or firmware update. The conservative 210 °C effective-target limit remains in place.

The original STATUS frame is retained here without a device identifier for reproducible decoder checks:

```text
01 00 00 80 34 08 0f 0f 0e 00 00 00 00 01 82 00 00 00
```

This sample decodes to battery 14%, charging, base target 210 °C, offsets 15/15 °C, heater off and an unavailable measured temperature. The percentage is a historical sample, not a current battery promise.

To repeat this passive test while the native panel is connected:

```bash
~/.local/share/omarchy-veazy/venv/bin/python scripts/check-device-readonly --seconds 8
```

Use the corresponding `$XDG_DATA_HOME` path when configured. The script reads BlueZ object metadata and subscribes to existing property-change signals. It does not call discovery, connect, pairing, ReadValue, WriteValue or StartNotify. Without an active stream it reports a failed observation rather than starting one.
