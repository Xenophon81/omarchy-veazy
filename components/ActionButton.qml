// SPDX-License-Identifier: AGPL-3.0-only
import QtQuick
import qs.Ui as Ui

Ui.Button {
  id: root
  property var focusHandler: null
  focusable: true
  bordered: true
  opacity: enabled ? 1 : 0.42
  // No dynamic tooltip is forwarded to a shared shell sink.
  tooltipText: ""
  onActiveFocusChanged: if (activeFocus && focusHandler) focusHandler(root)
}
