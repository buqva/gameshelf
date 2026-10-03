// SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Game Shelf: every installed game from Steam, Heroic and Lutris in one grid.
 *
 * The backend produces data and this file renders it. Everything that persists —
 * favourites, the hidden list, the sort mode — is written here and nowhere else;
 * the popup asks by signal. Filtering and sorting themselves live in
 * code/gamelist.js so this file stays about state and actions.
 */
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami
import org.kde.plasma.core as PlasmaCore

PlasmoidItem {
    id: root

    property var games: []
    // The launcher applications themselves, kept apart from the games so the
    // popup can pin them first and the tooltip can still count only games.
    property var launchers: []
    property var providerReports: []
    property var errors: []
    property bool loaded: false

    readonly property var favorites: Plasmoid.configuration.favorites || []

    Plasmoid.icon: Plasmoid.configuration.panelIcon || "input-gaming"

    toolTipMainText: i18n("Game Shelf")
    toolTipSubText: loaded
        ? i18np("%1 game", "%1 games", games.length)
        : i18n("Loading…")

    preferredRepresentation: compactRepresentation
    compactRepresentation: CompactRepresentation {
        plasmoidItem: root
    }

    switchWidth: Kirigami.Units.gridUnit * 14
    switchHeight: Kirigami.Units.gridUnit * 10

    Backend {
        id: backend

        onListReady: (payload) => {
            root.applyPayload(payload);
        }

        onFailed: (message) => {
            root.errors = [{ provider: "backend", message: message, detail: null }];
            root.loaded = true;
            console.warn("gameshelf:", message);
        }
    }

    function applyPayload(payload) {
        const hidden = Plasmoid.configuration.hiddenGames || [];
        const keep = entries => hidden.length === 0
            ? entries
            : entries.filter(entry => hidden.indexOf(entry.key) === -1);
        root.games = keep(payload.games || []);
        // Launcher tiles cannot be hidden from the grid's menu, but an older
        // hidden list or a hand-edited config may still name one, and the
        // Hidden Games page has to be able to bring it back.
        root.launchers = keep(payload.launchers || []);
        root.providerReports = payload.providers || [];
        root.errors = payload.errors || [];
        root.loaded = true;
    }

    function refresh(noCache) {
        backend.list(noCache === true);
    }

    function launchGame(game) {
        if (!game) {
            return;
        }
        if (game.launch_uri) {
            Qt.openUrlExternally(game.launch_uri);
        } else if (game.launch_cmd && game.launch_cmd.length > 0) {
            backend.launch(game.key);
        } else {
            console.warn("gameshelf: no way to launch", game.key);
            return;
        }
        if (Plasmoid.configuration.closeOnLaunch) {
            root.expanded = false;
        }
    }

    function toggleFavorite(game) {
        if (!game) {
            return;
        }
        const current = Plasmoid.configuration.favorites || [];
        Plasmoid.configuration.favorites = current.indexOf(game.key) === -1
            ? current.concat([game.key])
            : current.filter(key => key !== game.key);
    }

    function hideGame(game) {
        if (!game) {
            return;
        }
        const hidden = Plasmoid.configuration.hiddenGames || [];
        if (hidden.indexOf(game.key) === -1) {
            Plasmoid.configuration.hiddenGames = hidden.concat([game.key]);
        }
        // Drop it from the view now rather than waiting for the next scan: the
        // backend does not know about hidden games and would return it again.
        root.games = root.games.filter(entry => entry.key !== game.key);
    }

    function openInstallFolder(game) {
        if (game && game.install_path) {
            Qt.openUrlExternally("file://" + game.install_path);
        }
    }

    function copyKey(game) {
        if (!game) {
            return;
        }
        // QML has no clipboard API; a TextEdit's own copy() is the way in.
        clipboardHelper.text = game.key;
        clipboardHelper.selectAll();
        clipboardHelper.copy();
        clipboardHelper.deselect();
    }

    function openConfiguration() {
        Plasmoid.internalAction("configure").trigger();
    }

    TextEdit {
        id: clipboardHelper
        visible: false
    }

    fullRepresentation: FullRepresentation {
        Layout.preferredWidth: Kirigami.Units.gridUnit * 40
        Layout.preferredHeight: Kirigami.Units.gridUnit * 32
        Layout.minimumWidth: Kirigami.Units.gridUnit * 16
        Layout.minimumHeight: Kirigami.Units.gridUnit * 12

        games: root.games
        launchers: Plasmoid.configuration.showLauncherTiles ? root.launchers : []
        providerReports: root.providerReports
        errors: root.errors
        favorites: root.favorites
        busy: backend.busy
        loaded: root.loaded

        onRefreshRequested: root.refresh(true)
        onGameActivated: (game) => root.launchGame(game)
        onFavoriteToggled: (game) => root.toggleFavorite(game)
        onHideRequested: (game) => root.hideGame(game)
        onInstallFolderRequested: (game) => root.openInstallFolder(game)
        onKeyCopyRequested: (game) => root.copyKey(game)
        onLauncherTilesHideRequested: Plasmoid.configuration.showLauncherTiles = false
        onConfigureRequested: root.openConfiguration()
        onCloseRequested: root.expanded = false
    }

    // The warm cache makes a scan on every open cheap, so the list is always
    // current without needing a file watcher.
    onExpandedChanged: {
        if (expanded) {
            root.refresh(false);
            // Typing has to work the moment the popup appears, and the popup is
            // not ready to take focus in the same frame it is shown.
            focusSearchTimer.restart();
        }
    }

    Timer {
        id: focusSearchTimer
        interval: Kirigami.Units.shortDuration
        onTriggered: {
            if (root.expanded && root.fullRepresentationItem) {
                root.fullRepresentationItem.focusSearch();
            }
        }
    }

    Connections {
        target: Plasmoid.configuration

        function onProviderConfigChanged() { root.refresh(true); }

        // Un-hiding from the config page has to bring the game back without a
        // manual refresh; the scan cache makes this nearly free.
        function onHiddenGamesChanged() { root.refresh(false); }
    }

    Component.onCompleted: root.refresh(false)
}
