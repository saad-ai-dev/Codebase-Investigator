PYTHON ?= python3

.PHONY: install install-dev serve test lint format format-check check hooks precommit docker-build docker-up docker-down

install:
	$(PYTHON) -m pip install -e .

install-dev:
	$(PYTHON) -m pip install -e .[dev]

serve:
	codebase-investigator serve --host 127.0.0.1 --port 8000

test:
	$(PYTHON) -m unittest discover -s tests

lint:
	$(PYTHON) -m ruff check src tests

format:
	$(PYTHON) -m ruff check src tests --fix
	$(PYTHON) -m ruff format src tests

format-check:
	$(PYTHON) -m ruff format --check src tests

check:
	$(PYTHON) -m ruff check src tests
	$(PYTHON) -m ruff format --check src tests
	$(PYTHON) -m unittest discover -s tests

hooks:
	pre-commit install

precommit:
	pre-commit run --all-files

docker-build:
	docker build -t codebase-investigator:local .

docker-up:
	docker compose up --build

docker-down:
	docker compose down
