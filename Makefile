.DEFAULT_GOAL := help
.PHONY: help up down setup migrate seed ingest enrich pipeline api web dev test lint status env clean reset

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-12s\033[0m %s\n", $$1, $$2}'

up: ## Start Postgres (pgvector) and Redis
	docker compose up -d
	@printf "waiting for postgres"
	@until docker compose exec -T db pg_isready -U pulseai -d pulseai >/dev/null 2>&1; do \
		printf "."; sleep 1; \
	done; echo " ready"

down: ## Stop containers, keeping data
	docker compose down

setup: up migrate seed ## Bring up infra, migrate, and seed the catalog
	@echo "\nReady. Next: make pipeline"

migrate: ## Apply database migrations
	uv run alembic upgrade head

seed: ## Insert or refresh the model catalog and source list
	uv run pulseai seed

ingest: ## Fetch new documents from every enabled source
	uv run pulseai ingest

enrich: ## Detect models and score sentiment for pending documents
	uv run pulseai enrich

pipeline: ## Ingest then enrich — the one command that refreshes everything
	uv run pulseai pipeline

status: ## Corpus totals and top models
	uv run pulseai status

api: ## Serve the REST API on :8000
	uv run uvicorn pulseai.api.app:app --reload --port 8000

web: ## Serve the dashboard on :3000
	cd web && npm run dev

dev: ## Run API and dashboard together
	@$(MAKE) -j2 api web

test: ## Run the test suite
	uv run pytest -q

lint: ## Lint and typecheck
	uv run ruff check src tests
	cd web && npx tsc --noEmit

env: ## Write .env, lifting a GitHub token from your local `gh` login
	@test -f .env || cp .env.example .env
	@if command -v gh >/dev/null && gh auth token >/dev/null 2>&1; then \
		token=$$(gh auth token); \
		if grep -q '^PULSEAI_GITHUB_TOKEN=' .env; then \
			sed -i '' "s|^PULSEAI_GITHUB_TOKEN=.*|PULSEAI_GITHUB_TOKEN=$$token|" .env; \
		else \
			printf '\nPULSEAI_GITHUB_TOKEN=%s\n' "$$token" >> .env; \
		fi; \
		echo "GitHub token written to .env (gitignored) — 5,000 req/hr"; \
	else \
		echo "No gh login found; GitHub stays at 10 search req/min"; \
	fi

clean: ## Remove caches
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache web/.next

reset: ## Destroy the database volume and rebuild from scratch
	@printf "This deletes all collected documents. Continue? [y/N] " && read ans && [ "$$ans" = "y" ]
	docker compose down -v
	$(MAKE) setup
