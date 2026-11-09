"""Unit tests for the business rules (no HTTP involved)."""
import pytest

from app import services as s
from app.errors import ConflictError, NotFoundError, ValidationError


@pytest.fixture
def eq(conn):
    return s.create_equipment(conn, "Camera", "DSLR")["id"]


# ----------------------------------------------------------- date handling
@pytest.mark.parametrize("bad", ["2026-13-01", "2026-02-30", "01/11/2026", "20261101", "2026-1-1", "", None, 20261101])
def test_parse_date_rejects_bad_values(bad):
    with pytest.raises(ValidationError):
        s.parse_date(bad)


def test_parse_date_accepts_iso():
    assert s.parse_date("2026-11-01").isoformat() == "2026-11-01"


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (("2026-11-01", "2026-11-05"), ("2026-11-03", "2026-11-10"), True),   # partial overlap
        (("2026-11-01", "2026-11-05"), ("2026-11-05", "2026-11-09"), True),   # touching day counts (inclusive)
        (("2026-11-01", "2026-11-05"), ("2026-11-06", "2026-11-09"), False),  # adjacent, no overlap
        (("2026-11-01", "2026-11-30"), ("2026-11-10", "2026-11-12"), True),   # containment
        (("2026-11-10", "2026-11-12"), ("2026-11-01", "2026-11-30"), True),
        (("2026-11-01", "2026-11-01"), ("2026-11-01", "2026-11-01"), True),   # same single day
    ],
)
def test_ranges_overlap(a, b, expected):
    d = s.parse_date
    assert s.ranges_overlap(d(a[0]), d(a[1]), d(b[0]), d(b[1])) is expected


# --------------------------------------------------------------- equipment
def test_equipment_name_required_and_trimmed(conn):
    with pytest.raises(ValidationError):
        s.create_equipment(conn, "   ")
    with pytest.raises(ValidationError):
        s.create_equipment(conn, None)
    assert s.create_equipment(conn, "  Laptop  ", "   ")["name"] == "Laptop"
    assert s.get_equipment(conn, 1)["description"] is None  # blank -> NULL


def test_equipment_length_limits(conn):
    with pytest.raises(ValidationError):
        s.create_equipment(conn, "x" * 101)
    with pytest.raises(ValidationError):
        s.create_equipment(conn, "ok", "x" * 501)


def test_update_equipment_partial_and_validation(conn, eq):
    s.update_equipment(conn, eq, {"description": None})
    got = s.get_equipment(conn, eq)
    assert got["name"] == "Camera" and got["description"] is None
    with pytest.raises(ValidationError):
        s.update_equipment(conn, eq, {})
    with pytest.raises(ValidationError):
        s.update_equipment(conn, eq, {"name": ""})
    with pytest.raises(ValidationError):
        s.update_equipment(conn, eq, {"colour": "red"})
    with pytest.raises(NotFoundError):
        s.update_equipment(conn, 999, {"name": "x"})


# ------------------------------------------------------------------- loans
def test_create_loan_happy_path(conn, eq):
    loan = s.create_loan(conn, eq, "2026-11-01", "2026-11-05")
    assert loan == {"id": 1, "equipment_id": eq, "from_date": "2026-11-01", "to_date": "2026-11-05", "status": "active"}


def test_create_loan_unknown_equipment(conn):
    with pytest.raises(NotFoundError):
        s.create_loan(conn, 42, "2026-11-01", "2026-11-05")


def test_create_loan_from_after_to(conn, eq):
    with pytest.raises(ValidationError):
        s.create_loan(conn, eq, "2026-11-05", "2026-11-01")


def test_one_day_loan_allowed(conn, eq):
    assert s.create_loan(conn, eq, "2026-11-01", "2026-11-01")["status"] == "active"


@pytest.mark.parametrize("bad_id", ["1", 1.5, None, True])
def test_create_loan_requires_integer_equipment_id(conn, bad_id):
    with pytest.raises(ValidationError):
        s.create_loan(conn, bad_id, "2026-11-01", "2026-11-05")


def test_overlapping_active_loan_rejected(conn, eq):
    s.create_loan(conn, eq, "2026-11-01", "2026-11-05")
    with pytest.raises(ConflictError) as err:
        s.create_loan(conn, eq, "2026-11-05", "2026-11-09")
    assert err.value.details["conflicting_loan_id"] == 1
    assert len(s.list_loans(conn)) == 1  # nothing was inserted


def test_overlap_only_applies_to_same_equipment(conn, eq):
    other = s.create_equipment(conn, "Laptop")["id"]
    s.create_loan(conn, eq, "2026-11-01", "2026-11-05")
    assert s.create_loan(conn, other, "2026-11-01", "2026-11-05")


def test_cancelled_loan_frees_the_dates(conn, eq):
    loan = s.create_loan(conn, eq, "2026-11-01", "2026-11-05")
    s.cancel_loan(conn, loan["id"])
    assert s.create_loan(conn, eq, "2026-11-02", "2026-11-04")["status"] == "active"


def test_cancel_is_idempotent(conn, eq):
    loan = s.create_loan(conn, eq, "2026-11-01", "2026-11-05")
    assert s.cancel_loan(conn, loan["id"])["status"] == "cancelled"
    assert s.cancel_loan(conn, loan["id"])["status"] == "cancelled"
    with pytest.raises(NotFoundError):
        s.cancel_loan(conn, 999)


def test_change_loan_keeps_missing_fields(conn, eq):
    loan = s.create_loan(conn, eq, "2026-11-01", "2026-11-05")
    out = s.change_loan(conn, loan["id"], {"to_date": "2026-11-07"})
    assert (out["from_date"], out["to_date"]) == ("2026-11-01", "2026-11-07")


def test_change_loan_can_overlap_itself_but_not_others(conn, eq):
    a = s.create_loan(conn, eq, "2026-11-01", "2026-11-05")
    s.create_loan(conn, eq, "2026-11-10", "2026-11-12")
    assert s.change_loan(conn, a["id"], {"to_date": "2026-11-09"})  # extends into own old range only
    with pytest.raises(ConflictError):
        s.change_loan(conn, a["id"], {"to_date": "2026-11-10"})
    assert s.get_loan(conn, a["id"])["to_date"] == "2026-11-09"  # unchanged after failure


def test_change_loan_rules(conn, eq):
    loan = s.create_loan(conn, eq, "2026-11-01", "2026-11-05")
    with pytest.raises(ValidationError):
        s.change_loan(conn, loan["id"], {"from_date": "2026-11-09"})  # would be after to_date
    with pytest.raises(ValidationError):
        s.change_loan(conn, loan["id"], {})
    with pytest.raises(NotFoundError):
        s.change_loan(conn, 999, {"to_date": "2026-11-09"})
    s.cancel_loan(conn, loan["id"])
    with pytest.raises(ConflictError):
        s.change_loan(conn, loan["id"], {"to_date": "2026-11-09"})


def test_list_loans_filters(conn, eq):
    other = s.create_equipment(conn, "Laptop")["id"]
    a = s.create_loan(conn, eq, "2026-11-01", "2026-11-02")
    s.create_loan(conn, other, "2026-11-01", "2026-11-02")
    s.cancel_loan(conn, a["id"])
    assert [l["id"] for l in s.list_loans(conn, status="active")] == [2]
    assert [l["id"] for l in s.list_loans(conn, equipment_id=eq)] == [1]
    with pytest.raises(ValidationError):
        s.list_loans(conn, status="bogus")


# ------------------------------------------------------------ availability
def test_availability_search(conn, eq):
    other = s.create_equipment(conn, "Laptop")["id"]
    s.create_loan(conn, eq, "2026-11-01", "2026-11-05")
    free = s.list_equipment(conn, "2026-11-04", "2026-11-08")
    assert [e["id"] for e in free] == [other]
    assert len(s.list_equipment(conn, "2026-11-06", "2026-11-08")) == 2


def test_availability_ignores_cancelled_loans(conn, eq):
    loan = s.create_loan(conn, eq, "2026-11-01", "2026-11-05")
    s.cancel_loan(conn, loan["id"])
    assert len(s.list_equipment(conn, "2026-11-01", "2026-11-05")) == 1


def test_availability_needs_both_dates_in_order(conn, eq):
    with pytest.raises(ValidationError):
        s.list_equipment(conn, "2026-11-01", None)
    with pytest.raises(ValidationError):
        s.list_equipment(conn, "2026-11-05", "2026-11-01")


# ----------------------------------------------------------- deleting
def test_delete_blocked_by_active_loan_but_removes_history(conn, eq):
    active = s.create_loan(conn, eq, "2026-11-01", "2026-11-05")
    with pytest.raises(ConflictError) as err:
        s.delete_equipment(conn, eq)
    assert err.value.details["active_loan_ids"] == [active["id"]]
    s.cancel_loan(conn, active["id"])
    s.delete_equipment(conn, eq)
    assert s.list_loans(conn) == [] and s.list_equipment(conn) == []
    with pytest.raises(NotFoundError):
        s.delete_equipment(conn, eq)


def test_concurrent_overlapping_requests_only_one_wins(tmp_path):
    """The overlap check and insert are one transaction, so racing requests
    from separate connections (as with multiple gunicorn workers) can't both pass."""
    import threading
    from app import db

    path = str(tmp_path / "race.db")
    db.init_db(path)
    c = db.connect(path)
    eq = s.create_equipment(c, "Laser")["id"]
    results = []
    barrier = threading.Barrier(8)

    def worker():
        conn = db.connect(path)
        barrier.wait()
        try:
            s.create_loan(conn, eq, "2026-11-01", "2026-11-05")
            results.append("ok")
        except ConflictError:
            results.append("conflict")
        finally:
            conn.close()

    threads = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count("ok") == 1 and results.count("conflict") == 7
    assert len(s.list_loans(c)) == 1
