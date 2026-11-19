// SPDX-License-Identifier: AGPL-3.0-only
// Loaded only in a private GNOME session by scripts/check-gnome-shell.
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

function pause(ms) { return new Promise(resolve => GLib.timeout_add(GLib.PRIORITY_DEFAULT, ms, () => { resolve(); return GLib.SOURCE_REMOVE; })); }
let count = 0;
function check(name, condition) { if (!condition) throw Error(name); count++; console.log(`VEAZY_SHELL_PASS ${name}`); }
async function screenshot(name) {
    if (GLib.getenv('VEAZY_TEST_CAPTURE') !== '1') return;
    const path = `${GLib.getenv('VEAZY_TEST_OUTPUT')}/${name}.png`;
    const stream = Gio.File.new_for_path(path).replace(null, false, Gio.FileCreateFlags.NONE, null);
    const shooter = new Shell.Screenshot();
    await new Promise((resolve, reject) => shooter.screenshot(false, stream, (obj, result) => {
        try { obj.screenshot_finish(result); resolve(); } catch (error) { reject(error); }
    }));
    stream.close(null);
}
export default class Test extends Extension {
    enable() {
        GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 4, () => {
            this._run().catch(error => {
                console.error(`VEAZY_SHELL_FAIL ${error.message}: ${error.stack}`);
            }).finally(() => GLib.timeout_add(GLib.PRIORITY_DEFAULT, 300, () => {
                global.context.terminate(); return GLib.SOURCE_REMOVE;
            }));
            return GLib.SOURCE_REMOVE;
        });
    }
    async _run() {
        const ext = Main.extensionManager.lookup('veazy@xenophon81.github.io');
        check('extension loaded without errors', ext?.state === 1 && !ext.errors?.length);
        const i = ext.stateObj._indicator;
        const c = i._client;
        check('native panel starts mock and disconnected', c.mode === 'mock' && c.state === 'disconnected' && !c._worker);
        Main.overview.hide();
        await pause(400);
        i.menu.open();
        await pause(300);
        check('panel opens without scanning or connecting', i.menu.isOpen && c.state === 'disconnected');
        check('mode selection lives in settings', i._demoButton.get_parent().get_parent() === i._pages.settings && !i._pages.settings.visible);
        check('unknown battery is hidden from bar', !i._barBattery.text.includes('%'));
        await screenshot('disconnected');
        c.scan(); await pause(350);
        check('scan never auto-selects', c.devices.length === 1 && c.selectedDeviceId === '');
        c.selectDevice('mock-veazy'); c.connectDevice();
        await pause(300);
        check('explicit demo connect does not heat', c.snapshot.heater_mode === 0 && c.state === 'ready');
        check('demo battery visible and marked', i._barBattery.text.includes('82%') && i._barBattery.text.includes('D'));
        check('measurement remains unavailable', c.snapshot.current_temperature_c === null && !i._measured.text.includes('185'));
        i._plus.emit('clicked', 1);
        check('temperature editing only changes draft', i._draftTarget === 186 && c.snapshot.target_temperature_c === 185);
        i._apply.emit('clicked', 1);
        check('apply sends explicit target, leaves heater off', c.snapshot.target_temperature_c === 186 && c.snapshot.heater_mode === 0);
        c.setTarget(185);
        await pause(200);
        await screenshot('control');
        i._modeButtons[1].emit('clicked', 1);
        check('heating only follows explicit button', c.snapshot.heater_mode === 1);
        c.snapshot = {...c.snapshot, setpoint_reached: false, charging: true}; c._changed();
        check('warming and charging use confirmed state', i._visualState().warming && i._visualState().charging);
        const settings = new Gio.Settings({schema_id: 'org.gnome.desktop.interface'});
        settings.set_boolean('enable-animations', false); await pause(100);
        check('reduced motion has no animation timer', !i._animationId);
        settings.set_boolean('enable-animations', true); await pause(100);
        check('animation preference restarts visible animation', Boolean(i._animationId));
        await pause(150); await screenshot('warming-charging');
        c.setHeaterMode(2);
        check('boost gets its own visual mode', i._visualState().boost && i._heaterStatus.text.includes('Boost'));
        await pause(150); await screenshot('boost');
        c.snapshot = {...c.snapshot, setpoint_reached: true, charging: false}; c._changed();
        check('target reached stops warming pulse', !i._visualState().warming);
        i.menu.close();
        check('closing panel stops animation source', i._animationId === 0);
        i.menu.open();
        i._modeButtons[0].emit('clicked', 1);
        i._selectTab('settings');
        await pause(150);
        check('native settings page opens', i._pages.settings.visible && !i._pages.control.visible);
        i._settingButtons.vibration.emit('clicked', 1);
        check('setting requires explicit button', c.snapshot.vibration === false);
        await screenshot('settings');
        i._selectTab('about'); await pause(150);
        await screenshot('about');
        i._selectTab('control');
        c.snapshot = {...c.snapshot, stale: true}; c._changed();
        check('stale battery immediately disappears', !i._barBattery.text.includes('%') && i._battery.text === '—');
        check('stale target is not presented as confirmed', i._temperature.text === '—');
        check('stale status stops all animations', !i._animationId && !i._visualState().heating && !i._visualState().charging);
        c.disconnectDevice();
        check('disconnect keeps heater unknown', c.snapshot.heater_mode === null);
        const keyboard = Clutter.get_default_backend().get_default_seat().create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
        keyboard.notify_keyval(GLib.get_monotonic_time(), Clutter.KEY_Escape, Clutter.KeyState.PRESSED);
        keyboard.notify_keyval(GLib.get_monotonic_time(), Clutter.KEY_Escape, Clutter.KeyState.RELEASED);
        await pause(200);
        check('Escape closes native panel', !i.menu.isOpen);
        ext.stateObj.disable();
        check('disable destroys service and timers', c._destroyed && !c._watchdog && !c._worker && !i._animationId);
        ext.stateObj.enable();
        check('enable creates one fresh indicator', ext.stateObj._indicator._client.state === 'disconnected' && !ext.stateObj._indicator._client._worker);
        console.log(`VEAZY_SHELL_OK ${count}`);
    }
    disable() {}
}
