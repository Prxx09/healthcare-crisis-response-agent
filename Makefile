.PHONY: setup dev api web check data

BACKEND_PORT ?= 8001

setup:
	./scripts/setup.sh

dev:
	./scripts/dev.sh

api:
	cd backend && ../.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port $(BACKEND_PORT)

web:
	npm run dev --prefix frontend

check:
	.venv/bin/python -m compileall backend/app
	npm run build --prefix frontend

data:
	.venv/bin/python data/generate_synthetic_surveillance.py
