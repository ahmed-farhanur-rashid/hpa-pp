# ═══════════════════════════════════════════════════════════════
# HPA++ Top-Level Makefile
# ═══════════════════════════════════════════════════════════════
# Targets for development, testing, and demo.
# Each service also has its own Makefile under services/<name>/.
# ═══════════════════════════════════════════════════════════════

.PHONY: install install-all lint format test test-all clean \
        db-init build up down demo demo-load \
        test-contracts test-e2e

# ─── Installation ─────────────────────────────────────────────

install:
	pip install -r requirements.txt

install-all:
	@for dir in services/*/; do \
		echo "Installing $$dir..."; \
		cd "$$dir" && pip install -r requirements.txt && cd ../..; \
	done
	pip install -r requirements.txt

# ─── Code Quality ─────────────────────────────────────────────

lint:
	ruff check shared/ services/ --fix

format:
	ruff format shared/ services/

# ─── Testing ──────────────────────────────────────────────────

test:
	pytest shared/tests/ -v --cov=shared --cov-report=term-missing

test-all:
	@for dir in services/*/; do \
		echo "Testing $$dir..."; \
		cd "$$dir" && pytest tests/ -v && cd ../..; \
	done

test-contracts:
	pytest services/integration/tests/contracts/ -v

test-e2e:
	pytest services/integration/tests/e2e/ -v --timeout=120

# ─── Database ─────────────────────────────────────────────────

db-init:
	python -c "from shared.db.init import init_db; init_db()"

# ─── Docker ───────────────────────────────────────────────────

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down -v

demo:
	docker compose --profile demo up --build

demo-load:
	docker compose --profile demo up --build -d
	@echo "Load generator starting... Run 'make demo-logs' to follow."

demo-logs:
	docker compose logs -f

# ─── Cleanup ──────────────────────────────────────────────────

clean:
	rm -rf data/*.db __pycache__ .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

# ─── Individual Service Commands ──────────────────────────────

start-sim:
	docker compose up -d simulation

start-forecast:
	docker compose up -d forecasting

start-controller:
	docker compose up -d controller

start-dashboard:
	docker compose up -d dashboard

stop-all:
	docker compose down

logs-sim:
	docker compose logs -f simulation

logs-all:
	docker compose logs -f
