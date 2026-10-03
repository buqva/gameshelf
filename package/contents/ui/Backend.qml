// SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Wraps the Python backend behind a signal-based API.
 *
 * Commands run through the Plasma5Support executable data engine, which hands
 * back stdout, stderr and the exit code on a single newData signal. The backend
 * guarantees stdout is JSON and nothing else, so parsing is unconditional.
 */
import QtQuick
import org.kde.plasma.plasmoid
import org.kde.plasma.plasma5support as P5Support

Item {
    id: backend

    // Emitted with the parsed envelope from `run.py list`.
    signal listReady(var payload)
    // Emitted with the parsed payload from `run.py providers`.
    signal providersReady(var payload)
    // Emitted when a command could not be run, or returned something unusable.
    signal failed(string message)

    readonly property bool busy: pending > 0
    property int pending: 0

    // Each request gets a unique source name, so a reply arriving after a newer
    // request was issued can be recognised and discarded.
    property int requestCounter: 0
    property int latestList: 0
    property int latestProviders: 0

    /* Qt.resolvedUrl() returns a url value, not a string; String() is required
     * before any string method, or the binding throws and silently yields "". */
    readonly property string scriptPath: {
        const resolved = String(Qt.resolvedUrl("../code/backend/run.py"));
        return resolved.startsWith("file://") ? resolved.substring(7) : resolved;
    }

    /* Both inputs default to the saved configuration but stay assignable: the
     * config dialog has to query the backend with settings the user has typed
     * and not yet applied. Assigning either one replaces its binding.
     *
     * The attached Plasmoid is read through a guard because this component is
     * also instantiated inside the config dialog, where a missing applet would
     * otherwise turn the whole binding into a silent empty string. */
    readonly property var appletConfig: Plasmoid ? Plasmoid.configuration : null
    property string pythonPath: (appletConfig && appletConfig.pythonPath) || "python3"
    property string providerConfigJson: appletConfig ? appletConfig.providerConfig : "{}"

    /* Single-quote for POSIX sh: inside single quotes every character is
     * literal, so only the quote itself needs care. */
    function shellQuote(value) {
        return "'" + String(value).replace(/'/g, "'\\''") + "'";
    }

    function encodedConfig() {
        let providers = {};
        const raw = backend.providerConfigJson;
        if (raw && raw.length > 0) {
            try {
                const parsed = JSON.parse(raw);
                if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
                    providers = parsed;
                }
            } catch (error) {
                console.warn("gameshelf: providerConfig is not valid JSON, using defaults:", error);
            }
        }
        // Must match decode_config() in the backend: percent-encode, then base64.
        return Qt.btoa(encodeURIComponent(JSON.stringify({ providers: providers })));
    }

    function runCommand(subcommand, extraArgs, isProviders) {
        if (scriptPath.length === 0) {
            backend.failed(i18n("Could not locate the Game Shelf backend."));
            return;
        }
        const tag = ++requestCounter;
        // The trailing comment makes the source name unique without changing
        // what the shell actually executes.
        const command = [
            shellQuote(pythonPath),
            shellQuote(scriptPath),
            subcommand,
            "--config-b64",
            shellQuote(encodedConfig()),
            extraArgs || "",
            "# gameshelf-" + tag
        ].join(" ");

        // Record the tag before starting the job: the engine may deliver a
        // reply synchronously, and a later assignment would look stale.
        if (isProviders) {
            latestProviders = tag;
        } else {
            latestList = tag;
        }
        pending += 1;
        executable.connectSource(command);
    }

    function list(noCache) {
        runCommand("list", noCache ? "--no-cache" : "", false);
    }

    function providers() {
        runCommand("providers", "", true);
    }

    function launch(key) {
        // Fallback path for providers with no URI handler; the reply is ignored
        // beyond reporting failure.
        if (scriptPath.length === 0) {
            backend.failed(i18n("Could not locate the Game Shelf backend."));
            return;
        }
        executable.connectSource([
            shellQuote(pythonPath),
            shellQuote(scriptPath),
            "launch",
            shellQuote(key),
            "--config-b64",
            shellQuote(encodedConfig())
        ].join(" "));
    }

    P5Support.DataSource {
        id: executable
        engine: "executable"

        onNewData: (sourceName, data) => {
            executable.disconnectSource(sourceName);

            const exitCode = data["exit code"];
            const stderr = String(data["stderr"] || "").trim();
            const stdout = String(data["stdout"] || "").trim();

            if (stderr.length > 0) {
                console.warn("gameshelf backend:", stderr);
            }

            // `launch` carries no tag and produces no envelope worth parsing.
            const match = sourceName.match(/# gameshelf-(\d+)$/);
            if (!match) {
                if (exitCode !== 0) {
                    backend.failed(i18n("Could not launch the game."));
                }
                return;
            }

            backend.pending = Math.max(0, backend.pending - 1);
            const tag = parseInt(match[1], 10);

            if (stdout.length === 0) {
                backend.failed(exitCode === 0
                    ? i18n("The backend returned no output.")
                    : i18n("The backend failed (exit code %1).", exitCode));
                return;
            }

            let payload;
            try {
                payload = JSON.parse(stdout);
            } catch (error) {
                backend.failed(i18n("Could not read the backend's response."));
                console.warn("gameshelf: unparseable stdout:", stdout.substring(0, 400));
                return;
            }

            if (payload.fatal) {
                backend.failed(String(payload.fatal));
                return;
            }

            // Discard replies for superseded requests: they would overwrite
            // newer data with older.
            if (tag === backend.latestProviders && sourceName.indexOf(" providers ") !== -1) {
                backend.providersReady(payload);
            } else if (tag === backend.latestList) {
                backend.listReady(payload);
            }
        }
    }
}
