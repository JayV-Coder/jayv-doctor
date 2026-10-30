# Comandos do dia a dia. Requer: Node 22 + pnpm 9 (corepack), uv; Docker + Supabase CLI para os alvos db:*.
.PHONY: dev-setup dev lint typecheck test format check db\:reset db\:types db\:test db\:lint

dev-setup: ## instala dependências TS e Python e os hooks de pre-commit
	pnpm install
	uv sync --all-packages
	uvx pre-commit install

dev: ## sobe os apps em modo dev (web e api chegam nos tickets #7 e #9)
	pnpm turbo run dev

lint:
	pnpm turbo run lint
	pnpm format:check
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	pnpm turbo run typecheck
	uv run mypy

test:
	pnpm turbo run test
	uv run pytest

format:
	pnpm format
	uv run ruff check --fix .
	uv run ruff format .

check: lint typecheck test ## o mesmo que o CI roda

db\:reset: ## recria o banco local com migrações e seed (ticket #2)
	supabase db reset

db\:types: ## regenera os tipos TS do schema
	supabase gen types typescript --local > packages/contracts/src/database.types.ts

db\:test: ## testes pgTAP
	supabase test db

db\:lint: ## plpgsql_check só nos schemas mantidos aqui (extensões como pg_partman ficam de fora)
	supabase db lint --schema public,app --fail-on warning
