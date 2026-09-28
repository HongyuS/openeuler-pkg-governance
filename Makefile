.PHONY: help install build build-quick seed run dev stop status restart lint format typecheck check ui ui-install ui-build clean

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
BACKEND := backend

help:
	@echo "openEuler 包分级治理平台"
	@echo "  make install      Create venv and install backend dependencies (+ dev tools)"
	@echo "  make ui           Build the React/TypeScript frontend (pnpm)"
	@echo "  make build        Collect live data (all public APIs) + governance -> packages.json"
	@echo "  make build-quick  Build without the slow activity sweep (metadata + Ubuntu only)"
	@echo "  make seed         Regenerate a deterministic demo dataset (no network)"
	@echo "  make dev          Start the dev server with port management (idempotent)"
	@echo "  make stop         Stop the running dev server"
	@echo "  make restart      Restart the dev server"
	@echo "  make status       Show running dev-server instances"
	@echo "  make run          Start the server directly on 127.0.0.1:8000 (no instance management)"
	@echo "  make lint         ruff (lint+format check) + eslint"
	@echo "  make format       ruff auto-format + autofix"
	@echo "  make typecheck    mypy + tsc"
	@echo "  make check        lint + typecheck"

install:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r $(BACKEND)/requirements.txt
	$(PIP) install -e ".[dev]"

build:
	cd $(BACKEND) && PYTHONPATH=. $(CURDIR)/$(PY) $(CURDIR)/scripts/build.py

build-quick:
	cd $(BACKEND) && PYTHONPATH=. $(CURDIR)/$(PY) $(CURDIR)/scripts/build.py --quick

seed:
	cd $(BACKEND) && PYTHONPATH=. $(CURDIR)/$(PY) $(CURDIR)/scripts/seed.py

ui-install:
	cd frontend && pnpm install

ui-build: ui-install
	cd frontend && pnpm build

ui:
	cd frontend && pnpm install && pnpm build

dev:
	@$(CURDIR)/$(PY) $(CURDIR)/scripts/dev.py

stop:
	@$(CURDIR)/$(PY) $(CURDIR)/scripts/dev.py --stop

restart:
	@$(CURDIR)/$(PY) $(CURDIR)/scripts/dev.py --restart

status:
	@$(CURDIR)/$(PY) $(CURDIR)/scripts/dev.py --status

run:
	@test -d frontend/dist || (echo "UI 未构建，先执行 pnpm build…" && cd frontend && pnpm install && pnpm build)
	cd $(BACKEND) && PYTHONPATH=. $(CURDIR)/$(PY) -m uvicorn app.server:app --host 127.0.0.1 --port 8000

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .
	cd frontend && pnpm lint

format:
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .

typecheck:
	$(PY) -m mypy
	cd frontend && pnpm typecheck

check: lint typecheck

clean:
	rm -rf $(BACKEND)/data/cache
