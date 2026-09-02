.PHONY: help install build build-quick seed run ui ui-install ui-build clean

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
BACKEND := backend

help:
	@echo "openEuler 包分级治理平台"
	@echo "  make install      Create venv and install backend dependencies"
	@echo "  make ui           Build the React/TypeScript frontend (pnpm)"
	@echo "  make build        Collect live data (all public APIs) + governance -> packages.json"
	@echo "  make build-quick  Build without the slow activity sweep (metadata + Ubuntu only)"
	@echo "  make seed         Regenerate a deterministic demo dataset (no network)"
	@echo "  make run          Start the FastAPI server + interactive dashboard"
	@echo "  make clean     Remove generated data cache"

install:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r $(BACKEND)/requirements.txt

build:
	cd $(BACKEND) && PYTHONPATH=. $(CURDIR)/$(PY) $(CURDIR)/scripts/build.py

build-quick:
	cd $(BACKEND) && PYTHONPATH=. $(CURDIR)/$(PY) $(CURDIR)/scripts/build.py --no-activity

seed:
	cd $(BACKEND) && PYTHONPATH=. $(CURDIR)/$(PY) $(CURDIR)/scripts/seed.py

ui-install:
	cd frontend && pnpm install

ui-build: ui-install
	cd frontend && pnpm build

ui:
	cd frontend && pnpm install && pnpm build

run:
	@test -d frontend/dist || (echo "UI 未构建，先执行 pnpm build…" && cd frontend && pnpm install && pnpm build)
	cd $(BACKEND) && PYTHONPATH=. $(CURDIR)/$(PY) -m uvicorn app.server:app --host 127.0.0.1 --port 8000

clean:
	rm -rf $(BACKEND)/data/cache
