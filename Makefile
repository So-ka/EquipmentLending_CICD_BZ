.PHONY: up down test test-local logs reset import-db

# Start the web app in the background -> http://localhost:8000
up:
	docker compose up --build -d --wait

# Stop it. Data is kept in the `lending-data` volume.
down:
	docker compose down

# Run the test suite inside Docker (nothing to install locally).
test:
	docker compose run --rm --build tests

# Run the tests with a local Python 3.9+ (creates .venv).
test-local:
	python3 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt && .venv/bin/python -m pytest

logs:
	docker compose logs -f web

# DANGER: stops the app AND deletes the database volume.
reset:
	docker compose down -v

# Load an existing SQLite file (e.g. the Checkpoint 1 one) into the volume:
#   make import-db DB=./lending.db      (stop the app first: make down)
import-db:
	@test -n "$(DB)" || (echo "usage: make import-db DB=path/to/lending.db" && exit 1)
	docker compose run --rm --no-deps -v "$(abspath $(DB)):/import/lending.db:ro" --entrypoint cp web /import/lending.db /data/lending.db
