# v0.3.0 — GNOME-statusanimaties en eenvoudiger bijwerken

Preview · 19 november 2026

- Demo/Bluetooth staat onder Instellingen → Verbindingsmodus.
- Bevestigd opwarmen krijgt een pulserende gloed; boost en superboost eigen kleuren en een buitenaccent. Een bewegende laadindicator toont bevestigd laden.
- Animaties volgen de GNOME-voorkeur en stoppen bij gesloten paneel, veroudering of uitschakelen.
- `python3 scripts/gnome-extension update [zip]` werkt expliciet bij met backup. Meld daarna af en opnieuw aan.
- README-screenshots bijgewerkt naar de huidige native interface; de afbeeldingen tonen uitsluitend offline demo.

De BLE-opdrachten en conservatieve effectieve-doelgrens van 210 °C veranderen niet. Heater-/instellingswrites zijn nog niet hardwaregevalideerd. Passieve telemetrie op Ubuntu is wel waargenomen; zie [HARDWARE_TESTS.md](HARDWARE_TESTS.md).

---

# v0.2.0 — Native GNOME en Omarchy

Preview · 15 november 2026

Veazy heeft nu een native **GNOME Shell 46-extensie voor Ubuntu 24.04 LTS**, geschikt voor **X11 en Wayland**, naast de bestaande Omarchy Quickshell-plugin. Beide interfaces gebruiken één gedeelde Python/Bleak-codebase. Deze preview bevat een direct installeerbare GNOME-extension-zip.

## Nieuw

- Rechts in de bestaande GNOME-balk: Veazy-icoon en batterijpercentage; native paneel met doeltemperatuurboog, donkere kaarten en oranje accenten geïnspireerd op Reactive Volcano App.
- Basisdoel bewerken en apart toepassen; afzonderlijke knoppen voor verwarmen, stoppen, boost en superboost. Gemeten temperatuur blijft afzonderlijk en kan onbekend zijn.
- Apparaatinstellingen, offsets, firmware-/runtimegegevens, ruwe diagnostiek en zichtbare upstreamcredits. Nederlands en Engels volgen de desktoptaal.
- Herkenbare offline demo, expliciete apparaatkeuze en verbinding, pending/onbekende/verouderde status, geen automatische opdrachten of reconnect.
- GJS-procesbeheer met begrensde JSONL-pipes, worker-sessies, veilige moduswissels en opruimen bij uitschakelen. Geen browser, webserver of apart appvenster.
- Reproduceerbaar installatiepakket en lokale installer met backup; dependencies alleen via expliciete setup buiten de extensiemap.
- Project opgesplitst in `platforms/gnome`, `platforms/omarchy` en gedeelde `backend`. De Omarchy-plugin-id, rootmanifest, repository-URL en venv-locatie blijven behouden.

## Gecontroleerd

- Ubuntu 24.04.5 LTS, GNOME Shell 46.0 / Mutter 46.2, GJS 1.80.2, Python 3.12.3.
- **19 native UI-controles op zowel X11 als Wayland** in geïsoleerde GNOME-testsessies, inclusief laden, bediening in demo, concept/toepassen, onbekende temperatuur, verouderde batterij, Escape en disable/enable. Vier Wayland-screenshots zijn visueel gecontroleerd. X11-opnamen via de geneste Xephyr-screenshot-API zijn overgeslagen omdat die API niet terugkeerde.
- **40 Python-tests**, **6 JavaScript-validatietests** en **25 GJS-clientcontroles**, zonder fysieke BLE-opdrachten. Installer-/updatetests bevestigen pakketinhoud, backup en werkende workerpaden.
- Officiële Omarchy-validator uit `quattro`, commit `197f5ede68d044ad15ad6ccef4b6a2ab0fca92a1`, accepteert het rootmanifest en de verplaatste bestanden. Omarchy/Quickshell zijn niet geïnstalleerd op de Ubuntu-host; QML-runtimechecks moeten daar opnieuw worden uitgevoerd.

## Grenzen van deze preview

**Er zijn geen nieuwe hardwaretests uitgevoerd. Verwarming, doeltemperatuur-, boost- en instellingenwrites zijn nog niet op een fysieke Veazy bevestigd.** De eerdere 0.1.0-waarnemingen betreffen passieve telemetrie; zie [HARDWARE_TESTS.md](HARDWARE_TESTS.md).

Effectieve doelen boven 210 °C blijven geblokkeerd. Een ontbrekende meting wordt niet door een doel of schatting vervangen. Timeouts/ambigue resultaten blokkeren mutaties tot een expliciete reconnect; één bewuste heater-uit-opdracht blijft zichtbaar onbevestigd. Disconnect betekent heater onbekend.

Andere GNOME-versies, meerdere monitoren, fractionele schaling, schermlezers en fysieke BLE-werking op Ubuntu vragen verdere validatie. Firmware-updates, factory reset en andere apparaatmodellen vallen buiten scope. De geïnstalleerde Omarchy-kopie is niet automatisch vervangen.

## Ubuntu installeren

```bash
gnome-extensions install veazy@xenophon81.github.io.shell-extension.zip
bash ~/.local/share/gnome-shell/extensions/veazy@xenophon81.github.io/scripts/setup-backend
# Meld af en opnieuw aan, dan:
gnome-extensions enable veazy@xenophon81.github.io
```

Indien nodig eerst `sudo apt install python3-venv bluez`. Na installatie en updates is een nieuwe aanmeldsessie de gemeenschappelijke route voor X11 en Wayland. Er is geen automatische shellherstart. Zie [GNOME.md](GNOME.md) en [README](../README.md) voor broninstallatie, updates en gebruik.

## Bronnen

**[Reactive Volcano App by Tristan Teufel](https://github.com/firsttris/reactive-volcano-app)** blijft de bron van de protocolport en de visuele inspiratie. Onderzocht op `9d773eff709d721e0e79b403ac2258ba5a851d6c`. [storz-rs](https://github.com/flakesonnix/storz-rs), commit `07bf74be90b705eb3d2caa783542976b16c0f78a`, is als aanvullende referentie gelezen; geen Rust-code overgenomen. Licentie blijft [AGPL-3.0-only](../LICENSE), met [NOTICE](../NOTICE) en native credits.

---

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
