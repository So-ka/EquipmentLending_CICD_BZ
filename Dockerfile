# Equipment Lending System — web app image.
#
# Stages:  base -> test  (pytest; used by `docker compose run tests`)
#          base -> runtime (default; gunicorn serving the Flask app on :8000)
# The runtime stage is last, so a plain `docker build .` produces it.

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LENDING_DB=/data/lending.db
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY wsgi.py lending.py openapi.yaml ./

FROM base AS test
COPY requirements-dev.txt pytest.ini ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests ./tests
CMD ["python", "-m", "pytest"]

FROM base AS runtime
# The database lives in /data, which is a Docker *volume*, so it outlives
# containers and image rebuilds. Creating /data here (owned by the app user)
# means a fresh named volume inherits that ownership.
RUN useradd --system --uid 10001 --no-create-home app \
    && mkdir /data && chown app:app /data
USER app
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2).status == 200 else 1)"
# 2 workers share one SQLite file safely (writes are serialised by SQLite;
# the overlap check runs inside BEGIN IMMEDIATE).
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "wsgi:app"]
