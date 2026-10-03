// SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Scrollable grid of GameTiles. Purely presentational: it takes an already
 * filtered and sorted array and reports activations upward.
 */
import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

QQC2.ScrollView {
    id: root

    property var games: []
    property int tileWidth: 120
    property real aspectRatio: 1.5
    property bool showTitles: false
    property bool showBadges: true
    property bool showStoreBadges: true
    // Game keys the user has starred, and the launcher icons by provider id.
    property var favorites: []
    property var providerIcons: ({})

    signal gameActivated(var game)
    signal gameContextRequested(var game, var tileItem, var position)
    // Raised when the grid is at its top edge and the user presses Up, so the
    // caller can hand focus back to the search field.
    signal escapedUpward()

    contentWidth: availableWidth
    clip: true

    // The grid never scrolls sideways; without this the GridView's own content
    // width leaks out and produces a stray horizontal scrollbar.
    QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AlwaysOff
    QQC2.ScrollBar.vertical.policy: QQC2.ScrollBar.AsNeeded

    function focusFirst() {
        if (root.games.length === 0) {
            return false;
        }
        grid.currentIndex = 0;
        grid.forceActiveFocus();
        return true;
    }

    /* Focus without disturbing the selection, for handing focus back after a
     * popup closes. focusFirst() would jump the selection to the top. */
    function takeFocus() {
        grid.forceActiveFocus();
    }

    function currentGame() {
        return grid.currentIndex >= 0 && grid.currentIndex < root.games.length
            ? root.games[grid.currentIndex]
            : null;
    }

    GridView {
        id: grid

        model: root.games
        cacheBuffer: cellHeight * 4

        readonly property int spacing: Kirigami.Units.largeSpacing
        readonly property int tileHeight:
            Math.round(root.tileWidth * root.aspectRatio)
            + (root.showTitles ? Kirigami.Units.gridUnit * 2 : 0)

        cellWidth: root.tileWidth + spacing
        cellHeight: tileHeight + spacing

        // Centre the tiles rather than leaving a ragged gap on the right.
        readonly property int columns: Math.max(1, Math.floor(width / cellWidth))
        leftMargin: Math.max(0, Math.floor((width - columns * cellWidth) / 2))

        keyNavigationEnabled: true
        keyNavigationWraps: false
        highlightFollowsCurrentItem: true
        focus: true
        // Tab has to be able to reach the grid: the plan's cycle is
        // header -> filter chips -> grid.
        activeFocusOnTab: true

        // Filtering rebuilds the array under us; without this the selection
        // would keep whatever index it had and point at a different game.
        onCountChanged: if (currentIndex >= count) currentIndex = count - 1

        Keys.onUpPressed: (event) => {
            if (grid.currentIndex < grid.columns) {
                root.escapedUpward();
            } else {
                event.accepted = false;
            }
        }

        delegate: Item {
            id: cell
            required property int index
            required property var modelData

            width: grid.cellWidth
            height: grid.cellHeight

            readonly property bool current: GridView.isCurrentItem && grid.activeFocus

            GameTile {
                id: gameTile
                anchors.horizontalCenter: parent.horizontalCenter
                game: cell.modelData
                tileWidth: root.tileWidth
                aspectRatio: root.aspectRatio
                showTitle: root.showTitles
                showBadge: root.showBadges
                showStoreBadge: root.showStoreBadges
                favorite: root.favorites.indexOf(cell.modelData.key) !== -1
                providerIcon: root.providerIcons[cell.modelData.provider] || "applications-games"
                highlighted: cell.current

                onActivated: {
                    grid.currentIndex = cell.index;
                    grid.forceActiveFocus();
                    root.gameActivated(cell.modelData);
                }
                onContextRequested: (position) => {
                    grid.currentIndex = cell.index;
                    grid.forceActiveFocus();
                    root.gameContextRequested(cell.modelData, gameTile, position);
                }
            }
        }

        Keys.onReturnPressed: {
            const game = root.currentGame();
            if (game) {
                root.gameActivated(game);
            }
        }
        Keys.onEnterPressed: {
            const game = root.currentGame();
            if (game) {
                root.gameActivated(game);
            }
        }
        Keys.onMenuPressed: {
            const game = root.currentGame();
            if (game) {
                root.gameContextRequested(game, grid.currentItem, null);
            }
        }
    }
}
