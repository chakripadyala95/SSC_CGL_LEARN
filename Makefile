# Local development. Python tools run from .venv; `make setup` creates it.
PY := .venv/bin/python

.PHONY: setup up down migrate load api web test

setup:
	python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd web && npm install

up:            ## start PostgreSQL, API and web app in Docker
	docker compose up -d --build

down:
	docker compose down

migrate:       ## apply database migrations
	.venv/bin/alembic upgrade head

load: migrate  ## load intake, extraction and solver output from data/ (idempotent)
	$(PY) -m api.load

api:           ## run the API with reload on :8000
	.venv/bin/uvicorn api.main:app --reload

web:           ## run the web app with reload on :3000
	cd web && npm run dev

test:
	$(PY) -m pytest
