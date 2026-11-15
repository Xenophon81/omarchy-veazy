# GNOME-extensie op Ubuntu 24.04 LTS

De extensie richt zich op **GNOME Shell 46**, de shell van Ubuntu 24.04 LTS. De bediening is opgebouwd uit GNOME St/Clutter-componenten en Cairo; er is geen X11-specifieke code. X11 en Wayland gebruiken dezelfde extensie en BlueZ-backend.

## Installeren uit een release

1. Download `veazy@xenophon81.github.io.shell-extension.zip` van [GitHub Releases](https://github.com/Xenophon81/omarchy-veazy/releases).
2. Installeer met `gnome-extensions install <pad-naar-zip>`. Bij een update: `gnome-extensions install --force <pad-naar-zip>`.
3. Indien nodig: `sudo apt install python3-venv bluez`.
4. Voer expliciet `bash ~/.local/share/gnome-shell/extensions/veazy@xenophon81.github.io/scripts/setup-backend` uit.
5. Meld je af en opnieuw aan. Doe dit ook na een update; GNOME kan eerder geladen JavaScript-modules binnen dezelfde sessie bewaren.
6. Activeer met `gnome-extensions enable veazy@xenophon81.github.io`.

Op Wayland kan GNOME niet met Alt+F2 → `r` worden herstart. Afmelden/aanmelden is de gemeenschappelijke werkwijze voor beide sessietypen. Sluit of bewaar eerst je werk voordat je zelf afmeldt. De installer meldt je nooit automatisch af en herstart de shell niet.

De broninstaller is een alternatief:

```bash
python3 scripts/gnome-extension build
python3 scripts/gnome-extension install
bash scripts/setup-backend
```

Het pakket bevat alle extensiebestanden, de gedeelde Python-backend, de dependencieslijst en LICENSE/NOTICE. Het bevat geen venv, symlinks, tests, QML of downloads bij het aanmelden. De lokale installer bouwt niet impliciet; voer `build` ook na bronwijzigingen uit. Een vorige installatie wordt bewaard onder `~/.local/share/gnome-shell/veazy-extension-backups/`. Een reeds geladen versie blijft tot een nieuwe aanmeldsessie in het geheugen.

`XDG_DATA_HOME` wordt ondersteund voor zowel extensie als dependencysetup. Het bewaarde venv-pad is `$XDG_DATA_HOME/omarchy-veazy/venv` (standaard `~/.local/share/omarchy-veazy/venv`), zodat Omarchy en GNOME dezelfde dependencies kunnen gebruiken. De twee interfaces moeten niet tegelijk hetzelfde apparaat verbinden; er is geen inter-desktop-verbindingscoördinatie.

## Eerste gebruik

De extensie start in herkenbare **Demo**. Kies **Ontdek de demo**, dan **Verbind** bij het gevonden demoapparaat. Dit start geen Python-worker en geen BLE-actie. Wisselen naar **Bluetooth** start één nog niet verbonden worker. Vervolgens kies je zelf zoeken, een gevonden apparaat en verbinden.

Bewerk het basisdoel met de invoer of plus/min; **Toepassen** is een aparte actie. **Verwarm**, **Uit**, **Boost** en **Superboost** sturen elk een absolute modus. Een doeltemperatuur instellen start geen verwarming. Instellingswijzigingen en de vindfunctie vragen eveneens een expliciete bediening.

De temperatuurboog geeft uitsluitend het **effectieve doel** weer. Een Veazy-sentinel `0x8000` blijft een ontbrekende meting. Bij disconnect of veroudering verdwijnen het accupercentage en het bevestigde doel. Het apparaat kan zelfstandig blijven verwarmen.

Timeouts en onzekere resultaten worden zichtbaar; verdere mutaties blokkeren tot reconnect. Er is geen automatisch reconnecten, herstel van apparaatinstellingen of opnieuw afspelen van opdrachten. In een onzekere sessie kan één expliciete heater-uit-opdracht verstuurd worden; de uitkomst blijft onbevestigd.

## Probleemoplossing en uitschakelen

```bash
gnome-shell --version
gnome-extensions info veazy@xenophon81.github.io
journalctl --user -b --no-pager | rg -i 'veazy|gnome-shell'
gnome-extensions disable veazy@xenophon81.github.io
```

- **Extensie niet gevonden:** meld af/aan na installatie en controleer de mapnaam/UUID.
- **Andere GNOME-versie:** alleen 46 is gedeclareerd. Zet versiecontrole niet uit; nieuwere versies vragen eigen tests.
- **Backend stopt:** controleer dat de expliciete dependencysetup geslaagd is. Wissel Demo → Bluetooth om opnieuw een lege worker te starten; oude opdrachten worden niet herhaald.
- **Geen apparaat:** controleer Bluetooth in Ubuntu-instellingen, zet de Veazy aan en verbreek een eventuele verbinding met een andere app. Kies daarna opnieuw zoeken. Er worden geen algemene polkitregels of roothelpers toegevoegd.
- **Status onbevestigd:** verbreek de verbinding en verbind bewust opnieuw. Een late notification herstelt een onzekere commandosessie niet.

Verwijderen kan met `gnome-extensions uninstall veazy@xenophon81.github.io`. De aparte venv blijft bewaard en wordt ook door een eventuele Omarchy-installatie gebruikt.

## Uitgevoerde en open controles

De GNOME-client is getest met GJS 1.80.2 en de native interface met GNOME Shell 46.0 / Mutter 46.2. De UI-tests gebruiken gesimuleerde apparaatgegevens in eigen sessies en controleren laden, paneel, concepttemperatuur/toepassen, expliciete bediening, pagina's, veroudering, uitschakelen en opnieuw inschakelen. De testharness blokkeert Bleak-imports. Op beide sessietypen zijn 19 native UI-controles geslaagd, inclusief Escape en uitschakelen/opnieuw inschakelen. Vier screenshots zijn op de headless Wayland-testshell gemaakt en visueel beoordeeld. De screenshot-API reageerde niet onder Xephyr; de X11-harness slaat die opname over en controleert de bediening. Screenshots tonen simulatie, geen hardwaretest.

De Python-code draait hier onder Python 3.12.3; de bestaande 38 protocol-/controller-/transport-/IPC-tests blijven geslaagd. De GNOME-tests voegen JSONL-/schema-/grenscontroles en GJS-procesbeheercontroles toe. Er zijn tijdens deze implementatie geen hardware-opdrachten verstuurd.

Nog apart te beoordelen: fysiek Bluetooth-gebruik op deze Ubuntu-installatie, echte heater-/instellingswrites, schermlezers, fractionele schaling, meerdere monitoren en kleine schermen. De panelinhoud is scrollbaar en past zijn maximumhoogte aan het scherm aan. Plaatsing volgt GNOME's eigen paneelmenu; de desktopbalk wordt niet vervangen.

## API-bronnen

- [GNOME-extensies maken (ES modules)](https://gjs.guide/extensions/development/creating.html)
- [GNOME Shell 46-portingnotities](https://gjs.guide/extensions/upgrading/gnome-shell-46.html)
- [Gio.Subprocess en asynchrone pipes](https://gjs.guide/guides/gio/subprocesses.html)
- Lokale GNOME-bronmodules gelezen via `gresource` uit `/usr/lib/gnome-shell/libshell-14.so`: `panelMenu.js`, `popupMenu.js`, `extensionSystem.js`, `shellDBus.js` en `screenshot.js`.
