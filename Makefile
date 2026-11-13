.PHONY: up ingest web mcp eval eval-retrieval
up:            ## build + run web UI at http://localhost:8000 (ingests on first run)
	docker compose up --build
ingest:
	uv run copilot-ingest
web:
	uv run copilot-web
mcp:
	uv run copilot-mcp
eval:
	uv run python evals/run_evals.py
eval-retrieval:
	uv run python evals/run_evals.py --retrieval-only
