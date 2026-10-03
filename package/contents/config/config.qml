// SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Config page registry. `source` is resolved relative to contents/ui/.
 */
import QtQuick
import org.kde.plasma.configuration

ConfigModel {
    ConfigCategory {
        name: i18nc("@title:group configuration page", "General")
        icon: "configure"
        source: "ConfigGeneral.qml"
    }

    ConfigCategory {
        name: i18nc("@title:group configuration page", "Launchers")
        icon: "input-gaming"
        source: "ConfigProviders.qml"
    }

    ConfigCategory {
        name: i18nc("@title:group configuration page", "Hidden Games")
        icon: "view-hidden"
        source: "ConfigHidden.qml"
    }
}
