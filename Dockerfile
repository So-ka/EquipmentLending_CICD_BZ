# Equipment Lending System — container image
#
# This is a CLI tool (no server/port), so the image just wraps the Python
# script. The code is baked into the image at build time; only the SQLite
# database is mounted in from the host at run time, e.g.:
#
#   docker run --rm -v "$(pwd)/lending.db:/app/lending.db" equipment-lending equipment list
#
# lending.db must already exist on the host before that bind mount runs,
# or Docker will create a directory in its place instead of a file (see
# the Makefile's `lending.db` target, or `make run`, which handles this).

FROM python:3.12-slim

WORKDIR /app

# No third-party dependencies (stdlib only — argparse, sqlite3, pathlib),
# so there's no requirements.txt to install.
COPY lending.py .

# Every capability is a sub-command of lending.py, so the container
# image itself becomes that command.
ENTRYPOINT ["python", "lending.py"]
CMD ["--help"]
