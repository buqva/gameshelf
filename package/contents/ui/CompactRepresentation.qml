// SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
// SPDX-License-Identifier: GPL-2.0-or-later
/* Panel icon. Clicking it toggles the popup. */
import QtQuick
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami

Item {
    id: root

    required property PlasmoidItem plasmoidItem

    Kirigami.Icon {
        anchors.fill: parent
        source: Plasmoid.icon
        active: mouseArea.containsMouse
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: true
        onClicked: root.plasmoidItem.expanded = !root.plasmoidItem.expanded
    }
}
