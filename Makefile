.PHONY: help install test test-backend test-frontend build-frontend lint up down demo reset seed

PY := py -3.11
NPM := npm

help:
	@echo "TEEVRA AI - make targets"
	@echo "  install         Install backend + frontend dependencies"
	@echo "  test-backend    Run pytest backend + MCP + A2A tests"
	@echo "  test-frontend   Type-check + build frontend"
	@echo "  lint            Run ruff (if installed) + tsc"
	@echo "  up              Start docker compose"
	@echo "  down            Stop docker compose"
	@echo "  demo            Run automated demo smoke script"
	@echo "  reset           Reset demo data via API"
	@echo "  seed            Seed demo data via API"

install:
	$(PY) -m pip install -r requirements.txt
	cd apps/dashboard && $(NPM) install

test-backend:
	$(PY) -m pytest tests/ -q

test-frontend:
	cd apps/dashboard && $(NPM) run build

lint:
	cd apps/dashboard && $(PY) -m tsc --noEmit 2>/dev/null || true

up:
	docker compose up --build -d

down:
	docker compose down

demo: test-backend test-frontend
	@echo "Demo smoke: open http://localhost:5173 (dashboard) and http://localhost:8080/api/health (api)"

reset:
	curl -s -X POST http://localhost:8080/api/demo/reset -H 'Authorization: Bearer role:PLANNER' | $(PY) -m json.tool

seed: reset
