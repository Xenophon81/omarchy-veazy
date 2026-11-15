// SPDX-License-Identifier: AGPL-3.0-only
import assert from 'node:assert/strict';
import test from 'node:test';
import {emptySnapshot, JsonLineDecoder, targetAllowed, validateCommand, validateDevices,
    validateSnapshot} from '../../platforms/gnome/model.js';

const encode = value => new TextEncoder().encode(value);
test('bounded JSONL handles split UTF-8 and multiple messages', () => {
    const parser = new JsonLineDecoder();
    const bytes = encode('{"name":"Véazy"}\n{"ok":true}\n');
    const split = bytes.indexOf(0xc3) + 1;
    assert.deepEqual(parser.push(bytes.slice(0, split)), []);
    assert.deepEqual(parser.push(bytes.slice(split)), [{name: 'Véazy'}, {ok: true}]);
    parser.finish();
});
test('malformed/oversized/truncated IPC cannot establish state', () => {
    assert.throws(() => new JsonLineDecoder().push(encode('a'.repeat(32769))));
    assert.throws(() => new JsonLineDecoder().push(new Uint8Array([0xff, 10])));
    assert.throws(() => new JsonLineDecoder().push(encode('[]\n')));
    const parser = new JsonLineDecoder(); parser.push(encode('{"version":1}'));
    assert.throws(() => parser.finish());
});
test('unknown fields, sentinel, corrupt numeric and boolean data fail closed', () => {
    assert.equal(emptySnapshot().heater_mode, null);
    assert.equal(emptySnapshot().stale, true);
    const valid = {...emptySnapshot(), stale: false, application_valid: true};
    for (const change of [{current_temperature_c: 3276.8}, {battery_percent: '82'}, {heater_mode: 4},
        {heater_mode: 1.5}, {charging: 1}, {boost_offset_c: 0}, {battery_percent: NaN}, {confirmation: 'success'}])
        assert.throws(() => validateSnapshot({...valid, ...change}));
    assert.equal(validateSnapshot({...valid, current_temperature_c: 185.2}).current_temperature_c, 185.2);
    assert.equal(validateSnapshot({confirmation: 'unknown'}).stale, true);
    assert.equal(validateSnapshot({...valid, __proto__: {polluted: true}}).polluted, undefined);
});
test('boost limits apply to all affected changes; unknown mode never authorizes heating', () => {
    assert.equal(targetAllowed(195, 15, 25, 2), true);
    assert.equal(targetAllowed(196, 15, 25, 2), false);
    assert.equal(targetAllowed(185, 15, 25, 3), true);
    assert.equal(targetAllowed(186, 15, 25, 3), false);
    assert.equal(targetAllowed(185, 15, 25, null), false);
    assert.equal(targetAllowed('185', 15, 25, 0), false);
});
test('command validation rejects coercion, extra fields and unsupported settings', () => {
    for (const [command, args] of [['set_target', {value: '185'}], ['set_target', {value: 185.1}],
        ['set_heater_mode', {mode: true}], ['scan', {auto: true}], ['set_setting', {name: 'eco', value: true}],
        ['set_setting', {name: 'vibration', value: 'false'}], ['connect', {device_id: 'x\n'}]])
        assert.throws(() => validateCommand(command, args));
    assert.deepEqual(validateCommand('set_heater_mode', {mode: 0}), {command: 'set_heater_mode', args: {mode: 0}});
});
test('device results are bounded and markup remains literal text', () => {
    const device = {id: 'AA:BB', name: '<b>Veazy</b>'};
    assert.deepEqual(validateDevices([device]), [device]);
    assert.throws(() => validateDevices([device, device]));
    assert.throws(() => validateDevices(Array(65).fill(device)));
    assert.throws(() => validateDevices([{id: '', name: 'VZ'}]));
});
