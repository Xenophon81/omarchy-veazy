// SPDX-License-Identifier: AGPL-3.0-only
// Presentation only: no polling, device access, or Bluetooth commands.
import QtQuick
import qs.Commons as Commons

QtObject {
  id: root
  property var percentage: null
  property var charging: null
  property bool connected: false
  property bool stale: true
  property bool demo: false

  readonly property bool available: connected && !stale
    && typeof percentage === "number" && isFinite(percentage)
    && Math.floor(percentage) === percentage && percentage >= 0 && percentage <= 100
  readonly property bool chargingKnown: connected && !stale && typeof charging === "boolean"
  readonly property string percentageText: available
    ? strings.t("battery.percent").arg(Commons.I18n.formatNumber(percentage))
    : strings.t("common.unavailable")
  readonly property string chargingText: chargingKnown
    ? strings.t(charging ? "battery.charging" : "battery.notCharging")
    : strings.t("common.unknown")
  readonly property string compactText: available
    ? (chargingKnown && charging ? strings.t("battery.compactCharging").arg(percentageText) : percentageText)
    : ""
  readonly property string barText: demo
    ? (available ? strings.t("battery.demo").arg(strings.t("mode.mock")).arg(compactText) : strings.t("mode.mock"))
    : compactText

  property Commons.Translations strings: Commons.Translations {
    directory: Qt.resolvedUrl("../i18n")
  }
}
