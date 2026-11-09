#!/usr/bin/env python3
"""Equipment Lending System - command-line interface (kept from Checkpoint 1).

The CLI is now a thin wrapper over the same service layer the web app uses,
so the business rules are identical. Set LENDING_DB to choose the database.
"""
import argparse
import sys

from app import db, services
from app.errors import AppError


def build_parser():
    p = argparse.ArgumentParser(prog="lending.py", description="Equipment Lending System")
    sub = p.add_subparsers(dest="entity", required=True)

    eq = sub.add_parser("equipment").add_subparsers(dest="action", required=True)
    eq.add_parser("list")
    a = eq.add_parser("add")
    a.add_argument("--name", required=True)
    a.add_argument("--description")
    a = eq.add_parser("update")
    a.add_argument("id", type=int)
    a.add_argument("--name")
    a.add_argument("--description")
    a = eq.add_parser("remove")
    a.add_argument("id", type=int)
    a = eq.add_parser("search")
    a.add_argument("--from", dest="from_date", required=True)
    a.add_argument("--to", dest="to_date", required=True)

    ln = sub.add_parser("loan").add_subparsers(dest="action", required=True)
    ln.add_parser("list")
    a = ln.add_parser("create")
    a.add_argument("--equipment", type=int, required=True)
    a.add_argument("--from", dest="from_date", required=True)
    a.add_argument("--to", dest="to_date", required=True)
    a = ln.add_parser("change")
    a.add_argument("id", type=int)
    a.add_argument("--from", dest="from_date")
    a.add_argument("--to", dest="to_date")
    a = ln.add_parser("cancel")
    a.add_argument("id", type=int)
    return p


def run(args, conn):
    e, a = args.entity, args.action
    if e == "equipment":
        if a in ("list", "search"):
            items = services.list_equipment(conn, getattr(args, "from_date", None), getattr(args, "to_date", None))
            if not items:
                print("No equipment available in that date range." if a == "search" else "No equipment registered.")
            for r in items:
                print(f"{r['id']}\t{r['name']}\t{r['description'] or ''}")
        elif a == "add":
            r = services.create_equipment(conn, args.name, args.description)
            print(f"Added equipment {r['id']}: {r['name']}")
        elif a == "update":
            fields = {k: v for k in ("name", "description") if (v := getattr(args, k)) is not None}
            services.update_equipment(conn, args.id, fields)
            print(f"Updated equipment {args.id}")
        elif a == "remove":
            services.delete_equipment(conn, args.id)
            print(f"Removed equipment {args.id}")
    else:
        if a == "list":
            loans = services.list_loans(conn)
            if not loans:
                print("No loans found.")
            for r in loans:
                print(f"{r['id']}\tequipment={r['equipment_id']}\t{r['from_date']} -> {r['to_date']}\t{r['status']}")
        elif a == "create":
            r = services.create_loan(conn, args.equipment, args.from_date, args.to_date)
            print(f"Created loan {r['id']}")
        elif a == "change":
            fields = {k: v for k in ("from_date", "to_date") if (v := getattr(args, k)) is not None}
            services.change_loan(conn, args.id, fields)
            print(f"Updated loan {args.id}")
        elif a == "cancel":
            services.cancel_loan(conn, args.id)
            print(f"Cancelled loan {args.id}")


def main(argv=None):
    args = build_parser().parse_args(argv)
    db.init_db()
    conn = db.connect()
    try:
        run(args, conn)
    except AppError as e:
        print(f"Error: {e.message}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
