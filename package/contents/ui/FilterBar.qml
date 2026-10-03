// SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * One checkable chip per launcher or store that has games, plus "All".
 *
 * The chips come from the scan, not from a list kept here, so a new provider
 * gets a chip without any QML change. Only the store labels are spelled out,
 * because a store is a provider-internal idea the backend contract says nothing
 * about; anything unrecognised falls back to "<Launcher>: <store>".
 */
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

Flickable {
    id: root

    // Entries from gamelist.sources(): {id, provider, store, name, icon, count}.
    property var sources: []
    // The selected source id, or "" for All.
    property string activeSource: ""

    signal sourcePicked(string source)

    implicitHeight: row.implicitHeight
    contentWidth: row.implicitWidth
    contentHeight: row.implicitHeight
    flickableDirection: Flickable.HorizontalFlick
    clip: true
    boundsBehavior: Flickable.StopAtBounds

    function labelFor(source) {
        if (!source.store || source.store.length === 0) {
            return source.name;
        }
        switch (source.store) {
        case "epic":     return i18n("Epic Games");
        case "gog":      return i18n("GOG");
        case "amazon":   return i18n("Amazon Games");
        case "sideload": return i18n("Sideloaded");
        case "shortcut": return i18nc("a non-Steam game added to Steam as a shortcut",
                                      "Non-Steam");
        }
        return i18nc("launcher and store, for a store this widget does not know",
                     "%1: %2", source.name, source.store);
    }

    RowLayout {
        id: row
        spacing: Kirigami.Units.smallSpacing

        Kirigami.Chip {
            closable: false
            checkable: true
            activeFocusOnTab: true
            focusPolicy: Qt.StrongFocus
            checked: root.activeSource.length === 0
            text: i18nc("show games from every launcher", "All")
            onClicked: root.sourcePicked("")
        }

        Repeater {
            model: root.sources

            delegate: Kirigami.Chip {
                required property var modelData

                closable: false
                checkable: true
                activeFocusOnTab: true
                focusPolicy: Qt.StrongFocus
                checked: root.activeSource === modelData.id
                text: root.labelFor(modelData)
                icon.name: modelData.icon
                // Clicking the active chip clears it, so the bar can be reset
                // without reaching for "All".
                onClicked: root.sourcePicked(
                    root.activeSource === modelData.id ? "" : modelData.id)

                QQC2.ToolTip.text: i18np("%1 game", "%1 games", modelData.count)
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
        }
    }
}
