.PHONY: help install install-dev setup-hooks format lint type-check test test-cov clean run

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install production dependencies
	pip install -r backend/requirements.txt

install-dev:  ## Install development dependencies including pre-commit
	pip install -r backend/requirements.txt
	pip install pre-commit

setup-hooks:  ## Install pre-commit hooks
	pre-commit install
	@echo "✓ Pre-commit hooks installed!"

format:  ## Format code with black
	black backend/app tests

lint:  ## Lint code with ruff
	ruff check backend/app tests

lint-fix:  ## Lint and auto-fix with ruff
	ruff check --fix backend/app tests

type-check:  ## Run type checking with mypy
	mypy backend/app

test:  ## Run tests
	pytest tests/

test-cov:  ## Run tests with coverage report
	pytest --cov=backend/app --cov-report=html --cov-report=term tests/

test-unit:  ## Run only unit tests
	pytest tests/unit/ -v

test-integration:  ## Run only integration tests
	pytest tests/integration/ -v -m integration

clean:  ## Clean up cache and temporary files
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name ".coverage" -delete
	rm -rf htmlcov/

run:  ## Run the FastAPI development server
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

check-all: format lint type-check test  ## Run all quality checks

pre-commit-all:  ## Run pre-commit on all files
	pre-commit run --all-files
