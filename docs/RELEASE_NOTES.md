# v0.1.0 — First native preview

Initial release · 5 November 2026

Veazy controls now live in the existing Omarchy Quickshell bar: click the icon on the right to open a native, themed panel. The release includes a clearly marked offline demo and a Python/Bleak backend for Linux BlueZ.

## Included

- Explicit device search, selection, connect and disconnect.
- Base and effective target temperatures, heater controls, boost and superboost.
- Battery gauge, percentage and charging indication.
- Device-reported vibration, brightness and charging options, plus read-only diagnostics.
- English and Dutch text, connection errors, pending/unknown states and upstream credits.
- Official Omarchy plugin manifest, user dependency setup and offline protocol, controller, IPC and QML checks.

## Verified in this release

The panel is installed in the existing shell on an Intel MacBook Pro (`MacBookPro15,2`) running Omarchy `4.5.0-3`, Quickshell `0.3.2.r7.g2b4501a-1`, Python `3.14.8` and BlueZ `5.87`. The user environment uses Bleak `3.0.2` and dbus-fast `5.2.0`.

An eight-second passive BlueZ observation of an already connected Veazy collected 15 `STATUS` frames (including one cached sample) and one `EXTENDED_DATA` notification. Those frames contained valid battery percentage, charging state, target temperature and heater mode. The observer sent zero GATT operations; existing plugin polling continued as usual. No heater, target, boost or settings command was sent during that observation. The characteristic exposes both write modes and notifications; the transport explicitly selects writes with response when supported. See [hardware observations](HARDWARE_TESTS.md).

The measured-temperature field was `0x8000`. The interface treats this as unavailable and never substitutes the target temperature as a measurement.

Offline tests cover protocol decoding and bounds, unknown/malformed values, read-only initialization, serialized GATT operations, timeout handling, no command replay, IPC validation and fake transport behavior. QML checks cover the mock service, an idle live worker without Bluetooth access, display helpers and native component compilation.

## Preview boundaries

- **Heating, target, boost and settings writes have not been tested on the physical device.** Simulated tests establish code behavior, not device behavior.
- Effective targets above **210 °C** are blocked while hardware semantics remain unverified. Superboost follows the upstream base-plus-own-offset interpretation.
- Startup, opening the panel, connecting, polling and reconnecting send no heating or settings mutations. Searching and connecting require explicit user actions; there is no automatic reconnect.
- An ambiguous command or timeout leaves the session uncertain until an explicit reconnect. The interface permits one explicit, visibly unconfirmed heater-off request. Disconnecting does not establish that heating is off.
- Settings availability depends on reported firmware fields. Diagnostics preserve unknown codes without inventing manufacturer meanings.
- Multiple monitors, alternate bars, other Veazy firmware versions and a clean end-to-end Git installation/update/removal still need validation. The supported host is the built-in Omarchy bar.
- Firmware updates, factory reset and other device models are outside this release.

## Install

```bash
omarchy plugin add https://github.com/Xenophon81/omarchy-veazy.git --enable
bash ~/.config/omarchy/plugins/io.github.xenophon81.veazy/scripts/setup-backend
```

The plugin begins in **Demo** mode. For live telemetry, open the icon and select **Bluetooth → Find Veazy**, choose your device, then connect. See the [README](../README.md) for usage, updates and local development.

## Attribution

Protocol port based on **[Reactive Volcano App by Tristan Teufel](https://github.com/firsttris/reactive-volcano-app)**, commit `9d773eff709d721e0e79b403ac2258ba5a851d6c`. Distributed under [AGPL-3.0-only](../LICENSE); the [NOTICE](../NOTICE) preserves upstream attribution and identifies the project adaptations.
