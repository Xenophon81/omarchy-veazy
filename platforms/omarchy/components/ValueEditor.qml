// SPDX-License-Identifier: AGPL-3.0-only
import QtQuick
import QtQuick.Layouts
import qs.Commons as Commons
import qs.Ui as Ui

ColumnLayout {
  id: root
  property string label: ""
  property string applyLabel: ""
  property string suffix: ""
  property int value: 0
  property int minimum: 0
  property int maximum: 100
  property bool available: true
  property bool allowed: true
  property int draft: value
  property bool dirty: false
  property var focusHandler: null
  signal submitted(int value)

  spacing: Commons.Style.spacing.sm
  onValueChanged: if (!dirty) draft = value
  function reset() {
    dirty = false
    draft = value
  }

  PlainText {
    text: root.label
    Layout.fillWidth: true
    font.pixelSize: Commons.Style.font.bodySmall
    opacity: 0.8
  }

  RowLayout {
    Layout.fillWidth: true
    spacing: Commons.Style.spacing.md

    Ui.NumberField {
      id: input
      value: root.draft
      from: root.minimum
      to: root.maximum
      enabled: root.available
      fieldWidth: Commons.Style.space(112)
      field.locale: Qt.locale(Commons.I18n.formatLocale)
      onModified: function(next) {
        root.draft = next
        root.dirty = true
      }
      Connections {
        target: input.field
        function onActiveFocusChanged() {
          if (input.field.activeFocus && root.focusHandler) root.focusHandler(input)
        }
      }
    }

    PlainText {
      text: root.suffix
      Layout.fillWidth: true
      opacity: root.available ? 1 : 0.4
    }

    ActionButton {
      text: root.applyLabel
      enabled: root.available && root.allowed && root.draft >= root.minimum && root.draft <= root.maximum
      focusHandler: root.focusHandler
      onClicked: {
        root.submitted(root.draft)
        root.dirty = false
      }
    }
  }
}
