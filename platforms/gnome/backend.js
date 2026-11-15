// SPDX-License-Identifier: AGPL-3.0-only
// One shell-owned process; no automatic discovery, connection or heater writes.
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {emptySnapshot, integer, JsonLineDecoder, record, safeText, SETTINGS, STATES,
    targetAllowed, validateCommand, validateDevices, validateSnapshot} from './model.js';

export class VeazyClient {
    constructor({path, onChange}) {
        this._path = path;
        this._onChange = onChange;
        this.mode = 'mock';
        this._serial = 0;
        this._epoch = 0;
        this._requests = new Map();
        this._worker = null;
        this._destroyed = false;
        this.switchingMode = false;
        this._lastSnapshot = 0;
        this._mockTimer = 0;
        this._uncertainOffUsed = false;
        this._reset();
        this._watchdog = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
            if (this._destroyed) return GLib.SOURCE_REMOVE;
            if (this.mode === 'live' && this.state === 'ready' && !this.snapshot.stale && this.stale) this._changed();
            for (const request of this._requests.values()) {
                if (GLib.get_monotonic_time() - request.time > 45000000) {
                    this._fatal('Backend request timed out. Switch to Demo and back to Bluetooth to restart. No command is repeated.');
                    break;
                }
            }
            return GLib.SOURCE_CONTINUE;
        });
    }
    get pending() { return this._requests.size > 0; }
    get stale() {
        return this.snapshot.stale !== false || this.snapshot.session_uncertain === true || this.state !== 'ready'
            || (this.mode === 'live' && (!this._lastSnapshot || GLib.get_monotonic_time() - this._lastSnapshot > 2500000));
    }
    get canControl() {
        return this.state === 'ready' && !this.busy && !this.pending && !this.stale && this.snapshot.application_valid === true;
    }
    get canSetHeaterOff() {
        return this.state === 'ready' && !this.busy && !this.pending && !this._uncertainOffUsed && this.snapshot.application_valid === true;
    }
    _reset() {
        this.state = 'disconnected';
        this.snapshot = emptySnapshot();
        this.devices = [];
        this.selectedDeviceId = '';
        this.busy = false;
        this.error = '';
        this._lastSnapshot = 0;
        this._uncertainOffUsed = false;
        this._requests.clear();
        if (this._mockTimer) GLib.source_remove(this._mockTimer);
        this._mockTimer = 0;
    }
    _changed() { if (!this._destroyed) this._onChange?.(); }
    _fail(error) { this.error = safeText(error instanceof Error ? error.message : error); this._changed(); return false; }
    setMode(mode) {
        if (!['mock', 'live'].includes(mode)) return this._fail('Unknown operating mode');
        if (this._destroyed || this.switchingMode) return false;
        if (mode === this.mode) return true;
        ++this._epoch;
        this.mode = mode;
        this._reset();
        if (this._worker) {
            this.switchingMode = true;
            this._stop(this._worker);
            // wait_async is the only place a replacement can start.
        } else if (mode === 'live') this._start();
        this._changed();
        return true;
    }
    selectDevice(id) {
        if (this.busy || this.pending || this.state === 'ready' || !this.devices.some(d => d.id === id)) return false;
        this.selectedDeviceId = id;
        this._changed();
        return true;
    }
    scan() {
        if (this.busy || this.pending || this.switchingMode || !['disconnected', 'error'].includes(this.state)) return false;
        this.error = '';
        this.devices = [];
        this.selectedDeviceId = '';
        if (this.mode === 'live') return this._send('scan', {});
        this.state = 'scanning';
        this.busy = true;
        this._mockTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 250, () => {
            this._mockTimer = 0;
            this.devices = [{id: 'mock-veazy', name: 'S&B VZ · DEMO'}];
            this.state = 'disconnected';
            this.busy = false;
            this._changed();
            return GLib.SOURCE_REMOVE;
        });
        this._changed();
        return true;
    }
    connectDevice() {
        if (this.busy || this.pending || !this.selectedDeviceId || this.state === 'ready') return false;
        if (this.mode === 'live') return this._send('connect', {device_id: this.selectedDeviceId});
        if (this.selectedDeviceId !== 'mock-veazy') return false;
        this.snapshot = {...emptySnapshot(), target_temperature_c: 185, boost_offset_c: 15, superboost_offset_c: 25,
            heater_mode: 0, battery_percent: 82, charging: false, setpoint_reached: false, firmware_version: 'DEMO',
            serial_number: 'DEMO-VEAZY', brightness: 9, vibration: true, charge_current_optimization: false,
            charge_voltage_limit: false, boost_visualization: true, boost_timeout_disabled: false, permanent_bluetooth: false,
            heater_runtime_minutes: 0, charging_time_minutes: 0, application_valid: true, stale: false, confirmation: 'confirmed'};
        this.state = 'ready';
        this.error = '';
        this._changed();
        return true;
    }
    disconnectDevice() {
        if (this.mode === 'live') return this._send('disconnect', {}, true);
        this._reset(); this._changed(); return true;
    }
    _patch(change) { this.snapshot = {...this.snapshot, ...change}; this.error = ''; this._changed(); return true; }
    setTarget(value) {
        if (!this.canControl) return false;
        const s = this.snapshot;
        if (!targetAllowed(value, s.boost_offset_c, s.superboost_offset_c, s.heater_mode)) return this._fail('The effective target must stay at or below 210 °C');
        return this.mode === 'live' ? this._send('set_target', {value}) : this._patch({target_temperature_c: value, setpoint_reached: false});
    }
    setHeaterMode(mode) {
        if (!(mode === 0 ? this.canSetHeaterOff : this.canControl) || !integer(mode, 0, 3)) return false;
        const s = this.snapshot;
        if (mode !== 0 && (!integer(s.heater_mode, 0, 3) || !targetAllowed(s.target_temperature_c, s.boost_offset_c, s.superboost_offset_c, mode)))
            return this._fail('A known heater mode and effective target at or below 210 °C are required');
        if (mode === 0 && this.stale) this._uncertainOffUsed = true;
        return this.mode === 'live' ? this._send('set_heater_mode', {mode}) : this._patch({heater_mode: mode, setpoint_reached: false});
    }
    setOffset(kind, value) {
        if (!this.canControl || !['boost', 'superboost'].includes(kind) || !integer(value, 1, 99)) return false;
        const s = this.snapshot;
        if (!targetAllowed(s.target_temperature_c, kind === 'boost' ? value : s.boost_offset_c,
            kind === 'superboost' ? value : s.superboost_offset_c, s.heater_mode)) return this._fail('The effective target must stay at or below 210 °C');
        return this.mode === 'live' ? this._send('set_offset', {kind, value}) : this._patch({[`${kind}_offset_c`]: value});
    }
    setSetting(name, value) {
        if (!this.canControl || this.snapshot[name] === null || this.snapshot[name] === undefined) return false;
        try { validateCommand('set_setting', {name, value}); } catch (error) { return this._fail(error); }
        return this.mode === 'live' ? this._send('set_setting', {name, value}) : this._patch({[name]: value});
    }
    diagnose() {
        if (!this.canControl) return false;
        return this.mode === 'live' ? this._send('diagnose', {}) : this._patch({analysis_code: 0, analysis_category: 0});
    }
    findDevice() {
        if (!this.canControl) return false;
        return this.mode === 'live' ? this._send('find_device', {}) : true;
    }
    _start() {
        if (this._worker || this._destroyed || this.mode !== 'live') return;
        const session = `${++this._epoch}-${GLib.uuid_string_random()}`;
        try {
            const launcher = new Gio.SubprocessLauncher({flags: Gio.SubprocessFlags.STDIN_PIPE | Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE});
            launcher.setenv('OMARCHY_VEAZY_WORKER_SESSION', session, true);
            const process = launcher.spawnv(['/bin/bash', `${this._path}/scripts/run-backend`]);
            const worker = {process, session, decoder: new JsonLineDecoder(), cancel: new Gio.Cancellable(),
                stopped: false, epoch: this._epoch, stderrBytes: 0};
            this._worker = worker;
            this._read(worker, process.get_stdout_pipe(), false);
            this._read(worker, process.get_stderr_pipe(), true);
            process.wait_async(null, (proc, result) => {
                try { proc.wait_finish(result); } catch (_) { /* already reaped */ }
                worker.cancel.cancel();
                if (this._worker !== worker) return;
                this._worker = null;
                this.switchingMode = false;
                if (worker.killTimer) GLib.source_remove(worker.killTimer);
                if (this._destroyed) return;
                if (!worker.stopped) {
                    this._requests.clear(); this.snapshot = emptySnapshot(); this.state = 'error'; this.busy = false;
                    this.error ||= 'Bluetooth backend stopped. Run scripts/setup-backend, then switch Demo → Bluetooth to retry.';
                } else if (this.mode === 'live' && worker.epoch !== this._epoch) this._start();
                this._changed();
            });
        } catch (error) { this.state = 'error'; this._fail(error); }
    }
    _read(worker, stream, stderr) {
        stream.read_bytes_async(4096, GLib.PRIORITY_DEFAULT, worker.cancel, (source, result) => {
            try {
                const bytes = source.read_bytes_finish(result).get_data();
                if (!bytes.length) {
                    if (!stderr && !worker.stopped) {
                        worker.decoder.finish();
                        this._fatal('Bluetooth backend closed its response stream. Switch Demo → Bluetooth to restart.');
                    }
                    return;
                }
                if (stderr) {
                    // Bounded logs; do not buffer stderr as an unbounded line.
                    if (worker.stderrBytes < 8192) console.warn(`Veazy backend: ${safeText(new TextDecoder().decode(bytes), 2048)}`);
                    worker.stderrBytes += bytes.length;
                } else if (!worker.stopped && !this._destroyed && this._worker === worker && worker.epoch === this._epoch) {
                    for (const message of worker.decoder.push(bytes)) this._receive(worker, message);
                }
                if (!worker.cancel.is_cancelled()) this._read(worker, stream, stderr);
            } catch (error) {
                if (!worker.stopped && !this._destroyed) this._fatal(error);
            }
        });
    }
    _receive(worker, message) {
        if (worker.stopped || message.session !== worker.session) return;
        if (message.version !== 1) throw Error('Unsupported backend protocol');
        if (typeof message.id === 'string') {
            if (!this._requests.has(message.id)) return;
            if (typeof message.ok !== 'boolean') throw Error('Invalid backend result');
            this._requests.delete(message.id);
            if (!message.ok) {
                if (!record(message.error) || typeof message.error.message !== 'string') throw Error('Invalid backend error');
                this.error = safeText(message.error.message);
            } else if (message.result?.confirmation === 'unknown') this.error = safeText(message.result.message || 'Outcome unconfirmed; reconnect to read device state');
        } else if (message.event === 'state') {
            if (!record(message.data) || !STATES.includes(message.data.state) || typeof message.data.busy !== 'boolean') throw Error('Invalid backend state');
            this.state = message.data.state;
            this.busy = message.data.busy;
            if (this.state === 'connecting') this._uncertainOffUsed = false;
            if (this.state === 'disconnected' || this.state === 'error') { this.snapshot = emptySnapshot(); this._lastSnapshot = 0; }
        } else if (message.event === 'snapshot') {
            this.snapshot = validateSnapshot(message.data);
            this._lastSnapshot = GLib.get_monotonic_time();
        } else if (message.event === 'devices') {
            if (!record(message.data)) throw Error('Invalid backend discovery');
            this.devices = validateDevices(message.data.devices);
        } else if (message.event === 'error') {
            if (!record(message.data) || typeof message.data.message !== 'string' || message.data.message.length > 1024) throw Error('Invalid backend error');
            this.error = safeText(message.data.message);
        } else throw Error('Unknown backend event');
        this._changed();
    }
    _send(command, args, interrupt = false) {
        const worker = this._worker;
        if (this.mode !== 'live' || !worker || worker.stopped || this._destroyed) return this._fail('Bluetooth backend unavailable. Run scripts/setup-backend and switch Demo → Bluetooth.');
        if (this.pending && !interrupt) return false;
        try { validateCommand(command, args); } catch (error) { return this._fail(error); }
        const id = `${this._epoch}:${++this._serial}`;
        const bytes = new TextEncoder().encode(`${JSON.stringify({version: 1, id, command, args})}\n`);
        if (bytes.length > 4096) return this._fail('Command is too long');
        this._requests.set(id, {time: GLib.get_monotonic_time()});
        this.error = '';
        // Every request is < 4 KiB. Only one output write is outstanding; an
        // interrupt waits for that short write before sending disconnect.
        worker.writes = (worker.writes || Promise.resolve()).then(() => new Promise((resolve, reject) => {
            if (worker.stopped || worker.epoch !== this._epoch || this._destroyed) { resolve(); return; }
            worker.process.get_stdin_pipe().write_all_async(bytes, GLib.PRIORITY_DEFAULT, worker.cancel, (stream, result) => {
                try { stream.write_all_finish(result); resolve(); } catch (error) { reject(error); }
            });
        })).catch(error => { if (!worker.stopped && !this._destroyed) this._fatal(error); });
        this._changed();
        return true;
    }
    _stop(worker) {
        if (worker.stopped) return;
        worker.stopped = true;
        // stdin EOF cancels queued commands in Python. SIGTERM ends outstanding
        // operations; force-exit is a bounded fallback, never a retry.
        try { worker.process.get_stdin_pipe().close(null); } catch (_) { /* closed */ }
        try { worker.process.send_signal(15); } catch (_) { /* exited */ }
        worker.killTimer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 2, () => {
            worker.killTimer = 0;
            try { worker.process.force_exit(); } catch (_) { /* exited */ }
            return GLib.SOURCE_REMOVE;
        });
    }
    _fatal(error) {
        this._requests.clear();
        this.snapshot = emptySnapshot();
        this.state = 'error';
        this.busy = false;
        if (this._worker) this._stop(this._worker);
        this._fail(error);
    }
    destroy() {
        this._destroyed = true;
        ++this._epoch;
        this._onChange = null;
        this._requests.clear();
        if (this._watchdog) GLib.source_remove(this._watchdog);
        if (this._mockTimer) GLib.source_remove(this._mockTimer);
        this._watchdog = this._mockTimer = 0;
        if (this._worker) this._stop(this._worker);
    }
}
