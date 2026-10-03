// SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Providers page: one card per launcher, with its settings form built from the
 * schema the backend reports. No provider is named anywhere in this file — that
 * is the point of `settings_schema` (plan section 5).
 *
 * The page owns `providerConfig`, a JSON object of {provider: {key: value}}.
 * Only values that differ from the schema default are stored, so a default that
 * changes in a later version still reaches users who never touched the setting,
 * and an untouched configuration stays `{}`.
 */
import QtCore
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    id: page

    property string cfg_providerConfig: "{}"
    property string cfg_providerConfigDefault: "{}"

    // Parsed form of cfg_providerConfig; the forms read and write this.
    property var settings: ({})
    // Providers as last reported by `run.py providers`.
    property var providerList: []
    // provider id -> game count, from the report in `run.py list`.
    property var counts: ({})
    property string loadError: ""

    // Set while this page is the one writing cfg_providerConfig, so its own
    // writes are not mistaken for an external reset (the Defaults button).
    property bool writingConfig: false

    readonly property string homePath: {
        const home = String(StandardPaths.writableLocation(StandardPaths.HomeLocation));
        return home.startsWith("file://") ? home.substring(7) : home;
    }

    // -- config <-> local model ----------------------------------------------

    function loadFromConfig() {
        let parsed = {};
        try {
            const candidate = JSON.parse(page.cfg_providerConfig || "{}");
            if (candidate && typeof candidate === "object" && !Array.isArray(candidate)) {
                parsed = candidate;
            }
        } catch (error) {
            console.warn("gameshelf: providerConfig is not valid JSON, starting from defaults");
        }
        page.settings = parsed;
    }

    function storeConfig() {
        page.writingConfig = true;
        page.cfg_providerConfig = JSON.stringify(page.settings);
        page.writingConfig = false;
    }

    onCfg_providerConfigChanged: {
        if (!page.writingConfig) {
            page.loadFromConfig();
        }
    }

    function specFor(providerId, key) {
        for (const provider of page.providerList) {
            if (provider.id !== providerId) {
                continue;
            }
            for (const spec of provider.settings_schema) {
                if (spec.key === key) {
                    return spec;
                }
            }
        }
        return null;
    }

    function valueFor(providerId, spec) {
        const stored = page.settings[providerId];
        if (stored && stored[spec.key] !== undefined) {
            return stored[spec.key];
        }
        return spec.default;
    }

    function setValue(providerId, key, value) {
        const next = Object.assign({}, page.settings);
        const forProvider = Object.assign({}, next[providerId] || {});
        forProvider[key] = value;

        // Drop anything back at its default, so the stored object stays minimal
        // and providers keep following default changes they were never told
        // about explicitly.
        for (const storedKey of Object.keys(forProvider)) {
            const spec = page.specFor(providerId, storedKey);
            if (spec && JSON.stringify(forProvider[storedKey]) === JSON.stringify(spec.default)) {
                delete forProvider[storedKey];
            }
        }

        if (Object.keys(forProvider).length === 0) {
            delete next[providerId];
        } else {
            next[providerId] = forProvider;
        }
        page.settings = next;
        page.storeConfig();
    }

    function prettyPath(path) {
        const text = String(path);
        return page.homePath.length > 0 && text.startsWith(page.homePath)
            ? "~" + text.substring(page.homePath.length)
            : text;
    }

    function statusFor(provider) {
        if (!page.valueFor(provider.id, { key: "enabled", default: provider.default_enabled })) {
            return i18n("Disabled");
        }
        if (!provider.detect || !provider.detect.available) {
            return provider.detect && provider.detect.message
                ? String(provider.detect.message)
                : i18n("Not detected on this system");
        }
        const paths = (provider.detect.paths || []).map(page.prettyPath).join(", ");
        const count = page.counts[provider.id];
        if (count === undefined) {
            return i18n("Found: %1", paths);
        }
        return i18n("Found: %1 — %2", paths, i18np("%1 game", "%1 games", count));
    }

    // -- backend --------------------------------------------------------------

    function reload() {
        page.loadError = "";
        backend.providers();
        backend.list(false);
    }

    Backend {
        id: backend

        // Query with what the user has typed, not with what was last applied.
        providerConfigJson: page.cfg_providerConfig

        onProvidersReady: (payload) => {
            page.providerList = payload.providers || [];
        }

        onListReady: (payload) => {
            const tally = {};
            for (const report of (payload.providers || [])) {
                if (report.enabled && report.available) {
                    tally[report.id] = report.count;
                }
            }
            page.counts = tally;
        }

        onFailed: (message) => {
            page.loadError = message;
        }
    }

    Component.onCompleted: {
        page.loadFromConfig();
        page.reload();
    }

    // -- layout ---------------------------------------------------------------

    ColumnLayout {
        spacing: Kirigami.Units.largeSpacing

        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing

            QQC2.Label {
                Layout.fillWidth: true
                text: i18n("Each launcher can be turned on or off independently.")
                wrapMode: Text.WordWrap
                opacity: 0.7
            }

            QQC2.BusyIndicator {
                running: backend.busy
                visible: running
                implicitWidth: Kirigami.Units.iconSizes.small
                implicitHeight: implicitWidth
            }

            QQC2.Button {
                text: i18n("Re-detect")
                icon.name: "view-refresh"
                enabled: !backend.busy
                onClicked: page.reload()
            }
        }

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            type: Kirigami.MessageType.Error
            visible: page.loadError.length > 0
            text: page.loadError
        }

        Kirigami.PlaceholderMessage {
            Layout.fillWidth: true
            visible: page.providerList.length === 0 && !backend.busy && page.loadError.length === 0
            icon.name: "input-gaming"
            text: i18n("No launcher modules were found")
        }

        Repeater {
            model: page.providerList

            delegate: Kirigami.AbstractCard {
                required property var modelData

                Layout.fillWidth: true

                readonly property var provider: modelData
                readonly property bool providerEnabled:
                    page.valueFor(provider.id,
                                  { key: "enabled", default: provider.default_enabled }) === true

                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.smallSpacing

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing

                        Kirigami.Icon {
                            source: provider.icon || "applications-games"
                            implicitWidth: Kirigami.Units.iconSizes.medium
                            implicitHeight: implicitWidth
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0

                            Kirigami.Heading {
                                Layout.fillWidth: true
                                level: 3
                                text: provider.name || provider.id
                                elide: Text.ElideRight
                            }

                            QQC2.Label {
                                Layout.fillWidth: true
                                text: page.statusFor(provider)
                                wrapMode: Text.WordWrap
                                opacity: 0.7
                                font: Kirigami.Theme.smallFont
                            }
                        }

                        QQC2.Switch {
                            id: enableSwitch
                            checked: providerEnabled
                            onToggled: {
                                page.setValue(provider.id, "enabled", checked);
                                checked = Qt.binding(() => providerEnabled);
                            }
                        }
                    }

                    Kirigami.Separator {
                        Layout.fillWidth: true
                        visible: basicFields.count > 0 || advancedToggle.visible
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: Kirigami.Units.smallSpacing
                        spacing: Kirigami.Units.smallSpacing
                        enabled: providerEnabled

                        Repeater {
                            id: basicFields
                            // "enabled" is the switch in the header above.
                            model: (provider.settings_schema || []).filter(
                                spec => !spec.advanced && spec.key !== "enabled")

                            delegate: SettingField {
                                required property var modelData

                                Layout.fillWidth: true
                                spec: modelData
                                value: page.valueFor(provider.id, modelData)
                                onEdited: (newValue) => page.setValue(provider.id, modelData.key, newValue)
                            }
                        }

                        QQC2.ToolButton {
                            id: advancedToggle
                            visible: checkable
                            checkable: (provider.settings_schema || []).some(spec => spec.advanced)
                            text: i18n("Advanced")
                            icon.name: checked ? "go-down-symbolic" : "go-next-symbolic"
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.leftMargin: Kirigami.Units.gridUnit
                            spacing: Kirigami.Units.smallSpacing
                            visible: advancedToggle.checked

                            Repeater {
                                id: advancedFields
                                model: (provider.settings_schema || []).filter(spec => spec.advanced)

                                delegate: SettingField {
                                    required property var modelData

                                    Layout.fillWidth: true
                                    spec: modelData
                                    value: page.valueFor(provider.id, modelData)
                                    onEdited: (newValue) => page.setValue(provider.id, modelData.key, newValue)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
