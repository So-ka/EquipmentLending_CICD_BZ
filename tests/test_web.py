"""The HTML forms: each workflow must be completable without the CLI or JSON."""
from app import services as s
from app import db


def test_pages_render(client):
    for url in ("/", "/equipment", "/loans"):
        r = client.get(url, follow_redirects=True)
        assert r.status_code == 200 and b"Equipment Lending" in r.data


def test_equipment_form_workflow(client):
    r = client.post("/equipment", data={"name": "Projector", "description": "HD"}, follow_redirects=True)
    assert b"Added equipment #1" in r.data and b"Projector" in r.data
    r = client.post("/equipment/1/edit", data={"name": "Beamer", "description": ""}, follow_redirects=True)
    assert b"Updated equipment #1" in r.data and b"Beamer" in r.data
    r = client.post("/equipment/1/delete", follow_redirects=True)
    assert b"Removed equipment #1" in r.data and b"No equipment registered" in r.data


def test_equipment_form_error_keeps_input(client):
    r = client.post("/equipment", data={"name": " ", "description": "keep me"})
    assert r.status_code == 400 and b"keep me" in r.data and b"name" in r.data


def test_loan_form_workflow(client):
    client.post("/equipment", data={"name": "Camera"})
    r = client.post("/loans", data={"equipment_id": "1", "from_date": "2026-11-01", "to_date": "2026-11-05"}, follow_redirects=True)
    assert b"Created loan #1" in r.data and b"2026-11-05" in r.data

    r = client.post("/loans", data={"equipment_id": "1", "from_date": "2026-11-04", "to_date": "2026-11-09"})
    assert r.status_code == 409 and b"already loaned" in r.data
    assert b'value="2026-11-09"' in r.data  # form values preserved

    r = client.post("/loans/1/edit", data={"from_date": "2026-11-01", "to_date": "2026-11-07"}, follow_redirects=True)
    assert b"Updated loan #1" in r.data and b"2026-11-07" in r.data

    r = client.get("/equipment?available_from=2026-11-02&available_to=2026-11-03")
    assert b"No equipment available in that date range" in r.data

    r = client.post("/loans/1/cancel", follow_redirects=True)
    assert b"Cancelled loan #1" in r.data

    r = client.get("/equipment?available_from=2026-11-02&available_to=2026-11-03")
    assert b"Camera" in r.data
    assert b"no longer be changed" in client.get("/loans/1/edit").data


def test_loan_form_needs_equipment_choice(client):
    client.post("/equipment", data={"name": "Camera"})
    r = client.post("/loans", data={"equipment_id": "", "from_date": "2026-11-01", "to_date": "2026-11-05"})
    assert r.status_code == 400 and b"choose equipment" in r.data


def test_delete_with_active_loan_shows_message(client):
    client.post("/equipment", data={"name": "Camera"})
    client.post("/loans", data={"equipment_id": "1", "from_date": "2026-11-01", "to_date": "2026-11-05"})
    r = client.post("/equipment/1/delete", follow_redirects=True)
    assert b"has active loans" in r.data and b"Camera" in r.data


def test_html_is_escaped(client):
    client.post("/equipment", data={"name": "<script>alert(1)</script>"})
    assert b"<script>alert(1)" not in client.get("/equipment").data


def test_cli_wrapper_shares_rules(tmp_path, monkeypatch, capsys):
    import lending
    monkeypatch.setenv("LENDING_DB", str(tmp_path / "cli.db"))
    lending.main(["equipment", "add", "--name", "Cam"])
    lending.main(["loan", "create", "--equipment", "1", "--from", "2026-11-01", "--to", "2026-11-05"])
    try:
        lending.main(["loan", "create", "--equipment", "1", "--from", "2026-11-03", "--to", "2026-11-09"])
    except SystemExit as e:
        assert e.code == 1
    assert "already loaned" in capsys.readouterr().err
