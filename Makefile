.PHONY: dev test test-cov lint format docker-build clean

dev:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

test:
	uv run pytest -v

test-cov:
	uv run pytest --cov=app --cov-report=term-missing --cov-report=xml

lint:
	uv run ruff check .

format:
	uv run ruff format .

docker-build:
	docker build -t audio-mcp:dev .

clean:
	rm -rf .pytest_cache .coverage coverage.xml htmlcov .ruff_cache
