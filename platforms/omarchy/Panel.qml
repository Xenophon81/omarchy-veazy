// SPDX-License-Identifier: AGPL-3.0-only
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls as QQC
import QtQuick.Layouts
import qs.Commons as Commons
import qs.Ui as Ui
import "components" as Veazy

Ui.Panel {
  id: root
  moduleName: "io.github.xenophon81.veazy"
  ipcTarget: moduleName

  // The public facade scopes this lookup to this plugin. Every monitor uses
  // the same Service.qml instance; no process or Bluetooth work lives here.
  readonly property var backend: bar && bar.shell ? bar.shell.serviceFor(moduleName) : null
  readonly property var snapshot: backend && backend.snapshot ? backend.snapshot : ({})
  readonly property string connectionState: backend ? backend.state : "unavailable"
  readonly property bool mock: !backend || backend.mock
  readonly property bool busy: backend ? backend.busy : false
  readonly property bool pending: backend ? backend.pending : false
  readonly property bool ready: connectionState === "ready"
  readonly property bool canControl: backend ? backend.canControl : false
  readonly property bool stale: backend ? backend.stale : true
  readonly property int heaterMode: typeof snapshot.heater_mode === "number" ? snapshot.heater_mode : -1
  readonly property var target: snapshot.target_temperature_c
  readonly property var boostOffset: snapshot.boost_offset_c
  readonly property var superboostOffset: snapshot.superboost_offset_c
  readonly property var effectiveTarget: {
    if (typeof target !== "number" || heaterMode < 0) return null
    if (heaterMode === 2) return typeof boostOffset === "number" ? target + boostOffset : null
    if (heaterMode === 3) return typeof superboostOffset === "number" ? target + superboostOffset : null
    return target
  }
  property int pageIndex: 0

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }

  Veazy.BatteryStatus {
    id: battery
    percentage: root.snapshot.battery_percent
    charging: root.snapshot.charging
    connected: root.ready
    stale: root.stale
    demo: root.mock
  }

  function temperature(value) {
    return typeof value === "number" && isFinite(value)
      ? strings.t("temperature.value").arg(Commons.I18n.formatNumber(value, value % 1 ? 1 : 0))
      : strings.t("common.unavailable")
  }

  function information(value) {
    if (value === null || value === undefined || value === "") return strings.t("common.unavailable")
    if (typeof value === "number") return Commons.I18n.formatNumber(value)
    if (typeof value === "boolean") return strings.t(value ? "common.yes" : "common.no")
    return String(value).slice(0, 512)
  }

  function minutes(value) {
    return typeof value === "number"
      ? strings.t("diagnostics.minutes").arg(Commons.I18n.formatNumber(value))
      : strings.t("common.unavailable")
  }

  function focusItem(item) {
    if (panel.loadedContent) panel.loadedContent.ensureVisible(item)
  }

  function targetAllowed(base) {
    if (!canControl || heaterMode < 0) return false
    if (heaterMode === 2) return typeof boostOffset === "number" && base + boostOffset <= 210
    if (heaterMode === 3) return typeof superboostOffset === "number" && base + superboostOffset <= 210
    return true
  }

  function boostAllowed(mode) {
    var offset = mode === 2 ? boostOffset : superboostOffset
    return canControl && heaterMode >= 0 && typeof target === "number" && typeof offset === "number" && target + offset <= 210
  }

  onConnectionStateChanged: {
    if (!ready && panel.loadedContent) panel.loadedContent.resetEditors()
  }

  Ui.BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    labelText: vertical ? "" : battery.barText
    slotSize: labelText !== "" ? Math.max(Commons.Style.bar.iconSlot * 2,
      batteryLabelMetrics.advanceWidth(labelText) + canvasSize + Commons.Style.space(12)) : Commons.Style.bar.iconSlot
    // Static plugin-owned text only; no device names or IPC errors in tooltip.
    tooltipText: "Veazy"
    iconComponent: Component {
      Veazy.VeazyIcon {
        width: button.iconSize
        height: button.iconSize
        color: root.ready ? root.barForeground : Qt.darker(root.barForeground, 1.55)
        connected: root.ready
        heating: root.ready && !root.stale && root.heaterMode > 0
        mock: root.mock
      }
    }
    onPressed: function(mouseButton) {
      if (mouseButton === Qt.LeftButton) root.toggle()
    }
  }

  FontMetrics {
    id: batteryLabelMetrics
    font.family: button.fontFamily
    font.pixelSize: button.fontSize
  }

  Ui.KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: panel.loadedContent
    contentWidth: panel.fittedContentWidth(Commons.Style.space(410))
    contentHeight: panel.fittedContentHeight(panel.loadedContentHeight, Commons.Style.space(660))

    content: FocusScope {
      id: panelContent
      anchors.fill: parent
      implicitHeight: column.implicitHeight
      Keys.onEscapePressed: root.close()

      function resetEditors() {
        targetEditor.reset()
        boostEditor.reset()
        superboostEditor.reset()
        brightnessEditor.reset()
      }

      function ensureVisible(item) {
        Qt.callLater(function() {
          if (!item) return
          var position = item.mapToItem(column, 0, 0)
          var margin = Commons.Style.spacing.md
          if (position.y < flick.contentY + margin) flick.contentY = Math.max(0, position.y - margin)
          else if (position.y + item.height > flick.contentY + flick.height - margin)
            flick.contentY = Math.min(Math.max(0, flick.contentHeight - flick.height), position.y + item.height - flick.height + margin)
        })
      }

      Flickable {
        id: flick
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }

        ColumnLayout {
          id: column
          width: flick.width
          spacing: Commons.Style.spacing.xxl

          RowLayout {
            Layout.fillWidth: true
            spacing: Commons.Style.spacing.xl
            Veazy.VeazyIcon {
              Layout.preferredWidth: Commons.Style.space(28)
              Layout.preferredHeight: Commons.Style.space(28)
              connected: root.ready
              heating: root.ready && !root.stale && root.heaterMode > 0
              mock: root.mock
            }
            ColumnLayout {
              Layout.fillWidth: true
              spacing: Commons.Style.spacing.xs
              Veazy.PlainText { text: "Veazy"; font.pixelSize: Commons.Style.font.heading; font.bold: true }
              Veazy.PlainText {
                text: strings.t("state." + root.connectionState)
                Layout.fillWidth: true
                font.pixelSize: Commons.Style.font.caption
                opacity: 0.75
              }
            }
            Veazy.ActionButton {
              text: strings.t("common.close")
              focusHandler: root.focusItem
              onClicked: root.close()
            }
          }

          Rectangle {
            Layout.fillWidth: true
            implicitHeight: batterySummary.implicitHeight + Commons.Style.spacing.xl * 2
            radius: Commons.Style.cornerRadius
            color: Commons.Style.selectedFillFor(Commons.Color.popups.text, Commons.Color.accent)

            ColumnLayout {
              id: batterySummary
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              anchors.margins: Commons.Style.spacing.xl
              spacing: Commons.Style.spacing.md

              RowLayout {
                Layout.fillWidth: true
                Veazy.PlainText {
                  text: strings.t(root.mock ? "battery.demoLabel" : "battery.label")
                  font.pixelSize: Commons.Style.font.bodySmall
                  Layout.fillWidth: true
                }
                Veazy.PlainText {
                  text: battery.percentageText
                  font.pixelSize: Commons.Style.font.heading
                  font.bold: battery.available
                  color: battery.available && battery.percentage <= 15 && battery.charging !== true
                    ? Commons.Color.urgent : Commons.Color.popups.text
                }
              }

              Rectangle {
                Layout.fillWidth: true
                implicitHeight: Commons.Style.space(4)
                radius: height / 2
                color: Commons.Style.selectedFillFor(Commons.Color.popups.text, Commons.Color.popups.text)
                visible: battery.available
                Rectangle {
                  height: parent.height
                  width: parent.width * (battery.available ? battery.percentage / 100 : 0)
                  radius: parent.radius
                  color: battery.percentage <= 15 && battery.charging !== true
                    ? Commons.Color.urgent : Commons.Color.accent
                }
              }

              Veazy.PlainText {
                Layout.fillWidth: true
                text: battery.chargingKnown ? battery.chargingText : strings.t("battery.chargingUnknown")
                font.pixelSize: Commons.Style.font.caption
                opacity: 0.75
              }
            }
          }

          Rectangle {
            Layout.fillWidth: true
            implicitHeight: modeNotice.implicitHeight + Commons.Style.spacing.xl * 2
            color: Commons.Style.selectedFillFor(Commons.Color.popups.text, Commons.Color.accent)
            radius: Commons.Style.cornerRadius
            Veazy.PlainText {
              id: modeNotice
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              anchors.margins: Commons.Style.spacing.xl
              text: strings.t(root.mock ? "mode.mockNotice" : "mode.liveNotice")
              font.pixelSize: Commons.Style.font.bodySmall
            }
          }

          RowLayout {
            Layout.fillWidth: true
            spacing: Commons.Style.spacing.md
            Veazy.ActionButton {
              Layout.fillWidth: true
              text: strings.t("mode.mock")
              selected: root.mock
              enabled: root.backend && !root.backend.switchingMode && !root.busy && !root.pending
              focusHandler: root.focusItem
              onClicked: { root.backend.setMode("mock"); panelContent.resetEditors() }
            }
            Veazy.ActionButton {
              Layout.fillWidth: true
              text: strings.t("mode.live")
              selected: !root.mock
              enabled: root.backend && !root.backend.switchingMode && !root.busy && !root.pending
              focusHandler: root.focusItem
              onClicked: { root.backend.setMode("live"); panelContent.resetEditors() }
            }
          }

          Veazy.PlainText {
            Layout.fillWidth: true
            visible: root.backend && root.backend.lastError !== ""
            text: root.backend ? String(root.backend.lastError).slice(0, 1024) : ""
            color: Commons.Color.urgent
            font.pixelSize: Commons.Style.font.bodySmall
          }

          Veazy.PlainText {
            Layout.fillWidth: true
            visible: root.pending || (root.stale && root.ready)
            text: strings.t(root.pending ? "status.pending" : "status.stale")
            color: Commons.Color.urgent
            font.pixelSize: Commons.Style.font.bodySmall
          }

          RowLayout {
            Layout.fillWidth: true
            Veazy.ActionButton {
              Layout.fillWidth: true
              text: strings.t("connection.scan")
              enabled: root.backend && !root.busy && !root.pending && !root.ready
              focusHandler: root.focusItem
              onClicked: root.backend.scan()
            }
            Veazy.ActionButton {
              Layout.fillWidth: true
              text: strings.t("connection.disconnect")
              enabled: root.backend && ["connecting", "initializing", "ready"].indexOf(root.connectionState) >= 0
              focusHandler: root.focusItem
              onClicked: root.backend.disconnectDevice()
            }
          }

          ColumnLayout {
            Layout.fillWidth: true
            visible: !root.ready
            spacing: Commons.Style.spacing.sm
            Veazy.PlainText {
              Layout.fillWidth: true
              text: strings.t("connection.selectNotice")
              opacity: 0.7
              font.pixelSize: Commons.Style.font.caption
            }
            Repeater {
              model: root.backend ? root.backend.devices : []
              delegate: Veazy.ActionButton {
                required property var modelData
                Layout.fillWidth: true
                leftAlign: true
                text: String(modelData.name || strings.t("connection.unnamed")).slice(0, 128) + " · " + String(modelData.id || "").slice(0, 64)
                selected: root.backend && root.backend.selectedDeviceId === modelData.id
                enabled: root.backend && !root.busy
                focusHandler: root.focusItem
                onClicked: root.backend.selectDevice(modelData.id)
              }
            }
            Veazy.ActionButton {
              Layout.fillWidth: true
              text: strings.t("connection.connect")
              enabled: root.backend && !root.busy && root.backend.selectedDeviceId !== ""
              focusHandler: root.focusItem
              onClicked: root.backend.connectDevice()
            }
          }

          RowLayout {
            Layout.fillWidth: true
            spacing: Commons.Style.spacing.xs
            Repeater {
              model: ["control", "settings", "diagnostics", "about"]
              delegate: Veazy.ActionButton {
                required property string modelData
                required property int index
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                horizontalPadding: Commons.Style.spacing.sm
                text: strings.t("tab." + modelData)
                selected: root.pageIndex === index
                focusHandler: root.focusItem
                onClicked: { root.pageIndex = index; flick.contentY = 0 }
              }
            }
          }

          ColumnLayout {
            Layout.fillWidth: true
            visible: root.pageIndex === 0
            spacing: Commons.Style.spacing.xxl

            RowLayout {
              Layout.fillWidth: true
              spacing: Commons.Style.spacing.xl
              ColumnLayout {
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                Veazy.PlainText { text: strings.t("temperature.current"); font.pixelSize: Commons.Style.font.caption; opacity: 0.7; Layout.fillWidth: true }
                Veazy.PlainText {
                  Layout.fillWidth: true
                  text: root.ready && !root.stale ? root.temperature(root.snapshot.current_temperature_c) : strings.t("common.unavailable")
                  font.pixelSize: typeof root.snapshot.current_temperature_c === "number" ? Commons.Style.font.display : Commons.Style.font.body
                }
              }
              ColumnLayout {
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                Veazy.PlainText { text: strings.t("temperature.effective"); font.pixelSize: Commons.Style.font.caption; opacity: 0.7; Layout.fillWidth: true }
                Veazy.PlainText {
                  Layout.fillWidth: true
                  text: root.ready && !root.stale ? root.temperature(root.effectiveTarget) : strings.t("common.unavailable")
                  font.pixelSize: typeof root.effectiveTarget === "number" ? Commons.Style.font.display : Commons.Style.font.body
                }
              }
            }

            Veazy.PlainText {
              Layout.fillWidth: true
              text: strings.t("temperature.measurementNotice")
              opacity: 0.7
              font.pixelSize: Commons.Style.font.caption
            }

            Veazy.InfoRow {
              Layout.fillWidth: true
              label: strings.t("status.heater")
              value: root.ready && !root.stale && root.heaterMode >= 0 ? strings.t("heater.mode" + root.heaterMode) : strings.t("common.unknown")
            }
            Veazy.InfoRow {
              Layout.fillWidth: true
              label: strings.t("status.setpoint")
              value: !root.ready || root.stale ? strings.t("common.unknown") : root.information(root.snapshot.setpoint_reached)
            }
            Veazy.InfoRow {
              Layout.fillWidth: true
              label: strings.t("battery.label")
              value: battery.percentageText
            }
            Veazy.InfoRow {
              Layout.fillWidth: true
              label: strings.t("battery.charging")
              value: battery.chargingKnown ? root.information(root.snapshot.charging) : strings.t("common.unknown")
            }

            Veazy.ValueEditor {
              id: targetEditor
              Layout.fillWidth: true
              label: strings.t("temperature.target")
              suffix: "°C"
              minimum: 40
              maximum: 210
              value: typeof root.target === "number" ? root.target : 180
              available: root.ready && typeof root.target === "number"
              allowed: root.targetAllowed(draft)
              applyLabel: strings.t("common.apply")
              focusHandler: root.focusItem
              onSubmitted: function(value) { root.backend.setTarget(value) }
            }

            RowLayout {
              Layout.fillWidth: true
              Veazy.ActionButton {
                Layout.fillWidth: true
                text: strings.t("heater.on")
                selected: root.ready && !root.stale && root.heaterMode === 1
                enabled: root.canControl && root.heaterMode >= 0
                focusHandler: root.focusItem
                onClicked: root.backend.setHeaterMode(1)
              }
              Veazy.ActionButton {
                Layout.fillWidth: true
                text: strings.t("heater.off")
                selected: root.ready && !root.stale && root.heaterMode === 0
                enabled: root.backend ? root.backend.canSetHeaterOff : false
                focusHandler: root.focusItem
                onClicked: root.backend.setHeaterMode(0)
              }
            }
            RowLayout {
              Layout.fillWidth: true
              Veazy.ActionButton {
                Layout.fillWidth: true
                text: "Boost"
                selected: root.ready && !root.stale && root.heaterMode === 2
                enabled: root.boostAllowed(2)
                focusHandler: root.focusItem
                onClicked: root.backend.setHeaterMode(2)
              }
              Veazy.ActionButton {
                Layout.fillWidth: true
                text: "Superboost"
                selected: root.ready && !root.stale && root.heaterMode === 3
                enabled: root.boostAllowed(3)
                focusHandler: root.focusItem
                onClicked: root.backend.setHeaterMode(3)
              }
            }
            Veazy.PlainText {
              Layout.fillWidth: true
              text: strings.t("temperature.limitNotice")
              font.pixelSize: Commons.Style.font.caption
              opacity: 0.7
            }
            Veazy.ValueEditor {
              id: boostEditor
              Layout.fillWidth: true
              label: strings.t("boost.offset")
              suffix: "°C"
              minimum: 1
              maximum: 99
              value: typeof root.boostOffset === "number" ? root.boostOffset : 15
              available: root.ready && typeof root.boostOffset === "number"
              allowed: root.canControl && root.heaterMode >= 0 && (root.heaterMode !== 2 || (typeof root.target === "number" && root.target + draft <= 210))
              applyLabel: strings.t("common.apply")
              focusHandler: root.focusItem
              onSubmitted: function(value) { root.backend.setOffset("boost", value) }
            }
            Veazy.ValueEditor {
              id: superboostEditor
              Layout.fillWidth: true
              label: strings.t("boost.superOffset")
              suffix: "°C"
              minimum: 1
              maximum: 99
              value: typeof root.superboostOffset === "number" ? root.superboostOffset : 30
              available: root.ready && typeof root.superboostOffset === "number"
              allowed: root.canControl && root.heaterMode >= 0 && (root.heaterMode !== 3 || (typeof root.target === "number" && root.target + draft <= 210))
              applyLabel: strings.t("common.apply")
              focusHandler: root.focusItem
              onSubmitted: function(value) { root.backend.setOffset("superboost", value) }
            }
          }

          ColumnLayout {
            Layout.fillWidth: true
            visible: root.pageIndex === 1
            spacing: Commons.Style.spacing.xxl
            Veazy.PlainText {
              Layout.fillWidth: true
              text: strings.t("settings.notice")
              font.pixelSize: Commons.Style.font.caption
              opacity: 0.7
            }
            Repeater {
              model: [
                "vibration", "charge_current_optimization", "charge_voltage_limit",
                "boost_visualization", "boost_timeout_disabled", "permanent_bluetooth"
              ]
              delegate: Veazy.SettingRow {
                required property string modelData
                Layout.fillWidth: true
                label: strings.t("settings." + modelData)
                description: strings.t("settings." + modelData + ".description")
                value: root.ready ? root.snapshot[modelData] : null
                allowed: root.canControl
                enabledLabel: strings.t("common.on")
                disabledLabel: strings.t("common.off")
                unknownLabel: strings.t("common.unavailable")
                focusHandler: root.focusItem
                onRequested: function(value) { root.backend.setSetting(modelData, value) }
              }
            }
            Veazy.ValueEditor {
              id: brightnessEditor
              Layout.fillWidth: true
              label: strings.t("settings.brightness")
              minimum: 1
              maximum: 9
              value: typeof root.snapshot.brightness === "number" ? root.snapshot.brightness : 5
              available: root.ready && typeof root.snapshot.brightness === "number"
              allowed: root.canControl
              applyLabel: strings.t("common.apply")
              focusHandler: root.focusItem
              onSubmitted: function(value) { root.backend.setSetting("brightness", value) }
            }
            Veazy.ActionButton {
              Layout.fillWidth: true
              text: strings.t("settings.find")
              enabled: root.canControl && root.snapshot.permanent_bluetooth !== undefined && root.snapshot.permanent_bluetooth !== null
              focusHandler: root.focusItem
              onClicked: root.backend.findDevice()
            }
          }

          ColumnLayout {
            Layout.fillWidth: true
            visible: root.pageIndex === 2
            spacing: Commons.Style.spacing.xl
            Veazy.PlainText {
              Layout.fillWidth: true
              text: strings.t("diagnostics.notice")
              font.pixelSize: Commons.Style.font.caption
              opacity: 0.7
            }
            Repeater {
              model: ["firmware_version", "serial_number", "application_valid", "analysis_code", "analysis_category"]
              delegate: Veazy.InfoRow {
                required property string modelData
                Layout.fillWidth: true
                label: strings.t("diagnostics." + modelData)
                value: root.information(root.snapshot[modelData])
              }
            }
            Veazy.InfoRow {
              Layout.fillWidth: true
              label: strings.t("diagnostics.heater_runtime_minutes")
              value: root.minutes(root.snapshot.heater_runtime_minutes)
            }
            Veazy.InfoRow {
              Layout.fillWidth: true
              label: strings.t("diagnostics.charging_time_minutes")
              value: root.minutes(root.snapshot.charging_time_minutes)
            }
            Veazy.ActionButton {
              Layout.fillWidth: true
              text: strings.t("diagnostics.read")
              enabled: root.ready && !root.busy && !root.pending
              focusHandler: root.focusItem
              onClicked: root.backend.diagnose()
            }
          }

          ColumnLayout {
            Layout.fillWidth: true
            visible: root.pageIndex === 3
            spacing: Commons.Style.spacing.xl
            Veazy.PlainText { text: "omarchy-veazy"; font.bold: true; Layout.fillWidth: true }
            Veazy.PlainText { text: strings.t("about.native"); Layout.fillWidth: true }
            Veazy.PlainText { text: strings.t("about.credits"); Layout.fillWidth: true }
            Veazy.PlainText {
              text: "https://github.com/firsttris/reactive-volcano-app"
              Layout.fillWidth: true
              font.pixelSize: Commons.Style.font.bodySmall
              wrapMode: Text.WrapAnywhere
            }
            Veazy.PlainText { text: "AGPL-3.0-only"; Layout.fillWidth: true }
            Veazy.PlainText {
              text: strings.t("about.hardware")
              Layout.fillWidth: true
              font.pixelSize: Commons.Style.font.caption
              opacity: 0.7
            }
          }

          Veazy.PlainText {
            Layout.fillWidth: true
            text: strings.t("keyboard.hint")
            opacity: 0.5
            font.pixelSize: Commons.Style.font.caption
          }
        }
      }
    }
  }
}
