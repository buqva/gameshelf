#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
# Install or upgrade the Game Shelf plasmoid for the current user.
set -euo pipefail

PLUGIN_ID="io.github.buqva.gameshelf"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE="$HERE/package"

if ! command -v kpackagetool6 >/dev/null 2>&1; then
    echo "error: kpackagetool6 not found. Install the Plasma 6 development tools." >&2
    exit 1
fi

if [ ! -f "$PACKAGE/metadata.json" ]; then
    echo "error: $PACKAGE/metadata.json is missing." >&2
    exit 1
fi

# kpackagetool6 -u fails when nothing is installed yet, and -i fails when
# something is, so pick the verb from what is actually present.
if kpackagetool6 -t Plasma/Applet -l 2>/dev/null | grep -qx "$PLUGIN_ID"; then
    echo "Upgrading $PLUGIN_ID ..."
    kpackagetool6 -t Plasma/Applet -u "$PACKAGE"
else
    echo "Installing $PLUGIN_ID ..."
    kpackagetool6 -t Plasma/Applet -i "$PACKAGE"
fi

echo
echo "Done. To see QML changes in a running panel:"
echo "    systemctl --user restart plasma-plasmashell"
