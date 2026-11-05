// SPDX-License-Identifier: AGPL-3.0-only
// Compile the actual plugin components; do not instantiate the native panel.
import QtQuick
import Quickshell

ShellRoot {
  id: root
  property int failures: 0
  Item { id: scene }

  function check(name, condition) {
    console.log("VEAZY_COMPONENT", condition ? "PASS" : "FAIL", name)
    if (!condition) failures++
  }

  function checkBattery(object) {
    check("Battery starts unavailable without a connection", !object.available && object.barText === "" && !object.chargingKnown)
    object.connected = true
    object.stale = false
    object.percentage = 15
    object.charging = true
    check("Confirmed battery and charging appear in bar", object.available && object.chargingKnown
      && object.barText.indexOf(object.percentageText) >= 0 && object.barText.indexOf("⚡") >= 0)
    object.charging = false
    check("Not charging removes charge indicator", object.chargingKnown && object.barText.indexOf("⚡") === -1)
    object.charging = null
    check("Missing charging status stays unknown", !object.chargingKnown && object.available && object.barText.indexOf("⚡") === -1)
    object.charging = "true"
    check("String charging status is never treated as charging", !object.chargingKnown && object.barText.indexOf("⚡") === -1)
    object.percentage = 0
    check("An empty battery is a valid percentage", object.available && object.barText !== "")
    object.percentage = 100
    check("A full battery is a valid percentage", object.available)
    var invalid = [null, undefined, "82", -1, 101, 82.5, NaN, Infinity, "<b>82%</b>"]
    for (var i = 0; i < invalid.length; i++) {
      object.percentage = invalid[i]
      check("Invalid battery value stays unavailable: " + String(invalid[i]), !object.available && object.barText === "")
    }
    object.percentage = 82
    object.charging = true
    object.stale = true
    check("Stale snapshot hides old battery and charge indication", !object.available && !object.chargingKnown && object.barText === ""
      && object.percentageText === object.strings.t("common.unavailable"))
    object.stale = false
    object.connected = false
    check("Disconnect hides retained battery values", !object.available && !object.chargingKnown && object.barText === "")
    object.connected = true
    object.demo = true
    check("Mock battery is visibly marked as demo", object.available && object.barText.indexOf(object.strings.t("mode.mock")) >= 0)
    object.connected = false
    check("Disconnected demo never presents a real battery reading", object.barText === object.strings.t("mode.mock"))
  }

  Component.onCompleted: {
    var paths = JSON.parse(Quickshell.env("VEAZY_QML_FILES"))
    var instantiate = Quickshell.env("VEAZY_INSTANTIATE_HELPERS") === "1"
    for (var i = 0; i < paths.length; ++i) {
      var component = Qt.createComponent(paths[i], Component.PreferSynchronous)
      var ready = component.status === Component.Ready
      console.log("VEAZY_COMPONENT", ready ? "PASS" : "FAIL", paths[i], component.errorString())
      if (!ready) {
        failures++
        continue
      }
      if (instantiate) {
        var properties = ({})
        var hostileText = "<b>Veazy &amp; diagnostics</b>"
        var plainTextFixture = paths[i].endsWith("/PlainText.qml")
        if (plainTextFixture) properties.text = hostileText
        var object = component.createObject(scene, properties)
        console.log("VEAZY_COMPONENT_CREATE", object ? "PASS" : "FAIL", paths[i], component.errorString())
        if (!object) failures++
        if (object && plainTextFixture) {
          var plain = object.textFormat === Text.PlainText && object.text === hostileText
          console.log("VEAZY_COMPONENT", plain ? "PASS" : "FAIL", "Markup-shaped device text stays plain")
          if (!plain) failures++
        }
        if (object && paths[i].endsWith("/BatteryStatus.qml")) checkBattery(object)
      }
    }
    // Give property bindings and read-only Commons initialization a turn.
    finish.start()
  }

  Timer {
    id: finish
    interval: 250
    onTriggered: console.log("VEAZY_COMPONENTS_FINISHED", root.failures)
  }
}
