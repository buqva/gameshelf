#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Entry point invoked by the plasmoid: adds this directory to sys.path and runs the CLI."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gameshelf.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
