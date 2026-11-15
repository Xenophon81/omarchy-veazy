// SPDX-License-Identifier: AGPL-3.0-only
// GJS/GLib integration, no display and no BLE discovery or writes.
import GLib from 'gi://GLib';
import {VeazyClient} from '../../platforms/gnome/backend.js';

let checks = 0;
function check(name, value) { if (!value) throw Error(name); checks++; print(`PASS ${name}`); }
function sleep(ms) { return new Promise(resolve => GLib.timeout_add(GLib.PRIORITY_DEFAULT, ms, () => { resolve(); return GLib.SOURCE_REMOVE; })); }
const loop = new GLib.MainLoop(null, false);
let failed = false;
const client = new VeazyClient({path: GLib.get_current_dir(), onChange: () => {}});
async function run() {
    check('startup is mock, disconnected and heater unknown', client.mode === 'mock' && client.state === 'disconnected' && client.snapshot.heater_mode === null);
    check('no worker at startup', client._worker === null);
    check('heating blocked before explicit connection', !client.setHeaterMode(1));
    client.scan(); await sleep(300);
    check('no automatic selection or connection', client.selectedDeviceId === '' && client.state === 'disconnected');
    check('unknown device rejected', !client.selectDevice('unknown'));
    client.selectDevice('mock-veazy'); client.connectDevice();
    check('explicit demo connect leaves heater off', client.state === 'ready' && client.snapshot.heater_mode === 0);
    check('current temperature stays unknown', client.snapshot.current_temperature_c === null);
    check('target change does not heat', client.setTarget(190) && client.snapshot.heater_mode === 0);
    check('explicit boost permitted within limit', client.setHeaterMode(2));
    check('active boost target capped', !client.setTarget(196));
    check('active boost offset capped', !client.setOffset('boost', 21));
    check('superboost uses its own offset and cap', !client.setHeaterMode(3));
    client.snapshot = {...client.snapshot, session_uncertain: true};
    check('uncertain blocks changes', !client.canControl && !client.setTarget(180));
    check('one explicit heater off allowed', client.setHeaterMode(0));
    check('uncertain off is not repeatable', !client.setHeaterMode(0));
    client.disconnectDevice();
    check('disconnect clears telemetry and heater knowledge', client.snapshot.battery_percent === null && client.snapshot.heater_mode === null);
    check('mock never started a worker', client._worker === null);
    client.setMode('live'); await sleep(300);
    check('idle live backend starts disconnected', client._worker && client.state === 'disconnected' && !client.pending);
    const old = client._worker;
    client._uncertainOffUsed = true;
    client._receive(old, {version: 1, session: old.session, event: 'state', data: {state: 'connecting', busy: true}});
    check('explicit new connection resets emergency-off allowance', !client._uncertainOffUsed);
    client._receive(old, {version: 1, session: old.session, event: 'state', data: {state: 'disconnected', busy: false}});
    client._receive(old, {version: 1, session: 'old-session', event: 'state', data: {state: 'ready', busy: false}});
    check('old process messages ignored', client.state === 'disconnected');
    client.setMode('mock');
    check('mock invalidates live telemetry immediately', client.snapshot.heater_mode === null && client.stale);
    check('replacement waits for stop', client.switchingMode && !client.setMode('live'));
    await sleep(400);
    check('worker reaped on entering mock', client._worker === null && !client.switchingMode);
    client.setMode('live'); await sleep(200);
    client._fatal('simulated failure'); await sleep(200);
    check('backend failure clears knowledge and never auto-restarts', client.state === 'error' && client.snapshot.heater_mode === null && client._worker === null);
    client.setMode('mock'); client.destroy();
    check('destroy removes all timers', client._watchdog === 0 && client._mockTimer === 0);
    print(`GNOME_CLIENT_OK ${checks}`);
}
run().catch(error => { failed = true; printerr(error.stack); }).finally(() => { client.destroy(); loop.quit(); });
loop.run();
if (failed) throw Error('GNOME client integration failed');
