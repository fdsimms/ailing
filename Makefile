.PHONY: verify server-verify client-verify

verify: server-verify client-verify

server-verify:
	cd server && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q

client-verify:
	cd client && npm run typecheck && npm test
