// SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Hidden games page: the keys the grid filters out, with their titles resolved
 * from a live scan.
 *
 * The backend does not know about hidden games — it reports everything and the
 * QML filters — so a plain `list` is enough to turn a key back into a title. A
 * key whose game is no longer installed is shown as the key itself rather than
 * dropped, otherwise it would be impossible to un-hide.
 */
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    id: page

    property var cfg_hiddenGames: []
    property var cfg_hiddenGamesDefault: []

    // key -> game, from the last scan.
    property var known: ({})
    property string loadError: ""

    function titleFor(key) {
        const game = page.known[key];
        return game && game.title ? game.title : key;
    }

    function iconFor(key) {
        const game = page.known[key];
        if (!game) {
            return "dialog-question";
        }
        switch (game.provider) {
        case "steam": return "steam";
        case "heroic": return "com.heroicgameslauncher.hgl";
        case "lutris": return "lutris";
        default: return "applications-games";
        }
    }

    function unhide(key) {
        page.cfg_hiddenGames = page.cfg_hiddenGames.filter(entry => entry !== key);
    }

    function unhideAll() {
        page.cfg_hiddenGames = [];
    }

    Backend {
        id: backend

        onListReady: (payload) => {
            const index = {};
            for (const game of (payload.games || [])) {
                index[game.key] = game;
            }
            page.known = index;
        }

        onFailed: (message) => {
            page.loadError = message;
        }
    }

    Component.onCompleted: backend.list(false)

    ColumnLayout {
        spacing: Kirigami.Units.smallSpacing

        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing

            QQC2.Label {
                Layout.fillWidth: true
                text: i18n("Games hidden from the grid. Hide a game from its right-click menu.")
                wrapMode: Text.WordWrap
                opacity: 0.7
            }

            QQC2.Button {
                text: i18n("Show all again")
                icon.name: "edit-clear-list"
                enabled: page.cfg_hiddenGames.length > 0
                onClicked: page.unhideAll()
            }
        }

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            type: Kirigami.MessageType.Warning
            visible: page.loadError.length > 0
            text: i18n("Titles could not be looked up: %1", page.loadError)
        }

        Kirigami.PlaceholderMessage {
            Layout.fillWidth: true
            Layout.topMargin: Kirigami.Units.gridUnit * 2
            visible: page.cfg_hiddenGames.length === 0
            icon.name: "view-visible"
            text: i18n("Nothing is hidden")
            explanation: i18n("Every game your launchers report is shown in the grid.")
        }

        Repeater {
            model: page.cfg_hiddenGames

            delegate: RowLayout {
                required property string modelData

                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing

                Kirigami.Icon {
                    source: page.iconFor(modelData)
                    implicitWidth: Kirigami.Units.iconSizes.small
                    implicitHeight: implicitWidth
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0

                    QQC2.Label {
                        Layout.fillWidth: true
                        text: page.titleFor(modelData)
                        elide: Text.ElideRight
                    }

                    QQC2.Label {
                        Layout.fillWidth: true
                        // Worth showing: it is the only way to tell two games of
                        // the same name from different launchers apart.
                        text: modelData
                        elide: Text.ElideRight
                        opacity: 0.6
                        font: Kirigami.Theme.smallFont
                    }
                }

                QQC2.Button {
                    text: i18n("Show")
                    icon.name: "view-visible"
                    onClicked: page.unhide(modelData)
                }
            }
        }
    }
}
