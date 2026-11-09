# Equipment Lending System

![CI](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg) ![Quality](https://github.com/OWNER/REPO/actions/workflows/quality.yml/badge.svg)
<!-- replace OWNER/REPO with your GitHub path -->

Web application (HTML forms + JSON REST API) for managing equipment and loans.
Checkpoint 3 — built from the Checkpoint 1 CLI; the CLI still works and shares the same rules.

**Web address (Docker Compose): http://localhost:8000**

| What | URL |
|---|---|
| Web app (forms) | http://localhost:8000/ |
| REST API base | http://localhost:8000/api/v1 |
| Interactive API docs (Swagger UI, loads from a CDN) | http://localhost:8000/api/v1/docs |
| OpenAPI spec | `openapi.yaml` · http://localhost:8000/api/v1/openapi.yaml |

## Commands (from a fresh checkout)

Requires Docker with the Compose plugin and `make`. Nothing else to install.

```bash
git clone <your-repo-url> equipment-lending && cd equipment-lending

make up      # build + start in the background, waits until healthy  -> http://localhost:8000
make down    # stop and remove the containers (data is kept)
make test    # run the unit/API tests inside Docker
```

Without `make`, the equivalent commands are:

```bash
docker compose up --build -d --wait          # start
docker compose down                          # stop
docker compose run --rm --build tests        # run tests
```

Other helpers: `make logs`, `make reset` (**deletes the database volume**),
`make test-local` (tests with a local Python 3.10+ in `.venv`, no Docker).

## Data persistence

The SQLite file lives at `/data/lending.db` inside the container, on the named
Docker volume `lending-data`. It survives `make down`/`make up`, image rebuilds
and container removal; only `docker compose down -v` / `make reset` deletes it.

To load an existing database (e.g. your Checkpoint 1 `lending.db`):

```bash
make down
make import-db DB=./lending.db
make up
```

## Web forms

| Workflow | Where |
|---|---|
| Add / edit / remove equipment | **Equipment** page |
| Find equipment free during a date range | **Equipment** page → "Find available equipment" |
| Create a loan | **Loans** page → "Create loan" |
| View / filter loans | **Loans** page |
| Change loan dates / cancel a loan | **Loans** page → *Change* / *Cancel* |

## REST API summary

Full details, parameters, examples and error responses are in `openapi.yaml`.

| Method & URL | Purpose | Success |
|---|---|---|
| `GET /api/v1/equipment[?available_from=&available_to=]` | List (optionally only free in range) | 200 |
| `POST /api/v1/equipment` | Add | 201 + `Location` |
| `GET /api/v1/equipment/{id}` | Read | 200 |
| `PATCH /api/v1/equipment/{id}` | Update name/description | 200 |
| `DELETE /api/v1/equipment/{id}` | Remove | 204 |
| `GET /api/v1/loans[?equipment_id=&status=]` | List | 200 |
| `POST /api/v1/loans` | Create | 201 + `Location` |
| `GET /api/v1/loans/{id}` | Read | 200 |
| `PATCH /api/v1/loans/{id}` | Change dates (active loans only) | 200 |
| `POST /api/v1/loans/{id}/cancel` | Cancel (idempotent) | 200 |
| `GET /api/v1/health` | Health check | 200 |

Errors always look like `{"error": {"code", "message", "details"}}` with status
400 (validation), 404, 405, 409 (conflict), 415 or 500.

```bash
curl -X POST localhost:8000/api/v1/equipment -H 'Content-Type: application/json' \
     -d '{"name":"Projector","description":"HD projector"}'
curl -X POST localhost:8000/api/v1/loans -H 'Content-Type: application/json' \
     -d '{"equipment_id":1,"from_date":"2026-11-01","to_date":"2026-11-05"}'
# overlapping request -> 409
curl -i -X POST localhost:8000/api/v1/loans -H 'Content-Type: application/json' \
     -d '{"equipment_id":1,"from_date":"2026-11-03","to_date":"2026-11-10"}'
curl -X POST localhost:8000/api/v1/loans/1/cancel
```

## Business rules (tested in `tests/test_services.py`)

* Dates are `YYYY-MM-DD`, real calendar dates; `from_date` ≤ `to_date`; ranges are inclusive.
* Active loans of the same equipment may not overlap; cancelled loans never conflict. The check and the write happen in one transaction, so concurrent requests cannot double-book.
* Only active loans can be changed; cancelling twice is harmless.
* Equipment with active loans cannot be removed (409). *Change from Checkpoint 1, which silently deleted its loans.* Cancelled loans are removed with the equipment.
* Equipment name is required (max 100 chars); description max 500.

## Tests

`tests/test_services.py` (rules, incl. a concurrency test), `tests/test_api.py`
(URLs, methods, status codes, JSON, persistence across restarts, OpenAPI validity,
and a check that every route is documented in `openapi.yaml`), `tests/test_web.py`
(every form workflow, plus the CLI wrapper).

## Continuous integration (Checkpoint 4)

| | GitHub Actions | GitLab CI |
|---|---|---|
| Build + unit tests | `.github/workflows/ci.yml` → job **Build & unit tests** | `.gitlab-ci.yml` → `unit-tests` |
| Docker image build + smoke test | `ci.yml` → job **Docker image build & smoke test** | `docker-build` |
| Extra check: lint (ruff) + coverage ≥ 90 % | `.github/workflows/quality.yml` | `lint`, `coverage` |

All run on every push and pull request / merge request.
Run the same checks locally:

```bash
pip install -r requirements-dev.txt
python -m pytest --junitxml=junit.xml      # unit tests (69)
ruff check .                               # lint
python -m pytest --cov                     # coverage, fails under 90 % (see .coveragerc)
```

**Where results are visible**
* GitHub: the run page's *Summary* shows a test-result table and a coverage table; lint findings appear as inline annotations; `junit-report` and `coverage-report` (HTML) are downloadable artifacts; the README badges show pass/fail.
* GitLab: the pipeline's *Tests* tab (JUnit), coverage % on the `coverage` job, code-quality report, `htmlcov` artifact.

The Docker job builds the `test` image and runs the tests in it, builds the runtime image through
`docker compose up --build`, drives the real HTTP API with `scripts/smoke.py`, then restarts the stack to prove the
data survived in the `lending-data` volume.

### Publishing and demonstrating (what to do once)

```bash
git init -b main && git add . && git commit -m "Checkpoint 4: CI"
git remote add origin https://github.com/OWNER/REPO.git       # create an empty repo first
git push -u origin main                                       # -> both workflows run; wait for green
git remote add gitlab https://gitlab.<university>/<you>/REPO.git
git push gitlab main                                          # -> GitLab pipeline runs
```

Failing run, then the fix (on a branch, so `main` stays green):

```bash
git switch -c demo/broken-overlap
# in app/services.py, ranges_overlap(): change  a_from <= b_to and b_from <= a_to
#                                       into    a_from <  b_to and b_from <  a_to
git commit -am "Break overlap rule (demo)" && git push -u origin demo/broken-overlap
# -> CI fails: 4 tests red (test_ranges_overlap[...], test_overlapping_active_loan_rejected, ...)
#    save this run's URL as the "failed run" link; push to GitLab too (git push gitlab demo/broken-overlap)
git revert HEAD --no-edit && git push                         # -> green again; this is the "fixed run"
# open a pull request / merge into main so that main's latest run is green
```

Submit: the three workflow YAML files, the GitHub run URLs (green on `main`, red on the demo branch, green after
the fix) and the equivalent GitLab pipeline URLs.

## CLI (still available)

```bash
pip install -r requirements.txt
LENDING_DB=./lending.db python3 lending.py equipment list
```

## Layout

```
app/            __init__ (app factory), db, services (rules), api (REST), web (forms), templates/
lending.py      CLI wrapper over app.services
wsgi.py         gunicorn entry point
openapi.yaml    API contract
tests/          pytest suite
Dockerfile      stages: base, test, runtime
.github/workflows/  ci.yml, quality.yml      .gitlab-ci.yml
scripts/        smoke.py (HTTP end-to-end), junit_summary.py
docker-compose.yml, Makefile, requirements*.txt
```
