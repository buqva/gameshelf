// SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * The popup: search and sort header, filter chips, an error banner, and the grid.
 *
 * This file owns the view state — the query and the selected chip — and derives
 * what the grid shows from it. Everything that outlives the popup (favourites,
 * the hidden list, the sort mode) lives in the plasmoid config and is changed by
 * signalling upward, so main.qml stays the only writer.
 */
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents
import "../code/gamelist.js" as GameList

ColumnLayout {
    id: root

    required property var games            // already minus the hidden ones
    // Launcher tiles to pin ahead of the games; empty when the user has the
    // option switched off, so this file never reads that setting itself.
    required property var launchers
    required property var providerReports
    required property var errors
    required property var favorites
    required property bool busy
    required property bool loaded

    signal refreshRequested()
    signal gameActivated(var game)
    signal favoriteToggled(var game)
    signal hideRequested(var game)
    signal installFolderRequested(var game)
    signal keyCopyRequested(var game)
    // Switching the launcher tiles off is a stored setting, so main.qml writes
    // it, in keeping with this file only ever asking.
    signal launcherTilesHideRequested()
    signal configureRequested()
    signal closeRequested()

    property string query: ""
    property string activeSource: ""

    readonly property var sources: GameList.sources(root.games, root.providerReports)

    // The chips are off by configuration, or there is only one source and so
    // nothing to choose between. Either way no chip can be reached, so the
    // stored filter must not keep narrowing the grid behind the user's back.
    readonly property bool filterBarVisible:
        Plasmoid.configuration.showFilterBar && root.sources.length > 1

    readonly property string effectiveSource:
        root.filterBarVisible ? root.activeSource : ""

    readonly property var visibleGames: GameList.visible(
        root.games,
        root.query,
        root.effectiveSource,
        Plasmoid.configuration.sortMode,
        root.favorites,
        Plasmoid.configuration.favoritesFirst)

    readonly property var visibleLaunchers: GameList.visibleLaunchers(
        root.launchers,
        root.query,
        root.effectiveSource)

    // What the grid actually shows: the launchers first, whatever the sort.
    readonly property var gridEntries:
        root.visibleLaunchers.concat(root.visibleGames)

    // Anything at all to show before the search box and chips narrow it down.
    // The empty states turn on this rather than on the game count, so a user
    // whose launchers are found but whose games are not still gets a grid.
    readonly property bool hasEntries:
        root.games.length > 0 || root.launchers.length > 0

    readonly property var providerIcons: {
        const icons = {};
        for (const report of root.providerReports) {
            icons[report.id] = report.icon || "applications-games";
        }
        return icons;
    }

    // True when every provider the backend knows about is switched off — a very
    // different situation from "you own no games", and it needs a different fix.
    readonly property bool noProvidersEnabled:
        root.providerReports.length > 0
        && !root.providerReports.some(report => report.enabled)

    spacing: Kirigami.Units.smallSpacing

    function focusSearch() {
        searchField.forceActiveFocus();
        searchField.selectAll();
    }

    /* Typing anywhere in the popup goes to the search field. Modifier-only and
     * navigation keys carry no text, so they fall through untouched. */
    Keys.onPressed: (event) => {
        if (searchField.activeFocus || event.text.length === 0
                || event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)) {
            return;
        }
        if (event.text.charCodeAt(0) < 0x20) {   // control characters, incl. Enter/Esc
            return;
        }
        searchField.forceActiveFocus();
        searchField.text += event.text;
        event.accepted = true;
    }

    Keys.onEscapePressed: (event) => {
        if (root.query.length > 0) {
            searchField.text = "";
        } else if (root.effectiveSource.length > 0) {
            root.activeSource = "";
        } else {
            root.closeRequested();
        }
        event.accepted = true;
    }

    // -- header ---------------------------------------------------------------

    RowLayout {
        Layout.fillWidth: true
        Layout.margins: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents.TextField {
            id: searchField
            Layout.fillWidth: true
            placeholderText: i18n("Search games…")
            clearButtonShown: true
            focus: true
            onTextChanged: root.query = text

            Keys.onDownPressed: grid.focusFirst()
            Keys.onReturnPressed: {
                // Enter from the search box launches the only remaining match,
                // which is the whole point of typing three letters.
                if (root.gridEntries.length >= 1) {
                    root.gameActivated(root.gridEntries[0]);
                }
            }
        }

        PlasmaComponents.ComboBox {
            id: sortCombo
            Layout.preferredWidth: Kirigami.Units.gridUnit * 9
            textRole: "label"
            model: [
                { value: "recent", label: i18n("Recently played") },
                { value: "name", label: i18n("Name") },
                { value: "playtime", label: i18n("Time played") }
            ]
            // ComboBox.valueRole does not resolve against a plain JS array, so
            // the index is looked up by hand. See CLAUDE.md.
            currentIndex: {
                for (let i = 0; i < model.length; ++i) {
                    if (model[i].value === Plasmoid.configuration.sortMode) {
                        return i;
                    }
                }
                return 0;
            }
            // Changing the sort here changes it for good: the popup's control
            // and the General page's "Sort by" are the same setting.
            onActivated: (index) => Plasmoid.configuration.sortMode = model[index].value

            PlasmaComponents.ToolTip { text: i18n("Sort order") }
        }

        PlasmaComponents.BusyIndicator {
            running: root.busy
            visible: running
            implicitWidth: Kirigami.Units.iconSizes.small
            implicitHeight: implicitWidth
        }

        PlasmaComponents.ToolButton {
            icon.name: "view-refresh"
            enabled: !root.busy
            onClicked: root.refreshRequested()
            PlasmaComponents.ToolTip { text: i18n("Refresh") }
        }

        PlasmaComponents.ToolButton {
            icon.name: "configure"
            onClicked: root.configureRequested()
            PlasmaComponents.ToolTip { text: i18n("Configure…") }
        }
    }

    // -- filter chips ---------------------------------------------------------

    FilterBar {
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.smallSpacing
        Layout.rightMargin: Kirigami.Units.smallSpacing
        visible: root.filterBarVisible

        sources: root.sources
        activeSource: root.activeSource
        onSourcePicked: (source) => root.activeSource = source
    }

    // -- error banner ---------------------------------------------------------

    Kirigami.InlineMessage {
        id: errorBanner
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.smallSpacing
        Layout.rightMargin: Kirigami.Units.smallSpacing
        type: Kirigami.MessageType.Warning
        visible: root.errors.length > 0 && !dismissed

        property bool dismissed: false
        property bool detailed: false

        text: {
            if (root.errors.length === 0) {
                return "";
            }
            if (errorBanner.detailed) {
                return root.errors
                    .map(error => i18nc("launcher and what went wrong", "%1: %2",
                                        error.provider, error.message))
                    .join("\n");
            }
            return root.errors.length === 1
                ? i18nc("launcher and what went wrong", "%1: %2",
                        root.errors[0].provider, root.errors[0].message)
                : i18np("%1 launcher could not be read.",
                        "%1 launchers could not be read.", root.errors.length);
        }

        actions: [
            Kirigami.Action {
                text: errorBanner.detailed ? i18n("Less") : i18n("Details")
                icon.name: "dialog-information"
                visible: root.errors.length > 1
                onTriggered: errorBanner.detailed = !errorBanner.detailed
            },
            Kirigami.Action {
                text: i18n("Dismiss")
                icon.name: "dialog-close"
                onTriggered: errorBanner.dismissed = true
            }
        ]

        // A later scan that reports something new deserves to be seen again.
        Connections {
            target: root
            function onErrorsChanged() {
                errorBanner.dismissed = false;
                errorBanner.detailed = false;
            }
        }
    }

    // -- grid and its empty states --------------------------------------------

    Item {
        Layout.fillWidth: true
        Layout.fillHeight: true

        // First load: nothing to show yet.
        PlasmaComponents.BusyIndicator {
            anchors.centerIn: parent
            running: visible
            visible: !root.loaded && !root.hasEntries
        }

        Kirigami.PlaceholderMessage {
            anchors.centerIn: parent
            width: parent.width - Kirigami.Units.gridUnit * 4
            visible: root.loaded && root.noProvidersEnabled
            icon.name: "dialog-cancel"
            text: i18n("No launchers are enabled")
            explanation: i18n("Turn one on to see your games.")
            helpfulAction: Kirigami.Action {
                text: i18n("Configure…")
                icon.name: "configure"
                onTriggered: root.configureRequested()
            }
        }

        Kirigami.PlaceholderMessage {
            anchors.centerIn: parent
            width: parent.width - Kirigami.Units.gridUnit * 4
            visible: root.loaded && !root.noProvidersEnabled && !root.hasEntries
            icon.name: "input-gaming"
            text: i18n("No games found")
            explanation: root.errors.length > 0
                ? i18n("No launcher could be read. Check the widget settings.")
                : i18n("No installed games were found in the enabled launchers.")
            helpfulAction: Kirigami.Action {
                text: i18n("Configure…")
                icon.name: "configure"
                onTriggered: root.configureRequested()
            }
        }

        Kirigami.PlaceholderMessage {
            anchors.centerIn: parent
            width: parent.width - Kirigami.Units.gridUnit * 4
            visible: root.hasEntries && root.gridEntries.length === 0
            icon.name: "system-search"
            text: root.query.length > 0
                ? i18n("No results for “%1”", root.query)
                : i18n("Nothing matches this filter")
            helpfulAction: Kirigami.Action {
                text: i18n("Clear filters")
                icon.name: "edit-clear-all"
                onTriggered: {
                    searchField.text = "";
                    root.activeSource = "";
                    root.focusSearch();
                }
            }
        }

        GameGrid {
            id: grid
            anchors.fill: parent
            visible: root.gridEntries.length > 0

            games: root.gridEntries
            favorites: root.favorites
            providerIcons: root.providerIcons
            tileWidth: Plasmoid.configuration.tileSize
            aspectRatio: Plasmoid.configuration.tileStyle === "landscape" ? (215 / 460) : 1.5
            showTitles: Plasmoid.configuration.showTitles
            showBadges: Plasmoid.configuration.showProviderBadge
            showStoreBadges: Plasmoid.configuration.showStoreBadge

            onGameActivated: (game) => root.gameActivated(game)
            onEscapedUpward: root.focusSearch()
            onGameContextRequested: (game, tileItem, position) => {
                contextMenu.game = game;
                // popup() with no arguments lands at the mouse cursor, which is
                // wrong when the menu was opened with the Menu key: anchor it to
                // the selected tile instead.
                if (position) {
                    contextMenu.popup(tileItem, position.x, position.y);
                } else {
                    contextMenu.popup(tileItem, 0, tileItem.height);
                }
            }
        }
    }

    // -- context menu ---------------------------------------------------------

    QQC2.Menu {
        id: contextMenu
        property var game: null

        // Without this the popup never takes focus when it is opened from code,
        // so the Menu key would open a menu the keyboard could not then use.
        focus: true

        // Qt does not hand focus back to the grid on its own, which would leave
        // the keyboard with nothing to drive after one context-menu action.
        onClosed: grid.takeFocus()

        readonly property bool isFavorite:
            game && root.favorites.indexOf(game.key) !== -1

        // A launcher tile gets a shorter menu. Starring it would do nothing
        // (it is pinned first already), hiding it would strand a "Steam" row
        // on the Hidden Games page, and it has no install folder. The switch
        // in the settings is how a launcher tile is turned off.
        readonly property bool isLauncher: GameList.isLauncher(game)

        /* No MenuSeparator anywhere in here: Qt 6's QQC2 menu does not skip one
         * during Down navigation, it just stops there, which makes every item
         * below the first separator unreachable from the keyboard. */

        QQC2.MenuItem {
            text: contextMenu.isLauncher ? i18n("Open") : i18n("Play")
            icon.name: contextMenu.isLauncher
                ? "window-new"
                : "media-playback-start"
            onTriggered: root.gameActivated(contextMenu.game)
        }

        QQC2.MenuItem {
            text: contextMenu.isFavorite
                ? i18n("Remove from favourites")
                : i18n("Add to favourites")
            icon.name: "favorite"
            visible: !contextMenu.isLauncher
            height: visible ? implicitHeight : 0
            onTriggered: root.favoriteToggled(contextMenu.game)
        }

        QQC2.MenuItem {
            text: i18n("Hide this game")
            icon.name: "view-hidden"
            visible: !contextMenu.isLauncher
            height: visible ? implicitHeight : 0
            onTriggered: root.hideRequested(contextMenu.game)
        }

        QQC2.MenuItem {
            text: i18n("Hide launcher tiles")
            icon.name: "view-hidden"
            visible: contextMenu.isLauncher
            height: visible ? implicitHeight : 0
            onTriggered: root.launcherTilesHideRequested()
        }

        QQC2.MenuItem {
            text: i18n("Open install folder")
            icon.name: "folder-open"
            visible: !contextMenu.isLauncher
            height: visible ? implicitHeight : 0
            enabled: contextMenu.game && !!contextMenu.game.install_path
            onTriggered: root.installFolderRequested(contextMenu.game)
        }

        QQC2.MenuItem {
            text: i18n("Copy game key")
            icon.name: "edit-copy"
            // For bug reports; off by default so the menu stays short.
            visible: Plasmoid.configuration.showAdvancedActions
            height: visible ? implicitHeight : 0
            onTriggered: root.keyCopyRequested(contextMenu.game)
        }
    }
}
