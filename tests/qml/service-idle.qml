// SPDX-License-Identifier: AGPL-3.0-only
// Exercise the real Python JSONL process using status only. The runner blocks
// imports of Bleak, so even an accidental BLE operation cannot reach hardware.
import QtQuick
import Quickshell

ShellRoot {
  id: root
  property var service: null
  property int failures: 0
  property int phase: 0
  property int polls: 0
  property int serialBeforeRestart: 0
  property int generationBeforeRestart: 0
  Item { id: scene }

  function check(name, condition) {
    console.log("VEAZY_TEST", condition ? "PASS" : "FAIL", name)
    if (!condition) failures++
  }

  function finish() {
    polling.stop()
    if (service) service.setMode("mock")
    afterStop.start()
  }

  Component.onCompleted: {
    var component = Qt.createComponent(Quickshell.env("VEAZY_SOURCE_URL") + "/Service.qml", Component.PreferSynchronous)
    check("Idle Service compiles: " + component.errorString(), component.status === Component.Ready)
    if (component.status !== Component.Ready) { finish(); return }
    service = component.createObject(scene, {mode: "mock"})
    check("Idle Service instantiated", service !== null)
    if (!service) { finish(); return }
    check("Explicit live idle requested", service.setMode("live"))
    check("Live switch does not connect", service.state === "disconnected" && !service.pending)
    check("Live switch keeps heater unknown", service.snapshot.heater_mode === null)
    polling.start()
  }

  Timer {
    id: polling
    interval: 100
    repeat: true
    onTriggered: {
      if (++root.polls > 20) {
        root.check("Idle IPC completes within deadline: " + service.lastError, false)
        root.finish()
        return
      }
      if (root.phase === 0 && root.polls >= 3) {
        root.check("Live idle worker running", service.backendRunning && service._workerWanted)
        root.check("Live idle has no device", service.devices.length === 0 && service.selectedDeviceId === "")
        root.check("Live idle has no automatic request", service._serial === 0 && !service.pending)
        root.check("Explicit status request accepted", service.send("status", {}))
        root.check("Status request pending", service.pending)
        root.phase = 1
      } else if (root.phase === 1 && !service.pending) {
        root.check("Status response completed without error", service.lastError === "")
        root.check("Status remains disconnected", service.state === "disconnected" && !service.busy)
        root.check("Status has no measurement", service.snapshot.current_temperature_c === null)
        root.check("Status has no heater or target", service.snapshot.heater_mode === null && service.snapshot.target_temperature_c === null)
        root.serialBeforeRestart = service._serial
        root.generationBeforeRestart = service._generation
        root.check("Explicit return to mock", service.setMode("mock"))
        root.check("Mock switch drops requests and worker", !service.pending && !service._workerWanted)
        root.check("Mock switch clears snapshot", service.snapshot.stale === true && service.snapshot.heater_mode === null)
        root.check("Worker shutdown is serialized", service.switchingMode)
        root.check("Rapid live restart blocked", !service.setMode("live") && service.mode === "mock")
        service.receive(JSON.stringify({version: 1, session: String(root.generationBeforeRestart), event: "state", data: {state: "ready", busy: false}}))
        root.check("Stopping worker cannot restore ready", service.state === "disconnected" && !service.canControl)
        root.phase = 2
        root.polls = 0
      } else if (root.phase === 2 && root.polls >= 3 && !service.switchingMode) {
        root.check("Mock remains reset after worker exit", service.mock && service.state === "disconnected" && !service._workerStarted)
        root.check("Explicit second live idle requested", service.setMode("live"))
        root.phase = 3
        root.polls = 0
      } else if (root.phase === 3 && root.polls >= 3) {
        root.check("Second worker running", service.backendRunning && service._workerWanted)
        root.check("Restart advances session generation", service._generation > root.generationBeforeRestart)
        root.check("Restart does not replay commands", service._serial === root.serialBeforeRestart && !service.pending)
        root.check("Restart remains disconnected", service.state === "disconnected" && service.snapshot.heater_mode === null)
        root.check("New process accepts its own events", service._acceptEvents)
        service.receive(JSON.stringify({version: 1, session: String(root.generationBeforeRestart), event: "state", data: {state: "ready", busy: false}}))
        service.receive(JSON.stringify({version: 1, session: String(root.generationBeforeRestart), event: "snapshot", data: {application_valid: true, heater_mode: 1, target_temperature_c: 185, stale: false}}))
        root.check("Old process session cannot restore ready", service.state === "disconnected" && !service.canControl)
        root.check("Old process session cannot restore heater/target", service.snapshot.heater_mode === null && service.snapshot.target_temperature_c === null)
        service.receive(JSON.stringify({version: 1, event: "state", data: {state: "ready", busy: false}}))
        service.receive(JSON.stringify({version: 1, session: service._generation, event: "state", data: {state: "ready", busy: false}}))
        root.check("Missing or incorrectly typed session rejected", service.state === "disconnected")
        root.check("Second explicit status accepted", service.send("status", {}))
        root.check("Second status pending", service.pending)
        root.phase = 4
      } else if (root.phase === 4 && !service.pending) {
        root.check("Second status response completed", service.lastError === "" && service._serial === root.serialBeforeRestart + 1)
        root.check("No device after restart/status", service.devices.length === 0 && service.selectedDeviceId === "")
        root.finish()
      }
    }
  }

  Timer {
    id: afterStop
    interval: 200
    onTriggered: {
      if (service) {
        root.check("Final mode mock with worker unwanted", service.mock && !service._workerWanted)
        root.check("Final state reset", service.state === "disconnected" && !service.pending)
        root.check("Final worker fully exited", !service._workerStarted && !service.switchingMode)
        service.destroy()
      }
      console.log("VEAZY_IDLE_FINISHED", root.failures)
    }
  }
}
