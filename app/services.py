"""Business rules. Used by the REST API, the HTML forms and the CLI, so the
rules live in exactly one place and are unit-testable without HTTP."""
import re
from contextlib import contextmanager
from datetime import date

from .errors import ConflictError, NotFoundError, ValidationError

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_NAME = 100
MAX_DESCRIPTION = 500


# ------------------------------------------------------------------ helpers
@contextmanager
def transaction(conn):
    """BEGIN IMMEDIATE takes the write lock up front, so the overlap check and
    the insert/update that follows cannot be interleaved with another request."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def parse_date(value, field="date"):
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise ValidationError(
            f"'{field}' must be a date in YYYY-MM-DD format.", {"field": field}
        )
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"'{field}' is not a real calendar date.", {"field": field}) from None


def ranges_overlap(a_from, a_to, b_from, b_to):
    """Inclusive ranges overlap unless one ends before the other starts."""
    return a_from <= b_to and b_from <= a_to


def _clean_name(value):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("'name' is required and must be a non-empty string.", {"field": "name"})
    value = value.strip()
    if len(value) > MAX_NAME:
        raise ValidationError(f"'name' must be at most {MAX_NAME} characters.", {"field": "name"})
    return value


def _clean_description(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError("'description' must be a string or null.", {"field": "description"})
    value = value.strip()
    if len(value) > MAX_DESCRIPTION:
        raise ValidationError(
            f"'description' must be at most {MAX_DESCRIPTION} characters.", {"field": "description"}
        )
    return value or None


def _equipment(row):
    return {"id": row["id"], "name": row["name"], "description": row["description"]}


def _loan(row):
    return {
        "id": row["id"],
        "equipment_id": row["equipment_id"],
        "from_date": row["from_date"],
        "to_date": row["to_date"],
        "status": row["status"],
    }


def _check_range(from_d, to_d):
    if from_d > to_d:
        raise ValidationError(
            "'from_date' must not be after 'to_date'.",
            {"from_date": from_d.isoformat(), "to_date": to_d.isoformat()},
        )


def _find_conflict(conn, equipment_id, from_d, to_d, exclude_loan_id=None):
    rows = conn.execute(
        "SELECT * FROM loan WHERE equipment_id = ? AND status = 'active' AND id != ?",
        (equipment_id, exclude_loan_id or -1),
    ).fetchall()
    for r in rows:
        if ranges_overlap(
            from_d, to_d, date.fromisoformat(r["from_date"]), date.fromisoformat(r["to_date"])
        ):
            return r
    return None


# ---------------------------------------------------------------- equipment
def get_equipment(conn, equipment_id):
    row = conn.execute("SELECT * FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"Equipment {equipment_id} does not exist.", {"equipment_id": equipment_id})
    return _equipment(row)


def list_equipment(conn, available_from=None, available_to=None):
    """All equipment; if both dates are given, only items with no active loan
    overlapping that range. Giving just one of them is an error."""
    if (available_from is None) != (available_to is None):
        raise ValidationError(
            "'available_from' and 'available_to' must be provided together.",
            {"fields": ["available_from", "available_to"]},
        )
    rows = conn.execute("SELECT * FROM equipment ORDER BY id").fetchall()
    items = [_equipment(r) for r in rows]
    if available_from is None:
        return items
    f = parse_date(available_from, "available_from")
    t = parse_date(available_to, "available_to")
    _check_range(f, t)
    return [e for e in items if _find_conflict(conn, e["id"], f, t) is None]


def create_equipment(conn, name, description=None):
    name, description = _clean_name(name), _clean_description(description)
    cur = conn.execute(
        "INSERT INTO equipment (name, description) VALUES (?, ?)", (name, description)
    )
    return get_equipment(conn, cur.lastrowid)


def update_equipment(conn, equipment_id, fields):
    """`fields` holds only the keys the caller wants to change (PATCH semantics)."""
    get_equipment(conn, equipment_id)
    unknown = set(fields) - {"name", "description"}
    if unknown:
        raise ValidationError(f"Unknown field(s): {', '.join(sorted(unknown))}.", {"fields": sorted(unknown)})
    if not fields:
        raise ValidationError("Provide at least one of 'name' or 'description'.")
    sets, values = [], []
    if "name" in fields:
        sets.append("name = ?")
        values.append(_clean_name(fields["name"]))
    if "description" in fields:
        sets.append("description = ?")
        values.append(_clean_description(fields["description"]))
    conn.execute(f"UPDATE equipment SET {', '.join(sets)} WHERE id = ?", (*values, equipment_id))
    return get_equipment(conn, equipment_id)


def delete_equipment(conn, equipment_id):
    """Refuses while active loans exist; cancelled loans are history and are
    removed along with the equipment."""
    get_equipment(conn, equipment_id)
    with transaction(conn):
        active = conn.execute(
            "SELECT id FROM loan WHERE equipment_id = ? AND status = 'active'", (equipment_id,)
        ).fetchall()
        if active:
            ids = [r["id"] for r in active]
            raise ConflictError(
                f"Equipment {equipment_id} has active loans; cancel them first.",
                {"active_loan_ids": ids},
            )
        conn.execute("DELETE FROM loan WHERE equipment_id = ?", (equipment_id,))
        conn.execute("DELETE FROM equipment WHERE id = ?", (equipment_id,))


# -------------------------------------------------------------------- loans
def get_loan(conn, loan_id):
    row = conn.execute("SELECT * FROM loan WHERE id = ?", (loan_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"Loan {loan_id} does not exist.", {"loan_id": loan_id})
    return _loan(row)


def list_loans(conn, equipment_id=None, status=None):
    if status is not None and status not in ("active", "cancelled"):
        raise ValidationError("'status' must be 'active' or 'cancelled'.", {"field": "status"})
    sql, params = "SELECT * FROM loan WHERE 1=1", []
    if equipment_id is not None:
        sql += " AND equipment_id = ?"
        params.append(equipment_id)
    if status is not None:
        sql += " AND status = ?"
        params.append(status)
    return [_loan(r) for r in conn.execute(sql + " ORDER BY id", params).fetchall()]


def _conflict_error(c, equipment_id):
    return ConflictError(
        f"Equipment {equipment_id} is already loaned from {c['from_date']} to "
        f"{c['to_date']} (loan {c['id']}).",
        {"conflicting_loan_id": c["id"], "from_date": c["from_date"], "to_date": c["to_date"]},
    )


def create_loan(conn, equipment_id, from_date, to_date):
    if isinstance(equipment_id, bool) or not isinstance(equipment_id, int):
        raise ValidationError("'equipment_id' must be an integer.", {"field": "equipment_id"})
    f, t = parse_date(from_date, "from_date"), parse_date(to_date, "to_date")
    _check_range(f, t)
    get_equipment(conn, equipment_id)
    with transaction(conn):
        c = _find_conflict(conn, equipment_id, f, t)
        if c:
            raise _conflict_error(c, equipment_id)
        cur = conn.execute(
            "INSERT INTO loan (equipment_id, from_date, to_date, status) VALUES (?, ?, ?, 'active')",
            (equipment_id, f.isoformat(), t.isoformat()),
        )
    return get_loan(conn, cur.lastrowid)


def change_loan(conn, loan_id, fields):
    """Change dates of an *active* loan. Keys absent from `fields` are kept."""
    unknown = set(fields) - {"from_date", "to_date"}
    if unknown:
        raise ValidationError(f"Unknown field(s): {', '.join(sorted(unknown))}.", {"fields": sorted(unknown)})
    if not fields:
        raise ValidationError("Provide at least one of 'from_date' or 'to_date'.")
    with transaction(conn):
        loan = get_loan(conn, loan_id)
        if loan["status"] != "active":
            raise ConflictError(
                f"Loan {loan_id} is {loan['status']} and cannot be changed.", {"status": loan["status"]}
            )
        f = parse_date(fields.get("from_date", loan["from_date"]), "from_date")
        t = parse_date(fields.get("to_date", loan["to_date"]), "to_date")
        _check_range(f, t)
        c = _find_conflict(conn, loan["equipment_id"], f, t, exclude_loan_id=loan_id)
        if c:
            raise _conflict_error(c, loan["equipment_id"])
        conn.execute(
            "UPDATE loan SET from_date = ?, to_date = ? WHERE id = ?",
            (f.isoformat(), t.isoformat(), loan_id),
        )
    return get_loan(conn, loan_id)


def cancel_loan(conn, loan_id):
    """Idempotent: cancelling an already-cancelled loan is a no-op."""
    get_loan(conn, loan_id)
    conn.execute("UPDATE loan SET status = 'cancelled' WHERE id = ?", (loan_id,))
    return get_loan(conn, loan_id)
