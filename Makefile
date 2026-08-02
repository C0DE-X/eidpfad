.PHONY: setup content voice server-build server-up server-down server-test release-playtest client-windows repository-check validate ci package

VENV ?= .venv
BOOTSTRAP_PYTHON ?= python3
PYTHON ?= $(VENV)/bin/python
NPM ?= npm
GODOT ?= godot

setup:
	$(BOOTSTRAP_PYTHON) -m venv "$(VENV)"
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e './server[dev]'

content:
	$(PYTHON) scripts/generate_content.py
	$(PYTHON) scripts/generate_audio.py
	$(PYTHON) scripts/generate_narrative.py
	$(NPM) ci --ignore-scripts
	$(NPM) run voice
	$(PYTHON) scripts/generate_visual_assets.py

voice:
	$(PYTHON) scripts/generate_narrative.py
	$(NPM) ci --ignore-scripts
	$(NPM) run voice
	$(PYTHON) scripts/generate_visual_assets.py

server-build:
	docker compose build server

server-up:
	docker compose up --build -d

server-down:
	docker compose down

server-test:
	PYTHONPATH=server $(PYTHON) -m unittest discover -s server/tests -v

release-playtest:
	PYTHONPATH=server $(PYTHON) scripts/virtual_release_playthrough.py --campaign-length saga

client-windows:
	mkdir -p dist/client
	$(GODOT) --headless --path client --export-release "Windows 11" "$(abspath dist/client/eidpfad-windows-x86_64.exe)"

repository-check:
	$(PYTHON) scripts/check_repository.py

validate: server-test
	$(PYTHON) -m json.tool shared/cards.json >/dev/null
	$(PYTHON) -m json.tool shared/items.json >/dev/null
	$(PYTHON) -m json.tool shared/enemies.json >/dev/null
	$(PYTHON) -m json.tool shared/protocol.schema.json >/dev/null
	$(PYTHON) -m json.tool shared/narrative/cinematics.json >/dev/null
	$(PYTHON) -m json.tool shared/narrative/voice_manifest.de-DE.json >/dev/null
	$(PYTHON) -m compileall -q server/app server/tests scripts
	$(PYTHON) scripts/validate_project.py --report docs/content-report.json

ci: repository-check validate

package: validate
	mkdir -p dist
	rm -f "$(abspath dist/eidpfad-release-source.zip)"
	zip -qr dist/eidpfad-release-source.zip . -x '.env' '.venv/*' '.git/*' '.godot/*' 'node_modules/*' 'dist/*' '*/__pycache__/' '*/__pycache__/*' '*.pyc'
