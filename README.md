# Equipment Lending System

A command-line application for managing equipment and loans (Project Checkpoint 1).

## User stories implemented
- Add, update, remove, and view equipment.
- Create, view, change, and cancel loans.
- Search for equipment available during a date range.
- The system prevents overlapping loans of the same equipment.

## Requirements
- Python 3.8+ (standard library only — no external dependencies)

## How to start the application
No installation step is required beyond having Python 3 installed.

```bash
python3 lending.py --help
```

Data is stored persistently in `lending.db` (SQLite), created automatically
in the same folder on first run, so it survives restarts.

## API / command reference

```
$ python lending.py --help
Usage: lending.py COMMAND [OPTIONS]

Commands:
  equipment list
  equipment add --name NAME --description TEXT
  equipment update ID [--name NAME] [--description TEXT]
  equipment remove ID
  loan list
  loan create --equipment ID --from DATE --to DATE
  loan change ID [--from DATE] [--to DATE]
  loan cancel ID
  equipment search --from DATE --to DATE
```

Dates use `YYYY-MM-DD` format.

## Try it out

```bash
python3 lending.py equipment add --name "Projector" --description "HD projector"
python3 lending.py equipment add --name "Camera" --description "DSLR camera"
python3 lending.py equipment list

python3 lending.py loan create --equipment 1 --from 2026-11-01 --to 2026-11-05
python3 lending.py loan list

# This fails: Projector (equipment 1) is already loaned in that range
python3 lending.py loan create --equipment 1 --from 2026-11-03 --to 2026-11-10

# Only shows equipment with no conflicting active loan
python3 lending.py equipment search --from 2026-11-01 --to 2026-11-05

python3 lending.py loan cancel 1
```


## Project structure
```
.
├── lending.py              # CLI application (equipment + loan commands)
├── lending.db              # SQLite database (created automatically)
└── README.md
```
