check: lint test

lint:
	uv run ruff check .

test:
	uv run pytest -q

fmt:
	uv run ruff format .

# 預設只綁本機。要從別台裝置連進來:make studio HOST=0.0.0.0(等於對區網開放)
HOST ?= 127.0.0.1
studio:
	uv run uvicorn server:app --host $(HOST) --port 8020

.PHONY: check lint test fmt studio
