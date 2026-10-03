// SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * One row of a provider's settings form, rendered from a SettingSpec.
 *
 * The backend owns the schema (see plan section 5), so this file is the only
 * place that knows how a `type` maps to a control. Adding a provider never
 * touches QML; adding a *setting type* touches exactly this switch.
 *
 * The control is bound to `value` for its initial state and re-binds itself
 * after every edit, so a reset from outside (the dialog's Defaults button)
 * still reaches the widget.
 */
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import QtQuick.Dialogs as Dialogs
import org.kde.kirigami as Kirigami

ColumnLayout {
    id: field

    required property var spec      // one entry of settings_schema
    required property var value     // its current value

    signal edited(var newValue)

    readonly property string helpText: spec && spec.help ? String(spec.help) : ""

    /* ComboBox.indexOfValue and currentValue resolve `valueRole` through the
     * delegate model, which a plain array of JS objects does not supply, so
     * every enum would sit on its first option. Look the option up directly. */
    function optionIndex(value) {
        const options = field.spec.options || [];
        for (let index = 0; index < options.length; ++index) {
            if (options[index].value === value) {
                return index;
            }
        }
        return 0;
    }

    function optionValue(index) {
        const options = field.spec.options || [];
        return index >= 0 && index < options.length ? options[index].value : undefined;
    }

    spacing: 0

    Loader {
        Layout.fillWidth: true
        sourceComponent: {
            switch (field.spec.type) {
            case "bool": return boolField;
            case "enum": return enumField;
            case "int": return intField;
            case "path": return pathField;
            case "stringlist": return stringListField;
            default: return stringField;
            }
        }
    }

    QQC2.Label {
        Layout.fillWidth: true
        Layout.leftMargin: field.spec.type === "bool" ? Kirigami.Units.gridUnit : 0
        visible: field.helpText.length > 0
        text: field.helpText
        wrapMode: Text.WordWrap
        opacity: 0.7
        font: Kirigami.Theme.smallFont
    }

    // -- controls -------------------------------------------------------------

    Component {
        id: boolField

        QQC2.CheckBox {
            id: checkBox
            text: field.spec.label
            checked: field.value === true
            onToggled: {
                field.edited(checked);
                // The click broke the binding above; put it back so an external
                // reset still shows up.
                checked = Qt.binding(() => field.value === true);
            }
        }
    }

    Component {
        id: enumField

        RowLayout {
            spacing: Kirigami.Units.smallSpacing

            QQC2.Label {
                text: field.spec.label
                elide: Text.ElideRight
            }

            QQC2.ComboBox {
                id: comboBox
                Layout.fillWidth: true
                model: field.spec.options || []
                textRole: "label"
                currentIndex: field.optionIndex(field.value)
                onActivated: (index) => {
                    field.edited(field.optionValue(index));
                    currentIndex = Qt.binding(() => field.optionIndex(field.value));
                }
            }
        }
    }

    Component {
        id: intField

        RowLayout {
            spacing: Kirigami.Units.smallSpacing

            QQC2.Label {
                Layout.fillWidth: true
                text: field.spec.label
                elide: Text.ElideRight
            }

            QQC2.SpinBox {
                id: spinBox
                from: 0
                to: 99999
                value: Number(field.value) || 0
                onValueModified: {
                    field.edited(value);
                    value = Qt.binding(() => Number(field.value) || 0);
                }
            }
        }
    }

    Component {
        id: stringField

        RowLayout {
            spacing: Kirigami.Units.smallSpacing

            QQC2.Label {
                text: field.spec.label
                elide: Text.ElideRight
            }

            QQC2.TextField {
                Layout.fillWidth: true
                text: field.value === undefined || field.value === null ? "" : String(field.value)
                onTextEdited: field.edited(text)
            }
        }
    }

    Component {
        id: stringListField

        RowLayout {
            spacing: Kirigami.Units.smallSpacing

            QQC2.Label {
                text: field.spec.label
                elide: Text.ElideRight
            }

            QQC2.TextField {
                Layout.fillWidth: true
                placeholderText: i18n("Comma-separated")
                text: Array.isArray(field.value) ? field.value.join(", ") : String(field.value || "")
                onTextEdited: field.edited(
                    text.split(",").map(part => part.trim()).filter(part => part.length > 0))
            }
        }
    }

    Component {
        id: pathField

        RowLayout {
            spacing: Kirigami.Units.smallSpacing

            QQC2.Label {
                text: field.spec.label
                elide: Text.ElideRight
            }

            QQC2.TextField {
                id: pathInput
                Layout.fillWidth: true
                text: field.value === undefined || field.value === null ? "" : String(field.value)
                onTextEdited: field.edited(text)
            }

            QQC2.Button {
                icon.name: "document-open-folder"
                display: QQC2.AbstractButton.IconOnly
                onClicked: folderDialog.open()

                QQC2.ToolTip.text: i18n("Choose a folder…")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }

            Dialogs.FolderDialog {
                id: folderDialog
                title: field.spec.label
                // selectedFolder is a url; the backend wants a plain path.
                onAccepted: {
                    const picked = String(selectedFolder);
                    field.edited(picked.startsWith("file://") ? picked.substring(7) : picked);
                }
            }
        }
    }
}
