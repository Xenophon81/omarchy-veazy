// SPDX-License-Identifier: AGPL-3.0-only
import QtQuick
import QtQuick.Layouts
import qs.Commons as Commons

RowLayout {
  id: root
  property string label: ""
  property string value: ""
  spacing: Commons.Style.spacing.md

  PlainText {
    text: root.label
    Layout.fillWidth: true
    Layout.preferredWidth: 1
    opacity: 0.7
    font.pixelSize: Commons.Style.font.bodySmall
  }
  PlainText {
    text: root.value
    Layout.fillWidth: true
    Layout.preferredWidth: 1
    horizontalAlignment: Text.AlignRight
    font.pixelSize: Commons.Style.font.bodySmall
  }
}
