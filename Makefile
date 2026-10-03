# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
# Game Shelf — development tasks.
PLUGIN_ID := io.github.buqva.gameshelf
PACKAGE    := package
BACKEND    := $(PACKAGE)/contents/code/backend
PYTHON     ?= python3
VERSION    := $(shell $(PYTHON) -c "import json;print(json.load(open('$(PACKAGE)/metadata.json'))['KPlugin']['Version'])")
PLASMOID   := build/$(PLUGIN_ID)-$(VERSION).plasmoid

.PHONY: help test lint install upgrade uninstall package check-package run doctor clean

help:
	@echo "make test           run the backend test suite"
	@echo "make lint           byte-compile the backend and validate metadata"
	@echo "make install        install the plasmoid for the current user"
	@echo "make upgrade        reinstall over an existing install"
	@echo "make uninstall      remove the plasmoid"
	@echo "make package        build $(PLASMOID) for the KDE Store"
	@echo "make check-package  install that archive into a throwaway prefix and run it"
	@echo "make run            scan and pretty-print the game list"
	@echo "make doctor         print diagnostics for a bug report"

test:
	$(PYTHON) -m pytest tests/ -q

lint:
	$(PYTHON) -m compileall -q $(BACKEND)/gameshelf $(BACKEND)/run.py
	$(PYTHON) -c "import json; json.load(open('$(PACKAGE)/metadata.json'))"
	$(PYTHON) -c "import xml.dom.minidom as m; m.parse('$(PACKAGE)/contents/config/main.xml')"
	@# metadata.json and the backend must agree on the version, since `doctor`
	@# is what a bug report quotes and the store shows the other one.
	$(PYTHON) -c "import json,re,pathlib; \
	  m=json.load(open('$(PACKAGE)/metadata.json'))['KPlugin']['Version']; \
	  b=re.search(r'__version__\s*=\s*\"([^\"]+)\"', pathlib.Path('$(BACKEND)/gameshelf/__init__.py').read_text()).group(1); \
	  raise SystemExit(0 if m==b else 'version mismatch: metadata.json %s, backend %s' % (m,b))"
	@echo "lint ok"

install:
	./install.sh

upgrade:
	./install.sh

uninstall:
	kpackagetool6 -t Plasma/Applet -r $(PLUGIN_ID)

# The archive is built from a staging copy so the licence can be shipped inside
# it without keeping a second copy of the file in the repository.
package: clean lint
	@mkdir -p build/stage
	@cp -r $(PACKAGE)/. build/stage/
	@cp LICENSE build/stage/LICENSE
	@find build/stage -name __pycache__ -type d -prune -exec rm -rf {} +
	@find build/stage \( -name '*.pyc' -o -name '.*.sw?' -o -name '*~' -o -name '.directory' \) -delete
	cd build/stage && zip -qr ../../$(PLASMOID) .
	@rm -rf build/stage
	@echo "built $(PLASMOID) ($$(du -h $(PLASMOID) | cut -f1))"

# What a new user does: install the archive on an account that has never seen
# the widget. XDG_DATA_HOME points somewhere throwaway so the real install is
# left alone, and the backend is then run from the installed copy.
check-package: package
	@rm -rf build/prefix
	@mkdir -p build/prefix
	XDG_DATA_HOME=$(CURDIR)/build/prefix kpackagetool6 -t Plasma/Applet -i $(PLASMOID)
	@test -f build/prefix/plasma/plasmoids/$(PLUGIN_ID)/contents/ui/main.qml
	@test -f build/prefix/plasma/plasmoids/$(PLUGIN_ID)/LICENSE
	@test -f build/prefix/plasma/plasmoids/$(PLUGIN_ID)/contents/images/launchers/steam.jpg
	$(PYTHON) build/prefix/plasma/plasmoids/$(PLUGIN_ID)/contents/code/backend/run.py list \
	  | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); print('installed copy scanned', len(d['games']), 'games,', len(d['errors']), 'errors')"
	@# The launcher banners are found relative to the backend, so only a real
	@# install proves that path still resolves once the package has moved.
	$(PYTHON) build/prefix/plasma/plasmoids/$(PLUGIN_ID)/contents/code/backend/run.py list \
	  | $(PYTHON) -c "import json,sys,urllib.parse,os; \
	    d=json.load(sys.stdin); \
	    art=[e['art']['portrait'] for e in d['launchers']]; \
	    bad=[a for a in art if not a or not os.path.isfile(urllib.parse.unquote(a[7:]))]; \
	    raise SystemExit('launcher banner missing from the installed copy: %s' % bad if bad \
	      else print('installed copy resolved', len(art), 'launcher banners'))"
	XDG_DATA_HOME=$(CURDIR)/build/prefix kpackagetool6 -t Plasma/Applet -r $(PLUGIN_ID)
	@rm -rf build/prefix
	@echo "check-package ok"

run:
	@$(PYTHON) $(BACKEND)/run.py list | $(PYTHON) -m json.tool

doctor:
	@$(PYTHON) $(BACKEND)/run.py doctor

clean:
	rm -rf build
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
