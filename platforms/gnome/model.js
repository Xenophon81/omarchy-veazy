// SPDX-License-Identifier: AGPL-3.0-only
// Pure data validation; independent of GNOME and Bluetooth.
export const MAX_LINE_BYTES = 32768;
export const STATES = ['disconnected', 'scanning', 'connecting', 'initializing', 'ready', 'disconnecting', 'error'];
export const SETTINGS = ['vibration', 'charge_current_optimization', 'charge_voltage_limit',
    'boost_visualization', 'boost_timeout_disabled', 'permanent_bluetooth'];
const RANGES = {
    current_temperature_c: [0, 300], target_temperature_c: [40, 210],
    boost_offset_c: [1, 99], superboost_offset_c: [1, 99], heater_mode: [0, 3], battery_percent: [0, 100],
    brightness: [1, 9], heater_runtime_minutes: [0, 16777215], charging_time_minutes: [0, 16777215],
    analysis_code: [0, 255], analysis_category: [0, 255], effective_target_temperature_c: [40, 309], status_age_ms: [0, 2147483647],
};
const BOOLEANS = [...SETTINGS, 'charging', 'setpoint_reached', 'application_valid', 'stale', 'session_uncertain'];
export const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
export const integer = (value, low, high) => Number.isInteger(value) && value >= low && value <= high;
export function safeText(value, limit = 1024) {
    return String(value ?? '').replace(/[\x00-\x1f\x7f]/g, ' ').slice(0, limit);
}
export function emptySnapshot() {
    const result = Object.fromEntries([...Object.keys(RANGES), ...BOOLEANS,
        'firmware_version', 'serial_number', 'pending_command'].map(key => [key, null]));
    return {...result, stale: true, session_uncertain: false, confirmation: 'unknown'};
}
export function validateSnapshot(data) {
    if (!record(data)) throw Error('Invalid backend snapshot');
    const next = emptySnapshot();
    for (const [key, range] of Object.entries(RANGES)) {
        const value = data[key];
        if (value === undefined || value === null) continue;
        if (typeof value !== 'number' || !Number.isFinite(value) || value < range[0] || value > range[1]
            || (!['current_temperature_c', 'target_temperature_c', 'effective_target_temperature_c'].includes(key) && !Number.isInteger(value)))
            throw Error(`Invalid device field: ${key}`);
        next[key] = value;
    }
    for (const key of BOOLEANS) {
        const value = data[key];
        if (value === undefined || value === null) continue;
        if (typeof value !== 'boolean') throw Error(`Invalid boolean: ${key}`);
        next[key] = value;
    }
    for (const key of ['firmware_version', 'serial_number', 'pending_command']) {
        const value = data[key];
        if (value === undefined || value === null) continue;
        if (typeof value !== 'string' || value.length > 128) throw Error(`Invalid text: ${key}`);
        next[key] = safeText(value, 128);
    }
    if (!['confirmed', 'pending', 'unknown'].includes(data.confirmation)) throw Error('Invalid confirmation state');
    next.confirmation = data.confirmation;
    // Never let a partial snapshot establish freshness or application authority.
    next.stale = data.stale !== false;
    next.session_uncertain = data.session_uncertain === true;
    return next;
}
export function validateDevices(devices) {
    if (!Array.isArray(devices) || devices.length > 64) throw Error('Invalid discovery results');
    const seen = new Set();
    return devices.map(device => {
        if (!record(device) || typeof device.id !== 'string' || device.id.length < 1 || device.id.length > 128
            || /[\x00-\x1f\x7f]/.test(device.id) || typeof device.name !== 'string' || device.name.length > 128 || seen.has(device.id))
            throw Error('Invalid discovery entry');
        seen.add(device.id);
        return {id: device.id, name: safeText(device.name, 128)};
    });
}
export function targetAllowed(base, boost, superboost, mode) {
    return integer(base, 40, 210) && integer(boost, 1, 99) && integer(superboost, 1, 99)
        && integer(mode, 0, 3) && base + (mode === 2 ? boost : mode === 3 ? superboost : 0) <= 210;
}
export function validateCommand(command, args) {
    const fields = {scan: [], connect: ['device_id'], disconnect: [], status: [], set_target: ['value'],
        set_heater_mode: ['mode'], set_offset: ['kind', 'value'], set_setting: ['name', 'value'], diagnose: [], find_device: []};
    if (!Object.hasOwn(fields, command) || !record(args) || Object.keys(args).sort().join('|') !== fields[command].slice().sort().join('|'))
        throw Error('Invalid command arguments');
    if (command === 'connect' && (typeof args.device_id !== 'string' || args.device_id.length < 1 || args.device_id.length > 128 || /[\x00-\x1f\x7f]/.test(args.device_id)))
        throw Error('Invalid device selection');
    if (command === 'set_target' && !integer(args.value, 40, 210)) throw Error('Target must be a whole number from 40 to 210 °C');
    if (command === 'set_heater_mode' && !integer(args.mode, 0, 3)) throw Error('Invalid heater mode');
    if (command === 'set_offset' && (!['boost', 'superboost'].includes(args.kind) || !integer(args.value, 1, 99))) throw Error('Invalid boost offset');
    if (command === 'set_setting' && !(args.name === 'brightness' ? integer(args.value, 1, 9) : SETTINGS.includes(args.name) && typeof args.value === 'boolean'))
        throw Error('Invalid setting');
    return {command, args};
}
export class JsonLineDecoder {
    constructor() { this._bytes = []; }
    push(chunk) {
        const lines = [];
        for (const byte of chunk) {
            if (byte === 10) {
                if (this._bytes.length) {
                    const line = new TextDecoder('utf-8', {fatal: true}).decode(new Uint8Array(this._bytes));
                    this._bytes = [];
                    const value = JSON.parse(line);
                    if (!record(value)) throw Error('Invalid backend message');
                    lines.push(value);
                }
            } else {
                if (this._bytes.length >= MAX_LINE_BYTES) throw Error('Backend line exceeds 32768 bytes');
                this._bytes.push(byte);
            }
        }
        return lines;
    }
    finish() { if (this._bytes.length) throw Error('Backend closed mid-message'); }
}
