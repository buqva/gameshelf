Copied in shape from a real native Prism Launcher data directory
(`$XDG_DATA_HOME/PrismLauncher`) and then sanitised: the key names, the QSettings
escaping in `instance.cfg` and the `mmc-pack.json` component layout are
verbatim, while names, uuids and timestamps are made up.

Nothing here is read yet — the provider contributes only the launcher tile. The
tree is committed now because it was captured off a real install, and it is what
instance-level tiles will be written against.
