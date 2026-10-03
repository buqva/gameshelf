# Game Shelf — conventions

A KDE Plasma 6 panel widget (plasmoid) that lists every installed game from Steam,
Heroic, Lutris and other launchers in one popup grid, and launches them with a click.

Plugin id: `io.github.buqva.gameshelf`. It is the install directory name and must
match `KPlugin.Id` in `package/metadata.json`; changing it later means uninstalling and
reinstalling the widget rather than upgrading it. Never use the `org.kde.*` namespace,
which is reserved for KDE projects.

## Git

- Never merge to master.
- Never push to remote.

## Backend (Python)

- **Stdlib only.** Python >= 3.10. Type hints and `dataclasses` throughout.
- **Never guess file formats.** Inspect the real files first and build fixtures from
  them. If a path or shape is missing on this machine, ask rather than invent one.
- **stdout is JSON only.** Diagnostics go to stderr, and only behind `--verbose`.
- **Provider failures are isolated.** No provider may raise out of `registry.scan_all()`;
  failures are collected into the `errors` array of the output envelope.
- **Exit code 0 whenever valid JSON was printed**, even if some providers failed.
  Non-zero is reserved for fatal problems (bad arguments, unparseable config), and even
  then print `{"schema_version":1,"fatal":"..."}` if at all possible.
- **Read-only access** to every launcher file. Never write inside Steam, Heroic or
  Lutris directories. Open SQLite with `mode=ro`.
- **Stable game keys**, format `<provider>:<store-or-dash>:<id>` (e.g. `steam:-:570`,
  `steam:shortcut:3141592653`, `heroic:epic:Fortnite`, `lutris:-:42`). Changing the key
  format is a breaking change: it resets users' favorites and hidden lists.

## QML (Plasma 6 / Qt 6 only)

- Use `PlasmoidItem`, `org.kde.kirigami`, `org.kde.plasma.components` (3.x), and
  `org.kde.plasma.plasma5support` for the executable engine.
- Do **not** use Plasma 5 APIs: no `PlasmaCore.DataSource`, no lowercase `plasmoid.`
  attached properties.
- The QML is static and the backend only produces data. The backend never generates QML.
- Launch games with `Qt.openUrlExternally(game.launch_uri)`, never a shell command.
- **Every file using the `Plasmoid` attached property must `import org.kde.plasma.plasmoid`.**
  Without it the binding throws a ReferenceError and fails silently.
- `Qt.resolvedUrl()` returns a *url*, not a string. Wrap it in `String()` before
  calling `startsWith`, `substring` or any other string method.
- Reach the `PlasmoidItem` from a separate file with a
  `required property PlasmoidItem plasmoidItem`, passed in from `main.qml`.
- A `ComboBox` whose `model` is a plain JS array of objects **cannot use `valueRole`**:
  `indexOfValue()` returns -1 and `currentValue` is undefined, while `textRole` works
  on the same model. Map value to index in JavaScript instead.
- **Never put a `QQC2.MenuSeparator` in a menu that has to work from the keyboard.**
  Down does not skip it, it stops there, and every item below becomes unreachable.
- A `QQC2.Menu` opened from code needs `focus: true` to take the keyboard, and must
  hand focus back itself (`onClosed`) — Qt does not restore it.
- `Kirigami.Chip` needs both `activeFocusOnTab: true` and `focusPolicy: Qt.StrongFocus`
  before Tab will land on it.
- In the grid, the `GridView` owns the selection and every key handler; `GameTile` is
  told it is `highlighted` and never takes focus. Do not give a delegate focus as well.

### Config pages

`ConfigCategory.source` in `contents/config/config.qml` resolves relative to
`contents/ui/`. Each page is a `KCM.SimpleKCM` from `org.kde.kcmutils`, and the
`Plasmoid` attached property works inside the config dialog.

A `cfg_<key>` property on the page root is read and written by the dialog, so a page
that owns a composite value (`providerConfig`) must **assign** to it rather than bind,
and guard its own writes so a reset from the Defaults button can be told apart. Opening
a page must never leave Apply enabled.

### Testing QML

`plasmawindowed <plugin-id>` is the way to see the widget, but it is
**single-instance**: a second invocation exits 0 in silence and raises the *old*
window, so kill the previous process first or you will be looking at a stale
build. `console.warn` from QML reaches neither its stderr nor the journal; when
something needs tracing, have the data engine append to a file instead.

## Adding a provider

One Python file in `providers/`, no QML changes. Each new provider gets: a fixture
directory, a `test_<provider>.py`, a settings schema, and a row in the README's
supported-launchers table.

Implement `launcher_app()` too when the launcher itself can be opened. It returns a
`LauncherApp` (a URI, or argv, plus an optional icon name) and the registry turns it
into the pinned tile keyed `<provider>:launcher:<provider>`. Prefer a URI the vendor
documents — it focuses a running launcher instead of starting a second copy. Return
`None` when nothing can open it: a tile that does nothing is worse than no tile.

That tile's cover art is `package/contents/images/launchers/<provider-id>.jpg`, found
by filename, so artwork for a new launcher is a file and not a code change. Use a 2:3
portrait (the bundled ones are 267x400) — anything else gets cropped. Without one the
tile falls back to the launcher's freedesktop icon. The art must live under
`contents/`; `assets/` is repo-only and never installed.

## Commands

```bash
# backend, from the repo root
python3 package/contents/code/backend/run.py doctor
python3 package/contents/code/backend/run.py list --config-b64 "$(python3 -c 'import base64,urllib.parse,json;print(base64.b64encode(urllib.parse.quote(json.dumps({"providers":{}})).encode()).decode())')" | python3 -m json.tool
python3 -m pytest tests/

# plasmoid
kpackagetool6 -t Plasma/Applet -i package          # first install
kpackagetool6 -t Plasma/Applet -u package          # upgrade after changes
plasmoidviewer -a io.github.buqva.gameshelf    # test in a window (plasma-sdk)
journalctl --user -f | grep -i gameshelf           # QML console output in the real panel
```

If QML changes don't show up in the real panel, `plasmashell` has cached them:
`systemctl --user restart plasma-plasmashell`.
