// SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * General page: how the grid looks and what a click does.
 *
 * Sorting and favourites are stored here but only take effect in M7; the
 * entries exist now so a user's choice survives the upgrade.
 */
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM
import org.kde.iconthemes as KIconThemes

KCM.SimpleKCM {
    id: page

    property string cfg_panelIcon: "input-gaming"
    property string cfg_panelIconDefault: "input-gaming"

    property int cfg_tileSize: 120
    property int cfg_tileSizeDefault: 120

    property string cfg_tileStyle: "portrait"
    property string cfg_tileStyleDefault: "portrait"

    property alias cfg_showTitles: showTitles.checked
    property bool cfg_showTitlesDefault: false

    property alias cfg_showProviderBadge: showProviderBadge.checked
    property bool cfg_showProviderBadgeDefault: true

    property alias cfg_showStoreBadge: showStoreBadge.checked
    property bool cfg_showStoreBadgeDefault: true

    property alias cfg_showFilterBar: showFilterBar.checked
    property bool cfg_showFilterBarDefault: true

    property alias cfg_showLauncherTiles: showLauncherTiles.checked
    property bool cfg_showLauncherTilesDefault: true

    property alias cfg_favoritesFirst: favoritesFirst.checked
    property bool cfg_favoritesFirstDefault: true

    property string cfg_sortMode: "recent"
    property string cfg_sortModeDefault: "recent"

    property alias cfg_closeOnLaunch: closeOnLaunch.checked
    property bool cfg_closeOnLaunchDefault: true

    property alias cfg_pythonPath: pythonPath.text
    property string cfg_pythonPathDefault: "python3"

    property alias cfg_showAdvancedActions: showAdvancedActions.checked
    property bool cfg_showAdvancedActionsDefault: false

    /* ComboBox.indexOfValue and currentValue resolve `valueRole` through the
     * delegate model, which a plain array of JS objects does not supply, so a
     * combo would always show its first entry. Look the option up directly. */
    function optionIndex(options, value) {
        for (let index = 0; index < options.length; ++index) {
            if (options[index].value === value) {
                return index;
            }
        }
        return 0;
    }

    KIconThemes.IconDialog {
        id: iconDialog
        onIconNameChanged: (iconName) => page.cfg_panelIcon = iconName || "input-gaming"
    }

    Kirigami.FormLayout {
        id: form

        // -- panel ------------------------------------------------------------

        RowLayout {
            Kirigami.FormData.label: i18n("Panel icon:")
            spacing: Kirigami.Units.smallSpacing

            QQC2.Button {
                Layout.preferredWidth: Kirigami.Units.iconSizes.large + Kirigami.Units.largeSpacing
                Layout.preferredHeight: Layout.preferredWidth
                onClicked: iconDialog.open()

                Kirigami.Icon {
                    anchors.centerIn: parent
                    width: Kirigami.Units.iconSizes.large
                    height: width
                    source: page.cfg_panelIcon
                }
            }

            QQC2.Button {
                text: i18n("Reset")
                icon.name: "edit-clear"
                enabled: page.cfg_panelIcon !== page.cfg_panelIconDefault
                onClicked: page.cfg_panelIcon = page.cfg_panelIconDefault
            }
        }

        Item { Kirigami.FormData.isSection: true }

        // -- grid -------------------------------------------------------------

        RowLayout {
            Kirigami.FormData.label: i18n("Tile size:")
            spacing: Kirigami.Units.smallSpacing

            QQC2.Slider {
                id: tileSize
                Layout.fillWidth: true
                Layout.minimumWidth: Kirigami.Units.gridUnit * 10
                from: 64
                to: 256
                stepSize: 8
                snapMode: QQC2.Slider.SnapAlways
                value: page.cfg_tileSize
                onMoved: page.cfg_tileSize = Math.round(value)
            }

            QQC2.Label {
                id: tileSizeLabel
                text: i18nc("@label tile width in pixels", "%1 px", page.cfg_tileSize)
                // Reserve room for the widest value, so the slider next to it
                // does not shift as the number grows.
                Layout.minimumWidth: widestTileSize.width

                TextMetrics {
                    id: widestTileSize
                    font: tileSizeLabel.font
                    text: i18nc("@label tile width in pixels", "%1 px", 256)
                }
            }
        }

        QQC2.ComboBox {
            id: tileStyle
            Kirigami.FormData.label: i18n("Tile shape:")
            textRole: "label"
            model: [
                { value: "portrait", label: i18n("Portrait (box art)") },
                { value: "landscape", label: i18n("Landscape (banner)") }
            ]
            currentIndex: page.optionIndex(model, page.cfg_tileStyle)
            onActivated: (index) => {
                page.cfg_tileStyle = model[index].value;
                currentIndex = Qt.binding(() => page.optionIndex(model, page.cfg_tileStyle));
            }
        }

        QQC2.CheckBox {
            id: showTitles
            Kirigami.FormData.label: i18n("Show:")
            text: i18n("Game titles under the tiles")
        }

        QQC2.CheckBox {
            id: showProviderBadge
            text: i18n("A launcher badge on each tile")
        }

        QQC2.CheckBox {
            id: showStoreBadge
            text: i18n("A store badge on each Heroic tile")
        }

        QQC2.CheckBox {
            id: showFilterBar
            text: i18n("The launcher filter bar above the grid")
        }

        QQC2.CheckBox {
            id: showLauncherTiles
            text: i18n("The launchers themselves, first in the grid")
        }

        QQC2.Label {
            text: i18n("Every launcher that was found gets a tile of its own.")
            wrapMode: Text.WordWrap
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            opacity: 0.7
            font: Kirigami.Theme.smallFont
        }

        Item { Kirigami.FormData.isSection: true }

        // -- ordering ---------------------------------------------------------

        QQC2.ComboBox {
            id: sortMode
            Kirigami.FormData.label: i18n("Sort by:")
            textRole: "label"
            model: [
                { value: "recent", label: i18n("Recently played") },
                { value: "name", label: i18n("Name") },
                { value: "playtime", label: i18n("Time played") }
            ]
            currentIndex: page.optionIndex(model, page.cfg_sortMode)
            onActivated: (index) => {
                page.cfg_sortMode = model[index].value;
                currentIndex = Qt.binding(() => page.optionIndex(model, page.cfg_sortMode));
            }
        }

        QQC2.CheckBox {
            id: favoritesFirst
            text: i18n("Show favourites first")
        }

        Item { Kirigami.FormData.isSection: true }

        // -- behaviour --------------------------------------------------------

        QQC2.CheckBox {
            id: closeOnLaunch
            Kirigami.FormData.label: i18n("On launch:")
            text: i18n("Close the popup")
        }

        Item { Kirigami.FormData.isSection: true }

        // -- advanced ---------------------------------------------------------

        QQC2.ToolButton {
            id: advancedToggle
            checkable: true
            text: i18n("Advanced")
            icon.name: checked ? "go-down-symbolic" : "go-next-symbolic"
        }

        QQC2.CheckBox {
            id: showAdvancedActions
            Kirigami.FormData.label: i18n("Context menu:")
            visible: advancedToggle.checked
            text: i18n("Offer “Copy game key”")
        }

        QQC2.Label {
            visible: advancedToggle.checked
            text: i18n("The key identifies a game in a bug report.")
            wrapMode: Text.WordWrap
            opacity: 0.7
            font: Kirigami.Theme.smallFont
        }

        QQC2.TextField {
            id: pythonPath
            Kirigami.FormData.label: i18n("Python interpreter:")
            visible: advancedToggle.checked
            Kirigami.FormData.labelAlignment: Qt.AlignVCenter
            placeholderText: "python3"
        }

        QQC2.Label {
            visible: advancedToggle.checked
            text: i18n("Only needs changing where python3 is not on the session's PATH.")
            wrapMode: Text.WordWrap
            opacity: 0.7
            font: Kirigami.Theme.smallFont
        }
    }
}
