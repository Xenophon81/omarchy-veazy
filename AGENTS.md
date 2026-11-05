# Projectinstructies voor omarchy-veazy

## Doel en scope

- Bouw een native plugin voor de Omarchy Quickshell-interface om een Storz & Bickel Veazy via Bluetooth LE te bedienen.
- Het icoon hoort standaard rechts in de bestaande balk; bediening opent een native shell-paneel.
- Gebruik geen aparte desktopapp, browser, PWA, Electron of Chromium. Vervang ook niet de volledige Omarchy-balk.
- Lees eerst [docs/PROJECT.md](docs/PROJECT.md) voor onderzoeksbronnen, besluiten, fasering, open vragen en acceptatiecriteria.
- Communiceer en documenteer standaard in het Nederlands; gebruik Engelse code-identifiers en technische logs.

## Grenzen en voortgang

- De eerste documentatiefase is afgerond en gecommit. De vervolgvraag vraagt om een native interface met de relevante upstreamfuncties; implementatie in de repository is nu aan de orde.
- Bouw eerst de mock-plugin, vervolgens de Bluetooth-service en ten slotte hun integratie, volgens de afgesproken fasering.
- De gebruiker heeft op 2026-11-05 expliciet ingestemd met het icoon rechts activeren en Bluetooth-dependencies in de gebruikersmap installeren. Dit is uitgevoerd; vraag voor deze reeds geautoriseerde handelingen niet opnieuw toestemming.
- De plugin is als lokale kopie geïnstalleerd onder `~/.config/omarchy/plugins/io.github.xenophon81.veazy/`; de venv staat onder `~/.local/share/omarchy-veazy/venv`. Runtimecode en repository waren bij oplevering identiek. Houd latere wijzigingen/installatiekopieën bewust bij; iedere wijziging onder de geïnstalleerde plugin kan hot reload en disconnect veroorzaken.
- De gebruiker heeft daarna expliciet een uitleestest van de verbonden Veazy toegestaan en om publicatie van de eerste versie gevraagd. Passieve BlueZ-telemetrie is gevalideerd; zie `docs/HARDWARE_TESTS.md`. Dit is geen toestemming om zelf instellingen of verwarming te wijzigen.
- Accustatus wordt ook in de balk en prominent bovenaan het paneel getoond. Onbekende/verouderde/verbroken data mag geen oud percentage laten zien. De eerste publieke preview is versie `0.1.0`.

## Omarchy-contract

- Verifieer bij implementatie opnieuw `omarchy version`, de geïnstalleerde shellbron en de officiële pluginreferentie. Neem geen Omarchy 3/Waybar-instructies over.
- Onderzoeksbasis op 2026-11-05: Omarchy-pakket `4.5.0-3`, Quickshell `0.3.2.r7.g2b4501a-1`; het losse bestand `/usr/share/omarchy/version` bevat afwijkend `4.0.0.alpha` en is geen betrouwbare pakketversie.
- Lees bij shellintegratie de beschikbare `omarchy`-skill en de pluginhandleiding. Lees pakketbron onder `/usr/share/omarchy/` alleen; wijzig die nooit voor deze plugin.
- Gebruik het officiële `manifest.json` met `schemaVersion: 1` aan de repositoryroot. Een derdepartij-id mag niet met `omarchy.` beginnen.
- Beoogde plugin-id: `io.github.xenophon81.veazy`; kinds `bar-widget` en `service`, standaardsectie `right`, `allowMultiple: false`.
- Bouw op de publieke `qs.Ui`-componenten en de eigen servicefacade. Omzeil de facade niet via de QML-objectboom en neem geen first-party rechten aan.
- Deel één QML-service en één Python-backend over alle monitoren. Start geen BLE-proces per paneel of balkinstantie.
- Gebruik `qs.Commons as Commons` voor `Commons.Color`, shellthema-/spacingtokens en `Style.duration(...)` voor eigen animaties.
- Pluginteksten krijgen eigen vertaalcatalogi, aanvankelijk Nederlands en Engels. Toon apparaat-, fout- en IPC-tekst als `Text.PlainText`; beveilig ook gedeelde tooltip-/notificatiesinks tegen markup.

## Architectuur

- Houd QML-presentatie, IPC, verbindingsbeheer en protocolcodering gescheiden.
- Python met Bleak/BlueZ is de voorkeursbackend; geen Web Bluetooth-runtime.
- Het protocoldeel blijft zuivere Python zonder Bleak-, QML- of procesafhankelijkheden.
- Beoogde IPC: een door de QML-service beheerd `Quickshell.Io.Process` met versiegebonden JSON Lines over stdin/stdout. Logs gaan naar stderr.
- Ieder workerbericht draagt een lokale processessie; negeer oude sessies en serialiseer stoppen/starten bij moduswissels. Dit is IPC-metadata, geen BLE-transaction-id.
- Valideer typen, commando's, berichtlengtes en waardebereiken aan beide IPC-zijden. Gebruik argumentlijsten voor processen; interpoleer geen apparaatdata in shellcommando's.
- Houd dependencies/venvs buiten de geïnstalleerde pluginmap: Omarchy-validatie weigert symlinks binnen een plugin. Geen automatisch downloaden/installeren bij shellstart.
- Dagelijkse bediening werkt als gewone gebruiker via de bestaande BlueZ D-Bus-policy. Voeg geen roothelper of brede rechtenaanpassing toe.

## Protocol en apparaatgedrag

- De onderzochte referentie is `firsttris/reactive-volcano-app`, commit `9d773eff709d721e0e79b403ac2258ba5a851d6c`. Zie de vaste bronlinks in `docs/PROJECT.md`.
- Verzin nooit BLE-UUIDs, opcodes, flags, eenheden of frame-indelingen. Leg voor iedere overgenomen definitie de upstreambron en eventuele hardwarevalidatie vast.
- Maak onderscheid tussen broncode, upstreamdocumentatie, een ontwerpkeuze en een waarneming op de echte Veazy. Documenteer conflicten; behandel aannames niet als bewijs.
- Selecteer expliciet het apparaat en controleer GATT/model/capabilities. Een gedeelde Venty/Veazy-service-UUID bewijst geen Veazy-identiteit.
- Behandel de upstream genoemde actuele-temperatuursentinel `0x8000` als onbekend. Presenteer nooit de doeltemperatuur of een berekende schatting als gemeten temperatuur.
- Onderscheid basisdoel, boost-/superboost-offset, effectief doel en gemeten temperatuur. Verifieer boostgrenzen op hardware.
- Tot hardwarevalidatie geldt de conservatieve effectieve-doelgrens uit `docs/PROJECT.md` voor iedere mutatie die dat doel beïnvloedt, ook bij basisdoel-/offsetwijzigingen in actieve boost. Onbekende heatermodus blokkeert verhogende mutaties; expliciet heater-uit blijft mogelijk.
- Ondersteun instellingen alleen als hun betekenis en Veazy-beschikbaarheid vaststaan. Voeg geen fictieve algemene eco-charging-bit toe.
- Begrens/verifieer frames vóór decodering, serialiseer GATT-operaties, behandel notifications asynchroon en laat een geslaagde GATT-write niet doorgaan voor bewezen apparaatstatus.

## Expliciete gebruikersactie voor verwarming

- Scan en verbind alleen na een gebruikersactie in de eerste implementatie. Starten van de shell/backend of openen van het paneel doet dit niet.
- Verbinden, herverbinden, pollen, status herstellen, mockmodus verlaten en dependencies instellen mogen geen verwarming starten of doel-/boostinstellingen schrijven.
- Verwarming aan/uit, een doeltemperatuur toepassen en boost/superboost activeren komen uitsluitend uit een bewuste bediening door de gebruiker.
- Gebruik afzonderlijke, expliciete opdrachten zoals `set_heater(true/false)` in plaats van een toggle die na timeout kan omkeren.
- Herhaal of bewaar geen verwarmingsopdrachten automatisch bij fouten, procesherstart of reconnect. Gooi oude sessieopdrachten weg; lees eerst opnieuw de status.
- Een read/write-timeout, ambigue GATT-fout of onbevestigde mutatie maakt de sessie blijvend onzeker tot expliciete reconnect. Late responses/polls mogen dat niet herstellen. Blokkeer mutaties, behalve één expliciet heater-uit-verzoek met zichtbaar onbevestigde uitkomst.
- Een verbroken verbinding betekent dat de heaterstatus onbekend is, niet dat de verwarming uitstaat. Maak pending, bevestigd, verouderd en onbekend zichtbaar.
- Mockmodus blijft herkenbaar en strikt gescheiden van echte BLE-writes.

## Licentie en bronvermelding

- Plan afgeleide protocolcode onder `AGPL-3.0-only`, overeenkomstig de upstream pakketmetadata. Behoud auteursrecht- en licentiemeldingen en markeer port/aanpassingen.
- Neem vóór het overnemen/publiceren van code de volledige upstream `LICENSE` en toepasselijke `NOTICE` op en documenteer herkomst per afgeleid bestand.
- Respecteer de aanvullende upstream-attributie in `NOTICE`, inclusief zichtbare vermelding van Reactive Volcano App, Tristan Teufel en de upstream-link in een native informatie-/creditsweergave.
- Controleer apart de licentie/herkomst van eventuele iconen en andere assets.

## Verificatie en oplevering

- Werk in controleerbare fasen; rond eerst de mock af, test daarna protocol/backend onafhankelijk en verbind ze vervolgens met de UI.
- Voor een echte plugin: voer `omarchy plugin validate .` uit. Dit valideert manifest en bestanden, niet het laden/gedrag van QML.
- Test protocolvectoren, sentinelwaarden, korte/corrupte frames, grenswaarden, queue/timeouts, IPC-validatie en het ontbreken van automatische heater-writes met een fake transport.
- Houd hardwaretests apart en expliciet: eerst discovery/alleen uitlezen, daarna door de gebruiker gekozen schrijf-/verwarmingsacties. Claim geen geslaagde hardwaretest zonder echte waarneming.
- Verifieer bij UI-integratie paneelfocus/Escape, thema, meervoudige monitoren, herladen, backenduitval en dynamische tekst/markup.
- Werk `docs/PROJECT.md` bij wanneer een aanname is gevalideerd of een architectuurbesluit verandert; leg beperkingen en uitgevoerde checks eerlijk vast.
