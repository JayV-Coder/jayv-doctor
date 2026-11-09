# Comandos do dia a dia. Requer: Node 22 + pnpm 9 (corepack), uv; Docker + Supabase CLI para os alvos db:*.
.PHONY: dev-setup dev lint typecheck test format check contracts eval eval-hybrid eval-gate load\:ingestion load\:read load\:diagnoses load\:report db\:reset db\:types db\:test db\:lint

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

eval: ## avaliação do motor em rules_only, com relatório em tests/evaluation/reports (ticket #30)
	uv run python -m aid_evaluation run --modes rules_only

eval-hybrid: ## avaliação também no híbrido, com o provedor real e o juiz (precisa das chaves)
	uv run python -m aid_evaluation run --modes rules_only hybrid --provider $${EVAL_PROVIDER:-anthropic} --judge

eval-gate: ## gate de regressão: rules_only não cai mais de 2 p.p. contra a linha de base
	uv run python -m aid_evaluation gate

load\:ingestion: ## carga de ingestão (k6, #33): 3,5 Eventos/s e pico de 200/s; RUN_ID, INGESTION_TOKEN, INTEGRATION_ID, API_URL
	k6 run --summary-export=ingestion-summary.json tests/load/ingestion.js

load\:read: ## carga da API de leitura: 50 Usuários; USER_JWTS, API_URL
	k6 run --summary-export=read-summary.json tests/load/read.js

load\:diagnoses: ## 100 Diagnósticos em 1 h; USER_JWT, INCIDENT_IDS, API_URL
	k6 run tests/load/diagnoses.js

load\:report: ## confere no banco a rodada (zero perda, lag p95, Diagnósticos); RUN_ID, SINCE, INTEGRATION_ID, SUPABASE_DB_URL
	uv run python scripts/load_report.py --run $$RUN_ID --since $$SINCE --integration $$INTEGRATION_ID \
	  $$([ -f ingestion-summary.json ] && echo --ingestion ingestion-summary.json) \
	  $$([ -f read-summary.json ] && echo --read read-summary.json)

contracts: ## regenera modelos Pydantic e tipos TS a partir de packages/contracts/schemas
	pnpm exec prettier --write packages/contracts/schemas
	uv run python packages/contracts/scripts/generate.py

db\:reset: ## recria o banco local com migrações e seed (ticket #2)
	supabase db reset

db\:types: ## regenera os tipos TS do schema
	supabase gen types typescript --local --schema doctor > packages/contracts/src/database.types.ts

db\:test: ## testes pgTAP
	supabase test db

db\:lint: ## plpgsql_check só nos schemas mantidos aqui (extensões como pg_partman ficam de fora)
	supabase db lint --schema doctor --fail-on warning

ENV ?= dev
TF := terraform -chdir=infrastructure/terraform/stack

tf\:check: ## fmt, validate, tflint e testes do Terraform (sem credenciais)
	terraform -chdir=infrastructure/terraform fmt -check -recursive
	$(TF) init -backend=false -input=false
	$(TF) validate
	cd infrastructure/terraform && tflint --recursive --config="$$PWD/.tflint.hcl"
	$(TF) test

tf\:plan: ## plan de um ambiente: make tf:plan ENV=staging
	$(TF) init -reconfigure -input=false -backend-config=../environments/$(ENV).backend.hcl
	$(TF) plan -var-file=../environments/$(ENV).tfvars

tf\:apply: ## apply de um ambiente: make tf:apply ENV=staging
	$(TF) init -reconfigure -input=false -backend-config=../environments/$(ENV).backend.hcl
	$(TF) apply -var-file=../environments/$(ENV).tfvars
