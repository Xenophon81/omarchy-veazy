// SPDX-License-Identifier: AGPL-3.0-only
// Original native St UI; visual direction: Reactive Volcano App by Tristan Teufel.
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Pango from 'gi://Pango';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {VeazyClient} from './backend.js';
import {translator} from './i18n.js';

const CENTER = Clutter.ActorAlign.CENTER;
function label(text = '', style = '', props = {}) {
    // All dynamic text uses Clutter.Text's plain text API. Never set_markup().
    return new St.Label({text: String(text), style_class: style, y_align: CENTER, ...props});
}
function wrapped(text, style = 'veazy-note') {
    const actor = label(text, style, {x_expand: true});
    actor.clutter_text.line_wrap = true;
    actor.clutter_text.line_wrap_mode = Pango.WrapMode.WORD_CHAR;
    actor.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
    return actor;
}
function box(vertical = false, style = '', props = {}) {
    return new St.BoxLayout({vertical, style_class: style, ...props});
}
function button(text, action, style = '') {
    const actor = new St.Button({style_class: `veazy-button ${style}`, can_focus: true,
        reactive: true, track_hover: true, accessible_name: text, label: text});
    actor.connect('clicked', action);
    return actor;
}
function sensitive(actor, enabled) {
    actor.reactive = Boolean(enabled);
    actor.can_focus = Boolean(enabled);
    if (enabled) actor.remove_style_pseudo_class('disabled');
    else actor.add_style_pseudo_class('disabled');
}
function active(actor, enabled) {
    if (enabled) actor.add_style_pseudo_class('checked');
    else actor.remove_style_pseudo_class('checked');
}

const VeazyIndicator = GObject.registerClass(class VeazyIndicator extends PanelMenu.Button {
    _init(extension) {
        super._init(0.0, 'Veazy', false);
        this._extension = extension;
        this._t = translator();
        this._draftTarget = null;
        this._dirtyTarget = false;
        this._offsetDrafts = {};
        this._devicesKey = '';
        this._tab = 'control';
        this._animationId = 0;
        this._settings = St.Settings.get();
        this._animationSignal = this._settings.connect('notify::enable-animations', () => this._syncAnimation());
        const icon = new Gio.FileIcon({file: Gio.File.new_for_path(`${extension.path}/assets/veazy-symbolic.svg`)});
        const bar = box(false, 'panel-status-menu-box');
        bar.add_child(new St.Icon({gicon: icon, style_class: 'system-status-icon'}));
        this._barBattery = label('', 'veazy-bar-battery');
        bar.add_child(this._barBattery);
        this.add_child(bar);
        this.menu.actor.add_style_class_name('veazy-menu');
        this._build(icon);
        this._client = new VeazyClient({path: extension.path, onChange: () => this._render()});
        this._menuSignal = this.menu.connect('open-state-changed', (_menu, open) => {
            if (open) {
                const monitor = Main.layoutManager.primaryMonitor;
                // CSS pixels; scale factor is applied by St itself.
                this._scroll.set_style(`max-height: ${Math.max(240, Math.floor(monitor.height / St.ThemeContext.get_for_stage(global.stage).scale_factor) - 100)}px;`);
                this._render();
            }
            this._syncAnimation();
        });
        this._render();
    }

    _build(icon) {
        const t = this._t;
        const section = new PopupMenu.PopupMenuSection();
        this.menu.addMenuItem(section);
        this._scroll = new St.ScrollView({style_class: 'veazy-scroll', overlay_scrollbars: true,
            hscrollbar_policy: St.PolicyType.NEVER, vscrollbar_policy: St.PolicyType.AUTOMATIC});
        section.box.add_child(this._scroll);
        this._body = box(true, 'veazy-body');
        this._scroll.set_child(this._body);

        const header = box(false, 'veazy-header');
        const logo = new St.Bin({style_class: 'veazy-logo', child: new St.Icon({gicon: icon, icon_size: 25})});
        header.add_child(logo);
        const title = box(true, 'veazy-title-group', {x_expand: true});
        title.add_child(label('Veazy', 'veazy-title'));
        this._connectionLabel = label('', 'veazy-subtitle');
        title.add_child(this._connectionLabel);
        header.add_child(title);
        this._battery = label('—', 'veazy-battery');
        const batteryBox = box(true, 'veazy-battery-group');
        batteryBox.add_child(this._battery);
        this._chargeTrack = new St.DrawingArea({height: 5, x_expand: true});
        this._chargeTrack.connect('repaint', area => this._paintCharge(area));
        batteryBox.add_child(this._chargeTrack);
        header.add_child(batteryBox);
        this._body.add_child(header);


        this._errorBox = box(true, 'veazy-error');
        this._errorLabel = wrapped('');
        this._errorBox.add_child(this._errorLabel);
        this._body.add_child(this._errorBox);
        this._pendingLabel = wrapped('', 'veazy-status-notice');
        this._body.add_child(this._pendingLabel);

        this._connectionBox = box(true, 'veazy-card veazy-connection-card');
        this._connectionBox.add_child(wrapped(t('nearby')));
        this._scanButton = button(t('scan'), () => this._client.scan(), 'veazy-primary');
        this._connectionBox.add_child(this._scanButton);
        this._deviceList = box(true, 'veazy-device-list');
        this._connectionBox.add_child(this._deviceList);
        this._body.add_child(this._connectionBox);
        this._disconnectButton = button(t('disconnect'), () => this._client.disconnectDevice(), 'veazy-disconnect');
        this._body.add_child(this._disconnectButton);

        const tabs = box(false, 'veazy-tabs');
        this._tabs = {};
        this._pages = {};
        for (const key of ['control', 'settings', 'about']) {
            const tab = button(t(key), () => this._selectTab(key), 'veazy-tab');
            tab.x_expand = true;
            tabs.add_child(tab);
            this._tabs[key] = tab;
        }
        this._body.add_child(tabs);
        for (const key of ['control', 'settings', 'about']) {
            const page = box(true, `veazy-page veazy-${key}`);
            this._pages[key] = page;
            this._body.add_child(page);
        }
        this._buildControl();
        this._buildSettings();
        this._buildAbout();
        this._selectTab('control');
    }

    _buildControl() {
        const t = this._t;
        const page = this._pages.control;
        const gauge = new St.Widget({layout_manager: new Clutter.BinLayout(), style_class: 'veazy-gauge',
            x_expand: true, height: 225, accessible_name: t('target')});
        this._ring = new St.DrawingArea({x_expand: true, y_expand: true});
        this._ring.connect('repaint', area => this._paintRing(area));
        gauge.add_child(this._ring);
        const gaugeText = box(true, 'veazy-gauge-text', {x_align: CENTER, y_align: CENTER, width: 245});
        const caption = label(t('target'), 'veazy-eyebrow veazy-gauge-caption', {x_align: CENTER});
        caption.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
        caption.clutter_text.set_line_alignment(Pango.Alignment.CENTER);
        gaugeText.add_child(caption);
        this._temperature = label('—', 'veazy-temperature', {x_align: CENTER});
        gaugeText.add_child(this._temperature);
        this._heaterStatus = label(t('unknown'), 'veazy-heater-status', {x_align: CENTER});
        gaugeText.add_child(this._heaterStatus);
        gauge.add_child(gaugeText);
        page.add_child(gauge);
        const measurement = box(false, 'veazy-measurement');
        measurement.add_child(label(t('measured'), 'veazy-note', {x_expand: true}));
        this._measured = label(t('unavailable'), 'veazy-measured-value');
        measurement.add_child(this._measured);
        page.add_child(measurement);

        page.add_child(label(t('heaterMode'), 'veazy-eyebrow'));
        const modes = box(false, 'veazy-segment veazy-modes');
        this._modeButtons = [];
        for (const [mode, key] of ['heaterOff', 'heaterOn', 'boost', 'superboost'].entries()) {
            const actor = button(t(key), () => this._client.setHeaterMode(mode), 'veazy-mode-button');
            actor.x_expand = true;
            modes.add_child(actor);
            this._modeButtons.push(actor);
        }
        page.add_child(modes);

        const editor = box(true, 'veazy-card veazy-target-card');
        const editorTitle = box(false, 'veazy-editor-heading');
        editorTitle.add_child(label(t('base'), 'veazy-eyebrow', {x_expand: true}));
        this._draftLabel = label('', 'veazy-draft');
        editorTitle.add_child(this._draftLabel);
        editor.add_child(editorTitle);
        const targetRow = box(false, 'veazy-target-row');
        this._minus = button('−', () => this._changeTarget(-1), 'veazy-step');
        this._minus.accessible_name = `${t('decrease')} ${t('base')}`;
        targetRow.add_child(this._minus);
        this._targetEntry = new St.Entry({text: '', hint_text: '—', style_class: 'veazy-target-entry',
            can_focus: true, x_expand: false, accessible_name: t('base'), input_purpose: Clutter.InputContentPurpose.DIGITS});
        this._targetEntry.clutter_text.set_max_length(3);
        this._targetEntry.clutter_text.set_line_alignment(Pango.Alignment.CENTER);
        this._targetEntry.clutter_text.connect('text-changed', () => {
            if (this._updatingEntry) return;
            const text = this._targetEntry.get_text();
            this._draftTarget = /^\d{2,3}$/.test(text) ? Number(text) : null;
            this._dirtyTarget = true;
            this._updateEditor();
        });
        const targetValue = box(false, 'veazy-target-value', {x_expand: true, x_align: CENTER});
        targetValue.add_child(this._targetEntry);
        targetValue.add_child(label('°C', 'veazy-unit'));
        targetRow.add_child(targetValue);
        this._plus = button('+', () => this._changeTarget(1), 'veazy-step veazy-step-plus');
        this._plus.accessible_name = `${t('increase')} ${t('base')}`;
        targetRow.add_child(this._plus);
        editor.add_child(targetRow);
        this._apply = button(t('apply'), () => {
            if (this._client.setTarget(this._draftTarget)) {
                this._dirtyTarget = false;
                this._render();
            }
        }, 'veazy-primary veazy-apply');
        editor.add_child(this._apply);
        page.add_child(editor);
        page.add_child(wrapped(t('measureNotice')));
    }

    _buildSettings() {
        const t = this._t;
        const page = this._pages.settings;
        page.add_child(label(t('connectionMode'), 'veazy-eyebrow'));
        const modeRow = box(false, 'veazy-segment');
        this._demoButton = button(t('demo'), () => this._client.setMode('mock'), 'veazy-segment-button');
        this._liveButton = button(t('bluetooth'), () => this._client.setMode('live'), 'veazy-segment-button');
        this._demoButton.x_expand = this._liveButton.x_expand = true;
        modeRow.add_child(this._demoButton);
        modeRow.add_child(this._liveButton);
        page.add_child(modeRow);
        this._modeNotice = wrapped(t('demoNotice'), 'veazy-mode-notice');
        page.add_child(this._modeNotice);


        page.add_child(label(t('deviceSettings'), 'veazy-eyebrow'));
        page.add_child(wrapped(t('settingsNotice')));
        this._settingButtons = {};
        for (const key of ['vibration', 'charge_current_optimization', 'charge_voltage_limit',
            'boost_visualization', 'boost_timeout_disabled', 'permanent_bluetooth']) {
            const row = box(false, 'veazy-setting-row');
            row.add_child(wrapped(t(key), 'veazy-setting-name'));
            const actor = button('—', () => this._client.setSetting(key, !this._client.snapshot[key]), 'veazy-switch');
            row.add_child(actor);
            this._settingButtons[key] = actor;
            page.add_child(row);
        }
        this._valueEditors = {};
        for (const [key, min, max] of [['boost', 1, 99], ['superboost', 1, 99], ['brightness', 1, 9]]) {
            const row = box(true, 'veazy-card veazy-small-editor');
            row.add_child(label(t(key === 'boost' ? 'boostOffset' : key === 'superboost' ? 'superOffset' : 'brightness'), 'veazy-setting-name'));
            const controls = box(false, 'veazy-small-controls');
            const change = delta => {
                const old = this._offsetDrafts[key] ?? this._client.snapshot[key === 'brightness' ? key : `${key}_offset_c`];
                if (typeof old !== 'number') return;
                this._offsetDrafts[key] = Math.max(min, Math.min(max, old + delta));
                this._render();
            };
            const minus = button('−', () => change(-1), 'veazy-small-step');
            const value = label('—', 'veazy-offset-value', {x_expand: true, x_align: CENTER});
            const plus = button('+', () => change(1), 'veazy-small-step');
            const apply = button(t('apply'), () => {
                const v = this._offsetDrafts[key];
                const sent = key === 'brightness' ? this._client.setSetting(key, v) : this._client.setOffset(key, v);
                if (sent) delete this._offsetDrafts[key];
                this._render();
            }, 'veazy-small-apply');
            for (const actor of [minus, value, plus, apply]) controls.add_child(actor);
            row.add_child(controls);
            page.add_child(row);
            this._valueEditors[key] = {minus, plus, value, apply};
        }
        page.add_child(wrapped(t('limitNotice')));
        this._findButton = button(t('find'), () => this._client.findDevice());
        page.add_child(this._findButton);
    }

    _buildAbout() {
        const t = this._t;
        const page = this._pages.about;
        page.add_child(label(t('details'), 'veazy-eyebrow'));
        this._detailValues = {};
        for (const key of ['firmware_version', 'serial_number', 'heater_runtime_minutes',
            'charging_time_minutes', 'analysis_code', 'analysis_category']) {
            const row = box(false, 'veazy-detail-row');
            row.add_child(label(t(key), 'veazy-note', {x_expand: true}));
            const value = label('—', 'veazy-detail-value');
            row.add_child(value);
            page.add_child(row);
            this._detailValues[key] = value;
        }
        this._diagnoseButton = button(t('diagnose'), () => this._client.diagnose());
        page.add_child(this._diagnoseButton);
        const credits = box(true, 'veazy-card veazy-credits');
        credits.add_child(label(t('native'), 'veazy-credits-title'));
        credits.add_child(label(`Veazy ${this._extension.metadata['version-name'] ?? this._extension.metadata.version} · GNOME Shell 46`, 'veazy-note'));
        credits.add_child(button(t('updates'), () => {
            Gio.AppInfo.launch_default_for_uri('https://github.com/Xenophon81/omarchy-veazy/releases/latest', null);
        }));
        credits.add_child(wrapped(t('updateNotice')));
        credits.add_child(wrapped(t('aboutText')));
        credits.add_child(label(t('credits'), 'veazy-eyebrow'));
        credits.add_child(wrapped(t('attribution'), 'veazy-credit-link'));
        credits.add_child(button('github.com/firsttris/reactive-volcano-app', () => {
            Gio.AppInfo.launch_default_for_uri('https://github.com/firsttris/reactive-volcano-app', null);
        }, 'veazy-source-link'));
        credits.add_child(wrapped(t('reference')));
        credits.add_child(wrapped(t('license')));
        page.add_child(credits);
        page.add_child(wrapped(t('hardware')));
    }

    _selectTab(key) {
        this._tab = key;
        for (const name of Object.keys(this._tabs)) {
            this._pages[name].visible = name === key;
            active(this._tabs[name], name === key);
        }
        this._syncAnimation();
    }

    _changeTarget(delta) {
        if (!this._client.canControl) return;
        const value = this._draftTarget ?? this._client.snapshot.target_temperature_c;
        if (typeof value !== 'number') return;
        this._draftTarget = Math.max(40, Math.min(210, Math.round(value) + delta));
        this._dirtyTarget = true;
        this._setTargetText();
        this._updateEditor();
    }

    _setTargetText() {
        this._updatingEntry = true;
        this._targetEntry.set_text(typeof this._draftTarget === 'number' ? String(this._draftTarget) : '');
        this._updatingEntry = false;
    }

    _updateEditor() {
        if (!this._client) return;
        const s = this._client.snapshot;
        const value = this._draftTarget;
        const offset = s.heater_mode === 2 ? s.boost_offset_c : s.heater_mode === 3 ? s.superboost_offset_c : 0;
        const allowed = this._client.canControl && Number.isInteger(s.heater_mode) && typeof offset === 'number'
            && Number.isInteger(value) && value >= 40 && value <= 210 && value + offset <= 210;
        sensitive(this._apply, allowed && this._dirtyTarget);
        this._draftLabel.text = this._dirtyTarget ? this._t('draft') : '';
        sensitive(this._minus, this._client.canControl && value > 40);
        sensitive(this._plus, this._client.canControl && value < 210);
        this._targetEntry.reactive = this._targetEntry.can_focus = this._client.canControl;
    }

    _visualState() {
        const c = this._client;
        const s = c?.snapshot ?? {};
        const fresh = c?.state === 'ready' && !c.stale;
        const heating = fresh && s.heater_mode > 0;
        // Heater-off is not evidence that the device has cooled down.
        const measured = fresh && typeof s.current_temperature_c === 'number';
        const color = !fresh ? [0.4, 0.4, 0.45]
            : s.heater_mode === 3 ? [0.96, 0.30, 0.65]
            : s.heater_mode === 2 ? [0.65, 0.40, 1]
            : heating || (measured && s.current_temperature_c >= 40) ? [0.98, 0.45, 0.09]
            : measured ? [0.22, 0.72, 0.95] : [0.55, 0.55, 0.60];
        return {fresh, heating, color, charging: fresh && s.charging === true,
            warming: heating && s.setpoint_reached === false,
            boost: heating && s.heater_mode >= 2};
    }

    _syncAnimation() {
        const v = this._visualState();
        const animate = this.menu.isOpen && this._settings.enable_animations &&
            (v.charging || (this._tab === 'control' && (v.warming || v.boost)));
        if (!animate && this._animationId) {
            GLib.Source.remove(this._animationId);
            this._animationId = 0;
        } else if (animate && !this._animationId) {
            this._animationId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 50, () => {
                this._ring.queue_repaint();
                this._chargeTrack.queue_repaint();
                return GLib.SOURCE_CONTINUE;
            });
        }
        this._ring.queue_repaint();
        this._chargeTrack.queue_repaint();
    }

    _paintCharge(area) {
        const [w, h] = area.get_surface_size();
        const cr = area.get_context();
        const v = this._visualState();
        cr.setSourceRGBA(0.16, 0.16, 0.19, 1);
        cr.rectangle(0, 0, w, h); cr.fill();
        if (v.charging) {
            const phase = this._animationId ? (GLib.get_monotonic_time() / 2000000) % 1 : 0.5;
            cr.setSourceRGBA(0.20, 0.83, 0.60, 1);
            for (const shift of [-1, 0, 1]) {
                cr.rectangle((phase + shift) * w, 0, w * 0.35, h); cr.fill();
            }
        }
        cr.$dispose();
    }

    _paintRing(area) {
        const [width, height] = area.get_surface_size();
        const cr = area.get_context();
        const radius = Math.min(width / 2 - 18, height / 2 - 14);
        const cx = width / 2;
        const cy = height / 2 + 4;
        const start = Math.PI * 0.75;
        const length = Math.PI * 1.5;
        cr.setLineCap(1);
        const arc = (lineWidth, color, alpha, from, to, r = radius) => {
            cr.setLineWidth(lineWidth);
            cr.setSourceRGBA(...color, alpha);
            cr.arc(cx, cy, r, from, to); cr.stroke();
        };
        arc(7, [0.145, 0.145, 0.165], 1, start, start + length);
        const s = this._client?.snapshot;
        const v = this._visualState();
        const offset = s?.heater_mode === 2 ? s.boost_offset_c : s?.heater_mode === 3 ? s.superboost_offset_c : 0;
        const target = v.fresh && Number.isInteger(s?.heater_mode) && typeof s?.target_temperature_c === 'number' && typeof offset === 'number' ? s.target_temperature_c + offset : null;
        if (target !== null) {
            const end = start + length * Math.max(0.01, Math.min(1, (target - 40) / 170));
            const seconds = this._animationId ? GLib.get_monotonic_time() / 1000000 : 0;
            const pulse = v.warming ? 0.5 + 0.5 * Math.sin(seconds * Math.PI * 1.4) : 0.4;
            if (v.heating) {
                arc(23, v.color, 0.04 + pulse * 0.06, start, end);
                arc(15, v.color, 0.08 + pulse * 0.12, start, end);
            }
            arc(7, v.color, 1, start, end);
            if (v.boost) {
                // A moving outer accent denotes mode, never measured progress.
                const phase = this._animationId ? (seconds / 2) % 1 : 0.5;
                const from = start + phase * (length - 0.35);
                arc(3, v.color, 0.85, from, from + 0.35, radius + 11);
            }
        }
        cr.$dispose();
    }

    _render() {
        const c = this._client;
        if (!c) return;
        const t = this._t;
        const s = c.snapshot;
        const ready = c.state === 'ready';
        const fresh = ready && !c.stale;
        const mock = c.mode === 'mock';
        this._connectionLabel.text = mock && ready ? t('demoReady') : t(c.state);
        this._connectionLabel.set_style(fresh ? 'color: #34d399;' : '');
        active(this._demoButton, mock);
        active(this._liveButton, !mock);
        sensitive(this._demoButton, !c.switchingMode);
        sensitive(this._liveButton, !c.switchingMode);
        this._modeNotice.text = t(mock ? 'demoNotice' : 'liveNotice');
        const batteryKnown = fresh && Number.isInteger(s.battery_percent);
        this._battery.text = batteryKnown ? `${s.charging === true ? 'ϟ ' : ''}${s.battery_percent}%` : '—';
        this._battery.accessible_name = `${t('battery')}: ${batteryKnown ? s.battery_percent + '%' : t('unavailable')}. ${t(s.charging === true ? 'charging' : s.charging === false ? 'notCharging' : 'chargeUnknown')}`;
        this._barBattery.text = batteryKnown ? `${s.battery_percent}%${mock ? ' · D' : ''}` : mock ? 'D' : '';
        this.accessible_name = `Veazy · ${this._connectionLabel.text} · ${this._battery.accessible_name}`;
        this._errorBox.visible = Boolean(c.error);
        this._errorLabel.text = String(c.error || '').slice(0, 1024);
        this._pendingLabel.visible = c.pending || (ready && c.stale);
        this._pendingLabel.text = t(c.pending ? 'pending' : 'stale');
        this._connectionBox.visible = !ready;
        this._disconnectButton.visible = ready || ['connecting', 'initializing', 'disconnecting'].includes(c.state);
        sensitive(this._disconnectButton, c.state !== 'disconnecting');
        this._scanButton.label = t(mock ? 'startDemo' : 'scan');
        sensitive(this._scanButton, !c.pending && !c.busy && !c.switchingMode);
        const devicesKey = JSON.stringify(c.devices);
        if (devicesKey !== this._devicesKey) {
            this._devicesKey = devicesKey;
            this._deviceList.destroy_all_children();
            for (const device of c.devices) {
                const row = box(false, 'veazy-device-row');
                row.add_child(label(device.name, 'veazy-device-name', {x_expand: true}));
                row.add_child(button(t('connect'), () => {
                    if (c.selectDevice(device.id)) c.connectDevice();
                }, 'veazy-connect-button'));
                this._deviceList.add_child(row);
            }
        }
        for (const row of this._deviceList.get_children()) {
            const connect = row.get_last_child();
            sensitive(connect, !c.busy && !c.pending && !ready);
        }
        if (!ready) {
            this._dirtyTarget = false;
            this._draftTarget = null;
            this._offsetDrafts = {};
        } else if (!this._dirtyTarget) {
            this._draftTarget = fresh ? s.target_temperature_c : null;
        }
        if (!this._targetEntry.has_key_focus()) this._setTargetText();
        const offset = s.heater_mode === 2 ? s.boost_offset_c : s.heater_mode === 3 ? s.superboost_offset_c : 0;
        const effective = fresh && Number.isInteger(s.heater_mode) && typeof s.target_temperature_c === 'number' && typeof offset === 'number'
            ? s.target_temperature_c + offset : null;
        this._temperature.text = effective === null ? '—' : `${effective}°`;
        this._heaterStatus.set_style(`color: rgb(${this._visualState().color.map(value => Math.round(value * 255)).join(',')});`);
        this._heaterStatus.text = !fresh || !Number.isInteger(s.heater_mode) ? t('unknown')
            : s.heater_mode === 0 ? t('off') : `${s.heater_mode >= 2 ? t(s.heater_mode === 3 ? 'superboost' : 'boost') + ' · ' : ''}${t(s.setpoint_reached === true ? 'reached' : s.setpoint_reached === false ? 'heating' : 'unknown')}`;
        active(this._heaterStatus, fresh && s.heater_mode > 0);
        this._measured.text = fresh && typeof s.current_temperature_c === 'number' ? `${s.current_temperature_c} °C` : t('unavailable');
        for (const [mode, actor] of this._modeButtons.entries()) {
            active(actor, fresh && s.heater_mode === mode);
            const boost = mode === 2 ? s.boost_offset_c : mode === 3 ? s.superboost_offset_c : 0;
            const allowed = mode === 0 ? c.canSetHeaterOff : c.canControl && Number.isInteger(s.heater_mode)
                && typeof boost === 'number' && typeof s.target_temperature_c === 'number' && s.target_temperature_c + boost <= 210;
            sensitive(actor, allowed);
        }
        this._updateEditor();
        for (const [key, actor] of Object.entries(this._settingButtons)) {
            const value = fresh ? s[key] : null;
            actor.label = typeof value === 'boolean' ? t(value ? 'on' : 'offSetting') : '—';
            actor.accessible_name = `${t(key)}: ${actor.label}`;
            active(actor, value === true);
            sensitive(actor, c.canControl && typeof value === 'boolean');
        }
        for (const [key, editor] of Object.entries(this._valueEditors)) {
            const actual = s[key === 'brightness' ? key : `${key}_offset_c`];
            const value = this._offsetDrafts[key] ?? actual;
            editor.value.text = fresh && typeof value === 'number' ? `${key === 'brightness' ? '' : '+'}${value}${key === 'brightness' ? '/9' : '°'}` : '—';
            sensitive(editor.minus, c.canControl && typeof actual === 'number' && value > 1);
            sensitive(editor.plus, c.canControl && typeof actual === 'number' && value < (key === 'brightness' ? 9 : 99));
            sensitive(editor.apply, c.canControl && this._offsetDrafts[key] !== undefined && this._offsetDrafts[key] !== actual);
        }
        for (const [key, actor] of Object.entries(this._detailValues)) {
            const value = ready ? s[key] : null;
            actor.text = value === null || value === undefined ? '—' : String(value).slice(0, 128) + (key.endsWith('_minutes') ? ` ${t('minutes')}` : '');
        }
        sensitive(this._findButton, c.canControl);
        sensitive(this._diagnoseButton, c.canControl);
        this._syncAnimation();
    }

    destroy() {
        if (this._animationId) GLib.Source.remove(this._animationId);
        this._animationId = 0;
        this._settings.disconnect(this._animationSignal);
        this._client?.destroy();
        this._client = null;
        super.destroy();
    }
});

export default class VeazyExtension extends Extension {
    enable() {
        this._indicator = new VeazyIndicator(this);
        Main.panel.addToStatusArea(this.uuid, this._indicator, 0, 'right');
    }

    disable() {
        this._indicator?.destroy();
        this._indicator = null;
    }
}
