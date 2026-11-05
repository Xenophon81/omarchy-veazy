// SPDX-License-Identifier: AGPL-3.0-only
// Original geometric icon; no upstream artwork is used.
pragma ComponentBehavior: Bound
import QtQuick
import qs.Commons as Commons

Item {
  id: root
  property color color: Commons.Color.foreground
  property bool connected: false
  property bool heating: false
  property bool mock: true
  implicitWidth: 24
  implicitHeight: 24

  Item {
    anchors.centerIn: parent
    width: parent.width
    height: parent.height

    Rectangle {
      x: parent.width * 0.40
      y: parent.height * 0.04
      width: parent.width * 0.2
      height: parent.height * 0.24
      radius: width * 0.25
      color: root.color
    }

    Rectangle {
      x: parent.width * 0.26
      y: parent.height * 0.24
      width: parent.width * 0.48
      height: parent.height * 0.68
      radius: width * 0.24
      color: "transparent"
      border.width: Math.max(1, parent.width / 13)
      border.color: root.color

      Repeater {
        model: 3
        Rectangle {
          required property int index
          x: parent.width * 0.26
          y: parent.height * (0.32 + index * 0.14)
          width: parent.width * 0.48
          height: Math.max(1, parent.height * 0.045)
          color: root.color
          opacity: 0.75
        }
      }
    }

    Rectangle {
      x: parent.width * 0.73
      y: parent.height * 0.72
      width: parent.width * 0.21
      height: width
      radius: width / 2
      visible: root.connected || root.mock
      color: root.heating ? Commons.Color.urgent : root.color
      opacity: root.mock ? 0.5 : 1
    }
  }
}
