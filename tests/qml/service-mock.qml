// SPDX-License-Identifier: AGPL-3.0-only
// This fixture creates only the mock service, never a panel or BLE worker.
import QtQuick
import Quickshell
ShellRoot {
  id: root
  property var service: null
  property int failures: 0
  Item { id: scene }
  function check(name, condition) {
    console.log("VEAZY_TEST", condition ? "PASS" : "FAIL", name)
    if (!condition) failures++
  }
  Component.onCompleted: {
    var c = Qt.createComponent(Quickshell.env("VEAZY_SOURCE_URL") + "/Service.qml", Component.PreferSynchronous)
    check("Service component ready: " + c.errorString(), c.status === Component.Ready)
    if (c.status !== Component.Ready) {
      console.log("VEAZY_TESTS_FINISHED", failures)
      return
    }
    service = c.createObject(scene, {mode: "mock"})
    check("Service instantiated", service !== null)
    if (!service) { console.log("VEAZY_TESTS_FINISHED", ++failures); return }
    check("Explicit mock mode", service.mode === "mock" && service.mock)
    check("No worker startup", service._workerWanted === false)
    check("Initial disconnected", service.state === "disconnected" && !service.busy && !service.pending)
    check("Initial unknown measurement", service.snapshot.current_temperature_c === null)
    check("Initial heater unknown", service.snapshot.heater_mode === null && service.snapshot.stale === true)
    check("Cannot heat before connection", !service.setHeaterMode(1))
    check("Cannot connect without selected device", !service.connectDevice())
    check("Scan explicitly requested", service.scan() && service.state === "scanning" && service.busy)
    afterScan.start()
  }
  Timer {
    id: afterScan
    interval: 350
    onTriggered: {
      check("Mock discovery complete", service.devices.length === 1 && !service.busy)
      check("No automatic selection", service.selectedDeviceId === "")
      check("Wrong device selection rejected", !service.selectDevice("<img src='https://example.invalid'>"))
      check("Explicit selection", service.selectDevice("mock-veazy"))
      check("Explicit connect", service.connectDevice())
      check("Ready and controllable", service.state === "ready" && service.canControl)
      check("Connection never starts heater", service.snapshot.heater_mode === 0)
      check("Measurement remains unknown", service.snapshot.current_temperature_c === null)
      check("Explicit target", service.setTarget(190) && service.snapshot.target_temperature_c === 190)
      check("Explicit heater", service.setHeaterMode(1) && service.snapshot.heater_mode === 1)
      check("Explicit boost", service.setHeaterMode(2) && service.snapshot.heater_mode === 2)
      check("Boost target at 210 allowed", service.setTarget(195) && service.snapshot.target_temperature_c === 195)
      check("Boost target above 210 rejected", !service.setTarget(196) && service.snapshot.target_temperature_c === 195)
      check("Active boost offset above 210 rejected", !service.setOffset("boost", 16) && service.snapshot.boost_offset_c === 15)
      check("Inactive superboost offset retained", service.snapshot.superboost_offset_c === 25)
      check("Superboost above 210 rejected", !service.setHeaterMode(3) && service.snapshot.heater_mode === 2)
      check("Explicit stop", service.setHeaterMode(0) && service.snapshot.heater_mode === 0)
      check("Lower target", service.setTarget(185))
      check("Superboost 210 allowed", service.setHeaterMode(3) && service.snapshot.heater_mode === 3)
      check("Fractional target rejected", !service.setTarget(184.5))
      check("String target rejected", !service.setTarget("184"))
      check("Setting boolean", service.setSetting("vibration", false) && service.snapshot.vibration === false)
      check("String boolean rejected", !service.setSetting("vibration", "false"))
      check("Unsupported setting rejected", !service.setSetting("eco", true))
      check("Brightness out of range rejected", !service.setSetting("brightness", 10))
      check("Diagnostics explicit", service.diagnose() && service.snapshot.analysis_code === 0)
      check("Find device explicit", service.findDevice())
      check("Stale blocks normal controls", (service.patchSnapshot({stale: true}), !service.canControl && !service.setTarget(170)))
      check("Explicit heater-off allowed while stale", service.setHeaterMode(0) && service.snapshot.heater_mode === 0)
      service.patchSnapshot({stale: false, heater_mode: null})
      check("Unknown heater blocks normal mode", !service.setHeaterMode(1))
      check("Unknown heater blocks boost", !service.setHeaterMode(2))
      check("Unknown heater allows explicit stop", service.setHeaterMode(0) && service.snapshot.heater_mode === 0)
      check("Sentinel rejected from JSON", service.validateSnapshot({current_temperature_c: 3276.8}) === null)
      check("String battery rejected", service.validateSnapshot({battery_percent: "82"}) === null)
      check("Out of range heater rejected", service.validateSnapshot({heater_mode: 4}) === null)
      check("Invalid bool rejected", service.validateSnapshot({charging: 1}) === null)
      check("Oversize firmware rejected", service.validateSnapshot({firmware_version: "a".repeat(129)}) === null)
      var integerFields = ["boost_offset_c", "superboost_offset_c", "heater_mode", "battery_percent", "brightness", "heater_runtime_minutes", "charging_time_minutes", "analysis_code", "analysis_category"]
      for (var i = 0; i < integerFields.length; i++) {
        var bad = ({})
        bad[integerFields[i]] = integerFields[i] === "brightness" ? 1.5 : integerFields[i].indexOf("offset") !== -1 ? 15.5 : 0.5
        check("Fractional integer rejected: " + integerFields[i], service.validateSnapshot(bad) === null)
      }
      check("Fractional measurement allowed", service.validateSnapshot({current_temperature_c: 185.2}).current_temperature_c === 185.2)
      check("Null snapshot rejected", service.validateSnapshot(null) === null)
      check("Array snapshot rejected", service.validateSnapshot([]) === null)
      check("Unknown measurement preserved", service.validateSnapshot({current_temperature_c: null}).current_temperature_c === null)
      check("Disconnect explicit", service.disconnectDevice())
      check("Disconnect clears devices and selection", service.devices.length === 0 && service.selectedDeviceId === "")
      check("Disconnect clears heater knowledge", service.snapshot.heater_mode === null && service.snapshot.stale === true)
      check("Disconnect clears measured temperature", service.snapshot.current_temperature_c === null)
      check("Worker never started", service._workerWanted === false)
      console.log("VEAZY_TESTS_FINISHED", failures)
      service.destroy()
    }
  }
}
