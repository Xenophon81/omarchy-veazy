// SPDX-License-Identifier: AGPL-3.0-only
import QtQuick
import Quickshell
import Quickshell.Io

// One instance per plugin id, shared by every monitor through the host facade.
Item {
  id: root
  property var shell: null
  property string mode: "mock"
  readonly property bool mock: mode === "mock"
  property string state: "disconnected"
  property var devices: []
  property string selectedDeviceId: ""
  property var snapshot: emptySnapshot()
  property string lastError: ""
  property bool busy: false
  property var _requests: ({})
  property int _serial: 0
  property int _generation: 0
  property bool _workerWanted: false
  property bool _workerStarted: false
  property bool _workerStopping: false
  property bool _acceptEvents: false
  readonly property bool switchingMode: _workerStopping
  readonly property bool pending: Object.keys(_requests).length > 0
  readonly property bool backendRunning: mock || worker.running
  readonly property bool available: backendRunning
  readonly property bool stale: snapshot.stale !== false
  readonly property bool canControl: state === "ready" && !busy && !pending
    && !stale && snapshot.application_valid === true
  readonly property bool canSetHeaterOff: state === "ready" && !busy && !pending
    && snapshot.application_valid === true

  function emptySnapshot() {
    return {
      current_temperature_c: null, target_temperature_c: null,
      boost_offset_c: null, superboost_offset_c: null, heater_mode: null,
      battery_percent: null, charging: null, setpoint_reached: null,
      firmware_version: null, serial_number: null, brightness: null,
      vibration: null, charge_current_optimization: null,
      charge_voltage_limit: null, boost_visualization: null,
      boost_timeout_disabled: null, permanent_bluetooth: null,
      heater_runtime_minutes: null, charging_time_minutes: null,
      analysis_code: null, analysis_category: null,
      application_valid: null, stale: true
    }
  }

  function fail(message) {
    lastError = String(message).slice(0, 1024)
    return false
  }

  function integer(value, minimum, maximum) {
    return typeof value === "number" && isFinite(value)
      && Math.floor(value) === value && value >= minimum && value <= maximum
  }

  function localPath(url) {
    return decodeURIComponent(String(url).replace(/^file:\/\//, ""))
  }

  function reset() {
    _generation += 1
    _requests = ({})
    mockScan.stop()
    state = "disconnected"
    devices = []
    selectedDeviceId = ""
    snapshot = emptySnapshot()
    busy = false
    lastError = ""
  }

  function setMode(next) {
    if (next !== "mock" && next !== "live") return fail("Unknown operating mode.")
    if (next === mode) return true
    if (_workerStopping) return fail("The previous backend is still stopping. Try again when it has stopped.")
    // A live worker is terminated on leaving live mode, never carried into mock.
    _acceptEvents = false
    _workerStopping = worker.running || _workerStarted
    _workerWanted = false
    reset()
    mode = next
    if (!mock) _workerWanted = true
    return true
  }

  function selectDevice(deviceId) {
    if (busy || pending || state === "ready") return false
    for (var i = 0; i < devices.length; ++i) {
      if (devices[i].id === deviceId) {
        selectedDeviceId = deviceId
        return true
      }
    }
    return fail("Select a device from the discovery results.")
  }

  function scan() {
    if (busy || pending || state === "ready") return false
    lastError = ""
    devices = []
    selectedDeviceId = ""
    if (!mock) return send("scan", {})
    state = "scanning"
    busy = true
    mockScan.start()
    return true
  }

  function connectDevice() {
    if (busy || pending) return false
    if (!selectedDeviceId) return fail("Discover and select your Veazy first.")
    if (!mock) return send("connect", {device_id: selectedDeviceId})
    if (selectedDeviceId !== "mock-veazy") return fail("Unknown demonstration device.")
    snapshot = {
      current_temperature_c: null, target_temperature_c: 185,
      boost_offset_c: 15, superboost_offset_c: 25, heater_mode: 0,
      battery_percent: 82, charging: false, setpoint_reached: false,
      firmware_version: "DEMO", serial_number: "DEMO-VEAZY",
      brightness: 9, vibration: true, charge_current_optimization: false,
      charge_voltage_limit: false, boost_visualization: true,
      boost_timeout_disabled: false, permanent_bluetooth: false,
      heater_runtime_minutes: 0, charging_time_minutes: 0,
      analysis_code: null, analysis_category: null,
      application_valid: true, stale: false
    }
    state = "ready"
    return true
  }

  function disconnectDevice() {
    if (!mock) return send("disconnect", {}, true)
    reset()
    return true
  }

  function patchSnapshot(changes) {
    var next = Object.assign({}, snapshot, changes)
    snapshot = next
  }

  function targetAllowed(target, boost, superboost, heaterMode) {
    if (!integer(heaterMode, 0, 3)) return false
    var effective = target + (heaterMode === 2 ? boost : heaterMode === 3 ? superboost : 0)
    return integer(target, 40, 210) && integer(boost, 1, 99)
      && integer(superboost, 1, 99) && effective <= 210
  }

  function setTarget(value) {
    if (!canControl) return false
    if (!integer(value, 40, 210)
        || !targetAllowed(value, snapshot.boost_offset_c, snapshot.superboost_offset_c, snapshot.heater_mode))
      return fail("The effective target must remain at or below 210 °C.")
    if (!mock) return send("set_target", {value: value})
    patchSnapshot({target_temperature_c: value, setpoint_reached: false})
    return true
  }

  function setHeaterMode(value) {
    if (!(value === 0 ? canSetHeaterOff : canControl)) return false
    if (!integer(value, 0, 3)) return fail("Invalid heater mode.")
    if (value !== 0 && !integer(snapshot.heater_mode, 0, 3))
      return fail("A fresh, known heater mode is required before starting heating.")
    if (value !== 0 && !targetAllowed(snapshot.target_temperature_c,
        snapshot.boost_offset_c, snapshot.superboost_offset_c, value))
      return fail("The effective target must remain at or below 210 °C.")
    if (!mock) return send("set_heater_mode", {mode: value})
    patchSnapshot({heater_mode: value, setpoint_reached: false})
    return true
  }

  function setOffset(kind, value) {
    if (!canControl || (kind !== "boost" && kind !== "superboost")) return false
    if (!integer(value, 1, 99)) return fail("Boost offsets must be whole degrees from 1 to 99.")
    var boost = kind === "boost" ? value : snapshot.boost_offset_c
    var superboost = kind === "superboost" ? value : snapshot.superboost_offset_c
    if (!targetAllowed(snapshot.target_temperature_c, boost, superboost, snapshot.heater_mode))
      return fail("The effective target must remain at or below 210 °C.")
    if (!mock) return send("set_offset", {kind: kind, value: value})
    var change = ({})
    change[kind === "boost" ? "boost_offset_c" : "superboost_offset_c"] = value
    patchSnapshot(change)
    return true
  }

  function setSetting(name, value) {
    if (!canControl) return false
    var booleans = ["vibration", "charge_current_optimization", "charge_voltage_limit",
      "boost_visualization", "boost_timeout_disabled", "permanent_bluetooth"]
    if (name === "brightness") {
      if (!integer(value, 1, 9)) return fail("Brightness must be between 1 and 9.")
    } else if (booleans.indexOf(name) === -1 || typeof value !== "boolean") {
      return fail("Unsupported setting or value.")
    }
    if (snapshot[name] === null || snapshot[name] === undefined)
      return fail("This setting is unavailable on this device.")
    if (!mock) return send("set_setting", {name: name, value: value})
    var change = ({})
    change[name] = value
    patchSnapshot(change)
    return true
  }

  function diagnose() {
    if (!canControl) return false
    if (!mock) return send("diagnose", {})
    patchSnapshot({analysis_code: 0, analysis_category: 0})
    return true
  }

  function findDevice() {
    if (!canControl) return false
    if (!mock) return send("find_device", {})
    return true
  }

  function send(command, args, interrupt) {
    if (mock || !worker.running) return fail("The Bluetooth backend is not running.")
    if (pending && !interrupt) return false
    var id = String(_generation) + ":" + String(++_serial)
    var next = Object.assign({}, _requests)
    next[id] = Date.now()
    _requests = next
    lastError = ""
    worker.write(JSON.stringify({version: 1, id: id, command: command, args: args}) + "\n")
    return true
  }

  function validateSnapshot(data) {
    if (!data || typeof data !== "object" || Array.isArray(data)) return null
    var next = Object.assign({}, snapshot)
    var ranges = {
      current_temperature_c: [0, 300], target_temperature_c: [40, 210],
      boost_offset_c: [1, 99], superboost_offset_c: [1, 99], heater_mode: [0, 3],
      battery_percent: [0, 100], brightness: [1, 9],
      heater_runtime_minutes: [0, 16777215], charging_time_minutes: [0, 16777215],
      analysis_code: [0, 255], analysis_category: [0, 255]
    }
    var bools = ["charging", "setpoint_reached", "vibration", "charge_current_optimization",
      "charge_voltage_limit", "boost_visualization", "boost_timeout_disabled",
      "permanent_bluetooth", "application_valid", "stale"]
    for (var key in data) {
      var value = data[key]
      if (ranges[key]) {
        if (value !== null && (typeof value !== "number" || !isFinite(value)
            || value < ranges[key][0] || value > ranges[key][1]
            || (key !== "current_temperature_c" && key !== "target_temperature_c"
              && Math.floor(value) !== value))) return null
        next[key] = value
      } else if (bools.indexOf(key) !== -1) {
        if (value !== null && typeof value !== "boolean") return null
        next[key] = value
      } else if (key === "firmware_version" || key === "serial_number") {
        if (value !== null && (typeof value !== "string" || value.length > 128)) return null
        next[key] = value
      }
    }
    return next
  }

  function receive(line) {
    if (mock || !_workerWanted || !_acceptEvents) return
    if (line.length > 32768) return protocolFailure("Backend message exceeds the size limit.")
    var message
    try { message = JSON.parse(line) } catch (e) { return protocolFailure("Invalid backend JSON.") }
    if (!message || message.version !== 1) return protocolFailure("Unsupported backend protocol.")
    // Process epochs are local IPC metadata, not invented BLE transaction ids.
    if (message.session !== String(_generation)) return
    if (typeof message.id === "string") {
      if (!Object.prototype.hasOwnProperty.call(_requests, message.id)) return
      var remaining = Object.assign({}, _requests)
      delete remaining[message.id]
      _requests = remaining
      if (message.ok !== true) fail(message.error && message.error.message ? message.error.message : "The operation failed.")
      else if (message.result && message.result.confirmation === "unknown"
          && typeof message.result.message === "string") fail(message.result.message)
      return
    }
    var data = message.data
    if (message.event === "state") {
      var states = ["disconnected", "scanning", "connecting", "initializing", "ready", "disconnecting", "error"]
      if (!data || states.indexOf(data.state) === -1 || typeof data.busy !== "boolean")
        return protocolFailure("Invalid backend state.")
      state = data.state
      busy = data.busy
      if (state === "disconnected") snapshot = emptySnapshot()
    } else if (message.event === "snapshot") {
      var next = validateSnapshot(data)
      if (!next) return protocolFailure("Invalid device data from backend.")
      snapshot = next
    } else if (message.event === "devices") {
      if (!data || !Array.isArray(data.devices) || data.devices.length > 64)
        return protocolFailure("Invalid discovery results.")
      var found = []
      for (var i = 0; i < data.devices.length; ++i) {
        var device = data.devices[i]
        if (!device || typeof device.id !== "string" || device.id.length > 128
            || typeof device.name !== "string" || device.name.length > 128)
          return protocolFailure("Invalid discovery entry.")
        found.push({id: device.id, name: device.name})
      }
      devices = found
    } else if (message.event === "error") {
      if (!data || typeof data.message !== "string") return protocolFailure("Invalid backend error.")
      fail(data.message)
    } else {
      protocolFailure("Unknown backend event.")
    }
  }

  function protocolFailure(message) {
    _acceptEvents = false
    _workerStopping = worker.running || _workerStarted
    _workerWanted = false
    _requests = ({})
    snapshot = emptySnapshot()
    state = "error"
    busy = false
    fail(message)
  }

  Timer {
    id: mockScan
    interval: 250
    onTriggered: {
      root.devices = [{id: "mock-veazy", name: "S&B VZ — DEMO"}]
      root.busy = false
      root.state = "disconnected"
    }
  }

  Timer {
    interval: 1000
    running: !root.mock && root.pending
    repeat: true
    onTriggered: {
      var now = Date.now()
      for (var id in root._requests) {
        if (now - root._requests[id] > 45000) {
          // Terminate uncertain work; a new worker must never replay it.
          root.protocolFailure("The operation timed out. Select demonstration mode and Bluetooth mode to restart the backend; no commands are repeated.")
          return
        }
      }
    }
  }

  Process {
    id: worker
    command: ["bash", root.localPath(Qt.resolvedUrl("scripts/run-backend"))]
    environment: ({OMARCHY_VEAZY_WORKER_SESSION: String(root._generation)})
    stdinEnabled: true
    running: root._workerWanted
    stdout: SplitParser { onRead: data => root.receive(data) }
    stderr: SplitParser {
      onRead: data => console.warn("omarchy-veazy backend: " + data.slice(0, 2048))
    }
    onStarted: {
      root._workerStarted = true
      root._acceptEvents = !root.mock && !root._workerStopping && root._workerWanted
      if (!root._acceptEvents) root._workerWanted = false
    }
    onExited: function(exitCode, exitStatus) {
      var intentional = root._workerStopping
      root._workerStarted = false
      root._workerStopping = false
      root._acceptEvents = false
      root._workerWanted = false
      if (root.mock || intentional) return
      root._requests = ({})
      root.snapshot = root.emptySnapshot()
      root.busy = false
      root.state = "error"
      if (!root.lastError) root.fail("The Bluetooth backend stopped (exit " + exitCode + ").")
    }
    onRunningChanged: {
      if (!running && !root._workerStarted && root._workerStopping) root._workerStopping = false
      if (!running && root._workerWanted && !root.mock && !root._workerStarted) {
        root._workerWanted = false
        root.state = "error"
        root.fail("Unable to start the Bluetooth backend. Check the installation.")
      }
    }
  }

  Component.onDestruction: {
    _workerWanted = false
  }
}
