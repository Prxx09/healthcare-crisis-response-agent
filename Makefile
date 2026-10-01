.PHONY: setup dev api web check data

setup:
	./scripts/setup.sh

dev:
	./scripts/dev.sh

api:
	cd backend && ../.venv/bin/uvicorn app.main:app --reload

web:
	npm run dev --prefix frontend

check:
	.venv/bin/python -m compileall backend/app
	npm run build --prefix frontend

data:
	.venv/bin/python data/generate_synthetic_surveillance.py
