// SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * One game: cover art, an optional title, a provider badge, a store badge and a
 * favourite star.
 *
 * Art falls back portrait -> landscape -> icon -> a generated placeholder. The
 * Image element reports a load failure asynchronously, so the fallback is driven
 * by status changes rather than by checking the URLs up front.
 *
 * A launcher tile (Steam, Heroic, ...) is the same delegate with a banner that
 * ships with the widget rather than one from a launcher's cache. A provider
 * with no bundled banner falls back to its icon and name on a themed plate.
 */
import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents

Item {
    id: tile

    required property var game
    // Set by the grid from the backend's marker. A launcher tile carries no
    // badge or star, and falls back to its icon when it has no banner.
    readonly property bool isLauncher:
        !!(game && game.extra && game.extra.is_launcher)
    // The launcher's own freedesktop icon name, which the backend sends along
    // with the entry; the provider badge is the sensible fallback.
    readonly property string launcherIcon:
        (game && game.extra && game.extra.icon) ? game.extra.icon : providerIcon
    property int tileWidth: 120
    property real aspectRatio: 1.5          // portrait 2:3
    property bool showTitle: false
    property bool showBadge: true
    // The store badge has a setting of its own: it is only ever on Heroic
    // tiles, so it is worth turning off separately from the launcher badge.
    property bool showStoreBadge: true
    property bool favorite: false
    // The grid owns the selection and keyboard handling, so the tile is told
    // whether it is current rather than taking focus itself. Two things fighting
    // over focus is how the mouse and the arrow keys end up disagreeing.
    property bool highlighted: false
    // Freedesktop icon name for the launcher, resolved by the caller from the
    // scan report so this file needs no table of launcher names.
    property string providerIcon: "applications-games"

    // Short name of the store a Heroic game came from, for the top-right badge.
    // Heroic is one provider over four stores, so its provider icon alone does
    // not say whether a game is an Epic, GOG, Amazon or sideloaded one. Stores
    // are a provider-internal idea the backend contract says nothing about, so
    // the labels are spelled out here, as they are in FilterBar; a store with no
    // label gets no badge rather than a raw id over the cover art.
    readonly property string storeLabel: {
        if (!game || tile.isLauncher || game.provider !== "heroic") {
            return "";
        }
        switch (game.store) {
        case "epic":     return i18nc("@label Epic Games, on a cover-art badge", "EPIC");
        case "gog":      return i18nc("@label GOG, on a cover-art badge", "GOG");
        case "amazon":   return i18nc("@label Amazon Games, on a cover-art badge", "AMZN");
        case "sideload": return i18nc("@label a sideloaded game, on a cover-art badge", "LOCAL");
        }
        return "";
    }
    // Spelled-out store name, for the tooltip.
    readonly property string storeName: {
        if (tile.storeLabel.length === 0) {
            return "";
        }
        switch (game.store) {
        case "epic":     return i18n("Epic Games");
        case "gog":      return i18n("GOG");
        case "amazon":   return i18n("Amazon Games");
        case "sideload": return i18n("Sideloaded");
        }
        return "";
    }

    signal activated()
    // `position` is in tile coordinates for a right-click, and null when the
    // menu was asked for from the keyboard and there is no cursor to follow.
    signal contextRequested(var position)

    readonly property int artHeight: Math.round(tileWidth * aspectRatio)

    // Candidate art URLs, best first; index advances when one fails to load.
    readonly property var artCandidates: {
        const art = game && game.art ? game.art : {};
        const candidates = [];
        if (art.portrait) candidates.push(art.portrait);
        if (art.landscape && art.landscape !== art.portrait) candidates.push(art.landscape);
        if (art.icon) candidates.push(art.icon);
        return candidates;
    }
    property int artIndex: 0
    readonly property bool artExhausted: artIndex >= artCandidates.length

    // A stable colour per game, so the placeholder does not change between runs.
    readonly property color placeholderColor: {
        const key = game && game.key ? game.key : "";
        let hash = 0;
        for (let i = 0; i < key.length; ++i) {
            hash = ((hash << 5) - hash + key.charCodeAt(i)) | 0;
        }
        return Qt.hsla(Math.abs(hash % 360) / 360, 0.45, 0.38, 1.0);
    }

    readonly property string initials: {
        const title = (game && game.title ? game.title : "?").trim();
        const words = title.split(/\s+/).filter(w => w.length > 0);
        if (words.length === 0) return "?";
        if (words.length === 1) return words[0].substring(0, 2).toUpperCase();
        return (words[0][0] + words[1][0]).toUpperCase();
    }

    implicitWidth: tileWidth
    implicitHeight: artHeight + (showTitle ? titleLabel.implicitHeight + Kirigami.Units.smallSpacing : 0)

    Rectangle {
        id: artFrame
        width: tile.tileWidth
        height: tile.artHeight
        radius: Kirigami.Units.cornerRadius
        clip: true
        color: tile.isLauncher
            ? Kirigami.Theme.alternateBackgroundColor
            : tile.placeholderColor

        // Fallback for a launcher with no bundled banner: its icon, and its
        // name unless the grid is labelling tiles underneath anyway.
        Column {
            anchors.centerIn: parent
            width: parent.width - Kirigami.Units.largeSpacing * 2
            spacing: Kirigami.Units.smallSpacing
            visible: tile.isLauncher && coverArt.status !== Image.Ready

            Kirigami.Icon {
                anchors.horizontalCenter: parent.horizontalCenter
                source: tile.launcherIcon
                width: Math.round(Math.min(tile.tileWidth, tile.artHeight) * 0.5)
                height: width
            }

            PlasmaComponents.Label {
                visible: !tile.showTitle
                width: parent.width
                text: tile.game ? tile.game.title : ""
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
                font.bold: true
            }
        }

        // Placeholder, visible until (and unless) real art loads.
        PlasmaComponents.Label {
            anchors.centerIn: parent
            text: tile.initials
            visible: !tile.isLauncher && coverArt.status !== Image.Ready
            color: "white"
            font.pointSize: Math.max(10, Math.round(tile.tileWidth / 4))
            font.bold: true
            opacity: 0.85
        }

        Image {
            id: coverArt
            anchors.fill: parent
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            cache: true
            smooth: true
            // 2x for sharpness on HiDPI without decoding the full-size asset.
            sourceSize.width: tile.tileWidth * 2
            sourceSize.height: tile.artHeight * 2
            source: tile.artExhausted ? "" : tile.artCandidates[tile.artIndex]
            visible: status === Image.Ready

            onStatusChanged: {
                if (status === Image.Error && !tile.artExhausted) {
                    tile.artIndex += 1;
                }
            }
        }

        PlasmaComponents.BusyIndicator {
            anchors.centerIn: parent
            running: coverArt.status === Image.Loading
            visible: running
            width: Kirigami.Units.iconSizes.small
            height: width
        }

        Kirigami.Icon {
            id: badge
            // Never on a launcher tile: the badge would repeat the big icon.
            visible: tile.showBadge && !!tile.game && !tile.isLauncher
            source: tile.providerIcon
            width: Kirigami.Units.iconSizes.small
            height: width
            anchors {
                right: parent.right
                bottom: parent.bottom
                margins: Kirigami.Units.smallSpacing
            }
            // A dark plate keeps light icons readable over bright cover art.
            Rectangle {
                anchors.centerIn: parent
                width: parent.width + Kirigami.Units.smallSpacing
                height: width
                radius: width / 2
                color: Qt.rgba(0, 0, 0, 0.55)
                z: -1
            }
        }

        // Which Heroic store a game came from. Top right, so it clears the
        // favourite star (top left) and the provider badge (bottom right).
        Rectangle {
            id: storeBadge
            visible: tile.showStoreBadge && tile.storeLabel.length > 0
            // A dark plate, like the provider badge's, so the text stays
            // readable over bright cover art.
            color: Qt.rgba(0, 0, 0, 0.55)
            width: storeBadgeLabel.implicitWidth + Kirigami.Units.smallSpacing * 2
            height: storeBadgeLabel.implicitHeight + Kirigami.Units.smallSpacing
            radius: height / 2
            anchors {
                right: parent.right
                top: parent.top
                margins: Kirigami.Units.smallSpacing
            }

            PlasmaComponents.Label {
                id: storeBadgeLabel
                anchors.centerIn: parent
                text: tile.storeLabel
                color: "white"
                font.pointSize: Kirigami.Theme.smallFont.pointSize
                font.bold: true
            }
        }

        Kirigami.Icon {
            id: star
            visible: tile.favorite
            source: "favorite"
            width: Kirigami.Units.iconSizes.small
            height: width
            anchors {
                left: parent.left
                top: parent.top
                margins: Kirigami.Units.smallSpacing
            }
            Rectangle {
                anchors.centerIn: parent
                width: parent.width + Kirigami.Units.smallSpacing
                height: width
                radius: width / 2
                color: Qt.rgba(0, 0, 0, 0.55)
                z: -1
            }
        }

        // Dim uninstalled entries so they read as unavailable at a glance.
        Rectangle {
            anchors.fill: parent
            color: Qt.rgba(0, 0, 0, 0.45)
            visible: tile.game && tile.game.installed === false
        }

        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: "transparent"
            border.width: 2
            border.color: Kirigami.Theme.highlightColor
            visible: tile.highlighted || hoverHandler.hovered
        }
    }

    PlasmaComponents.Label {
        id: titleLabel
        visible: tile.showTitle
        anchors {
            top: artFrame.bottom
            topMargin: Kirigami.Units.smallSpacing
            left: parent.left
            right: parent.right
        }
        text: tile.game ? tile.game.title : ""
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideRight
        maximumLineCount: 2
        wrapMode: Text.Wrap
        font.pointSize: Kirigami.Theme.smallFont.pointSize
    }

    HoverHandler {
        id: hoverHandler
        cursorShape: Qt.PointingHandCursor
    }

    TapHandler {
        acceptedButtons: Qt.LeftButton
        onTapped: tile.activated()
    }

    TapHandler {
        acceptedButtons: Qt.RightButton
        onTapped: (eventPoint) => tile.contextRequested(eventPoint.position)
    }

    PlasmaComponents.ToolTip {
        text: {
            if (!tile.game) {
                return "";
            }
            if (tile.isLauncher) {
                return i18nc("@info:tooltip open a game launcher", "Open %1", tile.game.title);
            }
            return tile.storeName.length > 0
                ? i18nc("@info:tooltip game title and the store it came from",
                        "%1 (%2)", tile.game.title, tile.storeName)
                : tile.game.title;
        }
        visible: hoverHandler.hovered && (tile.isLauncher || !tile.showTitle)
    }
}
