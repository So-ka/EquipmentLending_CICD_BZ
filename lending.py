#!/usr/bin/env python3
"""
Equipment Lending System
=========================

A command-line application that lets a team add, update, remove and view
equipment, and create, view, change and cancel loans of that equipment.

Data is stored persistently in a local SQLite database (lending.db) so that
it survives application restarts.

Usage mirrors the "documented API" required by the course: every capability
is reachable as a sub-command, so the application can be driven entirely
without a graphical user interface (and, just as easily, wrapped by a
script, a test, or a future web layer).

Run `python lending.py --help` for the full command reference.
"""

import argparse
import datetime
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "lending.db"


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def get_connection():
    """Open a connection to the SQLite database, creating tables if needed."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS equipment (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS loan (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            equipment_id   INTEGER NOT NULL,
            from_date      TEXT NOT NULL,
            to_date        TEXT NOT NULL,
            status         TEXT NOT NULL DEFAULT 'active',
            FOREIGN KEY (equipment_id) REFERENCES equipment(id)
        );
        """
    )
    conn.commit()
    return conn


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def parse_date(value: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid date '{value}'. Expected format YYYY-MM-DD."
        )


def ranges_overlap(a_from, a_to, b_from, b_to) -> bool:
    """Two inclusive date ranges overlap unless one ends before the other starts."""
    return a_from <= b_to and b_from <= a_to


def equipment_exists(conn, equipment_id) -> bool:
    row = conn.execute(
        "SELECT 1 FROM equipment WHERE id = ?", (equipment_id,)
    ).fetchone()
    return row is not None


def get_equipment_or_die(conn, equipment_id):
    row = conn.execute(
        "SELECT * FROM equipment WHERE id = ?", (equipment_id,)
    ).fetchone()
    if row is None:
        print(f"Error: equipment {equipment_id} does not exist.", file=sys.stderr)
        sys.exit(1)
    return row


def get_loan_or_die(conn, loan_id):
    row = conn.execute("SELECT * FROM loan WHERE id = ?", (loan_id,)).fetchone()
    if row is None:
        print(f"Error: loan {loan_id} does not exist.", file=sys.stderr)
        sys.exit(1)
    return row


# --------------------------------------------------------------------------- #
# equipment sub-commands
# --------------------------------------------------------------------------- #
def cmd_equipment_list(args, conn):
    rows = conn.execute("SELECT * FROM equipment ORDER BY id").fetchall()
    if not rows:
        print("No equipment registered.")
        return
    for r in rows:
        print(f"{r['id']}\t{r['name']}\t{r['description'] or ''}")


def cmd_equipment_add(args, conn):
    cur = conn.execute(
        "INSERT INTO equipment (name, description) VALUES (?, ?)",
        (args.name, args.description),
    )
    conn.commit()
    print(f"Added equipment {cur.lastrowid}: {args.name}")


def cmd_equipment_update(args, conn):
    get_equipment_or_die(conn, args.id)
    fields, values = [], []
    if args.name is not None:
        fields.append("name = ?")
        values.append(args.name)
    if args.description is not None:
        fields.append("description = ?")
        values.append(args.description)
    if not fields:
        print("Nothing to update.")
        return
    values.append(args.id)
    conn.execute(f"UPDATE equipment SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    print(f"Updated equipment {args.id}")


def cmd_equipment_remove(args, conn):
    get_equipment_or_die(conn, args.id)
    conn.execute("DELETE FROM loan WHERE equipment_id = ?", (args.id,))
    conn.execute("DELETE FROM equipment WHERE id = ?", (args.id,))
    conn.commit()
    print(f"Removed equipment {args.id}")


def cmd_equipment_search(args, conn):
    """List equipment with NO active loan overlapping the given date range."""
    rows = conn.execute("SELECT * FROM equipment ORDER BY id").fetchall()
    available = []
    for eq in rows:
        loans = conn.execute(
            "SELECT * FROM loan WHERE equipment_id = ? AND status = 'active'",
            (eq["id"],),
        ).fetchall()
        conflict = any(
            ranges_overlap(
                args.from_date,
                args.to_date,
                datetime.date.fromisoformat(l["from_date"]),
                datetime.date.fromisoformat(l["to_date"]),
            )
            for l in loans
        )
        if not conflict:
            available.append(eq)

    if not available:
        print("No equipment available in that date range.")
        return
    for r in available:
        print(f"{r['id']}\t{r['name']}\t{r['description'] or ''}")


# --------------------------------------------------------------------------- #
# loan sub-commands
# --------------------------------------------------------------------------- #
def cmd_loan_list(args, conn):
    rows = conn.execute("SELECT * FROM loan ORDER BY id").fetchall()
    if not rows:
        print("No loans found.")
        return
    for r in rows:
        print(
            f"{r['id']}\tequipment={r['equipment_id']}\t"
            f"{r['from_date']} -> {r['to_date']}\t{r['status']}"
        )


def cmd_loan_create(args, conn):
    get_equipment_or_die(conn, args.equipment)

    if args.from_date > args.to_date:
        print("Error: --from date must not be after --to date.", file=sys.stderr)
        sys.exit(1)

    active_loans = conn.execute(
        "SELECT * FROM loan WHERE equipment_id = ? AND status = 'active'",
        (args.equipment,),
    ).fetchall()
    for l in active_loans:
        if ranges_overlap(
            args.from_date,
            args.to_date,
            datetime.date.fromisoformat(l["from_date"]),
            datetime.date.fromisoformat(l["to_date"]),
        ):
            print(
                f"Error: equipment {args.equipment} is already loaned "
                f"from {l['from_date']} to {l['to_date']} (loan {l['id']}).",
                file=sys.stderr,
            )
            sys.exit(1)

    cur = conn.execute(
        "INSERT INTO loan (equipment_id, from_date, to_date, status) "
        "VALUES (?, ?, ?, 'active')",
        (args.equipment, args.from_date.isoformat(), args.to_date.isoformat()),
    )
    conn.commit()
    print(f"Created loan {cur.lastrowid}")


def cmd_loan_change(args, conn):
    loan = get_loan_or_die(conn, args.id)
    if loan["status"] != "active":
        print(f"Error: loan {args.id} is {loan['status']}, cannot be changed.",
              file=sys.stderr)
        sys.exit(1)

    new_from = args.from_date if args.from_date else datetime.date.fromisoformat(
        loan["from_date"]
    )
    new_to = args.to_date if args.to_date else datetime.date.fromisoformat(
        loan["to_date"]
    )
    if new_from > new_to:
        print("Error: --from date must not be after --to date.", file=sys.stderr)
        sys.exit(1)

    other_loans = conn.execute(
        "SELECT * FROM loan WHERE equipment_id = ? AND status = 'active' AND id != ?",
        (loan["equipment_id"], args.id),
    ).fetchall()
    for l in other_loans:
        if ranges_overlap(
            new_from,
            new_to,
            datetime.date.fromisoformat(l["from_date"]),
            datetime.date.fromisoformat(l["to_date"]),
        ):
            print(
                f"Error: new dates overlap with loan {l['id']} "
                f"({l['from_date']} -> {l['to_date']}).",
                file=sys.stderr,
            )
            sys.exit(1)

    conn.execute(
        "UPDATE loan SET from_date = ?, to_date = ? WHERE id = ?",
        (new_from.isoformat(), new_to.isoformat(), args.id),
    )
    conn.commit()
    print(f"Updated loan {args.id}")


def cmd_loan_cancel(args, conn):
    loan = get_loan_or_die(conn, args.id)
    if loan["status"] == "cancelled":
        print(f"Loan {args.id} is already cancelled.")
        return
    conn.execute("UPDATE loan SET status = 'cancelled' WHERE id = ?", (args.id,))
    conn.commit()
    print(f"Cancelled loan {args.id}")


# --------------------------------------------------------------------------- #
# Argument parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lending.py",
        description="Equipment Lending System - manage equipment and loans.",
    )
    sub = parser.add_subparsers(dest="entity", required=True)

    # equipment
    equipment = sub.add_parser("equipment", help="Manage equipment")
    equipment_sub = equipment.add_subparsers(dest="action", required=True)

    equipment_sub.add_parser("list", help="List all equipment").set_defaults(
        func=cmd_equipment_list
    )

    p = equipment_sub.add_parser("add", help="Add new equipment")
    p.add_argument("--name", required=True)
    p.add_argument("--description", default=None)
    p.set_defaults(func=cmd_equipment_add)

    p = equipment_sub.add_parser("update", help="Update equipment")
    p.add_argument("id", type=int)
    p.add_argument("--name", default=None)
    p.add_argument("--description", default=None)
    p.set_defaults(func=cmd_equipment_update)

    p = equipment_sub.add_parser("remove", help="Remove equipment")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_equipment_remove)

    p = equipment_sub.add_parser("search", help="Search available equipment")
    p.add_argument("--from", dest="from_date", type=parse_date, required=True)
    p.add_argument("--to", dest="to_date", type=parse_date, required=True)
    p.set_defaults(func=cmd_equipment_search)

    # loan
    loan = sub.add_parser("loan", help="Manage loans")
    loan_sub = loan.add_subparsers(dest="action", required=True)

    loan_sub.add_parser("list", help="List all loans").set_defaults(func=cmd_loan_list)

    p = loan_sub.add_parser("create", help="Create a loan")
    p.add_argument("--equipment", type=int, required=True)
    p.add_argument("--from", dest="from_date", type=parse_date, required=True)
    p.add_argument("--to", dest="to_date", type=parse_date, required=True)
    p.set_defaults(func=cmd_loan_create)

    p = loan_sub.add_parser("change", help="Change a loan's dates")
    p.add_argument("id", type=int)
    p.add_argument("--from", dest="from_date", type=parse_date, default=None)
    p.add_argument("--to", dest="to_date", type=parse_date, default=None)
    p.set_defaults(func=cmd_loan_change)

    p = loan_sub.add_parser("cancel", help="Cancel a loan")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_loan_cancel)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    conn = get_connection()
    try:
        args.func(args, conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
