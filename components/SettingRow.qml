// SPDX-License-Identifier: AGPL-3.0-only
import QtQuick
import QtQuick.Layouts
import qs.Commons as Commons

RowLayout {
  id: root
  property string label: ""
  property string description: ""
  property var value: null
  property string enabledLabel: ""
  property string disabledLabel: ""
  property string unknownLabel: ""
  property bool allowed: false
  property var focusHandler: null
  signal requested(bool value)
  spacing: Commons.Style.spacing.md

  ColumnLayout {
    Layout.fillWidth: true
    spacing: Commons.Style.spacing.xs
    PlainText { text: root.label; Layout.fillWidth: true }
    PlainText {
      text: root.value === null || root.value === undefined ? root.unknownLabel : root.description
      visible: text !== ""
      Layout.fillWidth: true
      font.pixelSize: Commons.Style.font.caption
      opacity: 0.7
    }
  }

  ActionButton {
    text: typeof root.value === "boolean" ? (root.value ? root.enabledLabel : root.disabledLabel) : root.unknownLabel
    selected: root.value === true
    enabled: root.allowed && typeof root.value === "boolean"
    focusHandler: root.focusHandler
    onClicked: root.requested(root.value !== true)
  }
}
