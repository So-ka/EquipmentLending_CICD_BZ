"""The HTML forms: each workflow must be completable without the CLI or JSON."""


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
    first = {"equipment_id": "1", "from_date": "2026-11-01", "to_date": "2026-11-05"}
    r = client.post("/loans", data=first, follow_redirects=True)
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


# ---- error paths of the forms -------------------------------------------------
def test_missing_ids_redirect_with_message(client):
    for url in ("/equipment/99/edit", "/loans/99/edit"):
        r = client.get(url, follow_redirects=True)
        assert b"does not exist" in r.data
    assert b"does not exist" in client.post("/equipment/99/delete", follow_redirects=True).data
    assert b"does not exist" in client.post("/loans/99/cancel", follow_redirects=True).data


def test_equipment_edit_error_and_search_error(client):
    client.post("/equipment", data={"name": "Cam"})
    r = client.post("/equipment/1/edit", data={"name": "", "description": "x"})
    assert r.status_code == 400 and b"required" in r.data
    r = client.get("/equipment?available_from=2026-11-05&available_to=2026-11-01")
    assert b"must not be after" in r.data and b"Cam" in r.data  # error shown, full list still rendered


def test_loan_edit_error_keeps_page(client):
    client.post("/equipment", data={"name": "Cam"})
    client.post("/loans", data={"equipment_id": "1", "from_date": "2026-11-01", "to_date": "2026-11-05"})
    client.post("/loans", data={"equipment_id": "1", "from_date": "2026-11-10", "to_date": "2026-11-12"})
    r = client.post("/loans/1/edit", data={"from_date": "2026-11-01", "to_date": "2026-11-11"})
    assert r.status_code == 409 and b"already loaned" in r.data


def test_loans_page_filters_and_bad_filter(client):
    client.post("/equipment", data={"name": "Cam"})
    client.post("/loans", data={"equipment_id": "1", "from_date": "2026-11-01", "to_date": "2026-11-05"})
    assert b"2026-11-05" in client.get("/loans?equipment_id=1&status=active").data
    assert b"No loans found" in client.get("/loans?status=cancelled").data
    assert b"must be" in client.get("/loans?status=bogus").data


def test_loans_page_without_equipment(client):
    assert b"equipment</a> first" in client.get("/loans").data


# ---- CLI --------------------------------------------------------------------
def _cli(monkeypatch, tmp_path, capsys, *argv):
    import lending
    monkeypatch.setenv("LENDING_DB", str(tmp_path / "cli.db"))
    try:
        lending.main(list(argv))
        code = 0
    except SystemExit as e:
        code = e.code
    out = capsys.readouterr()
    return code, out.out, out.err


def test_cli_full_session(tmp_path, monkeypatch, capsys):
    run = lambda *a: _cli(monkeypatch, tmp_path, capsys, *a)  # noqa: E731
    assert "No equipment registered" in run("equipment", "list")[1]
    assert "Added equipment 1" in run("equipment", "add", "--name", "Cam", "--description", "d")[1]
    assert "Updated equipment 1" in run("equipment", "update", "1", "--name", "Camera")[1]
    create = ("loan", "create", "--equipment", "1", "--from", "2026-11-01", "--to", "2026-11-05")
    assert "Created loan 1" in run(*create)[1]
    assert "Updated loan 1" in run("loan", "change", "1", "--to", "2026-11-06")[1]
    assert "2026-11-06" in run("loan", "list")[1]
    assert "No equipment available" in run("equipment", "search", "--from", "2026-11-02", "--to", "2026-11-03")[1]
    assert "Cancelled loan 1" in run("loan", "cancel", "1")[1]
    assert "Camera" in run("equipment", "search", "--from", "2026-11-02", "--to", "2026-11-03")[1]
    assert "Removed equipment 1" in run("equipment", "remove", "1")[1]
    assert "No loans found" in run("loan", "list")[1]


def test_cli_errors_exit_1(tmp_path, monkeypatch, capsys):
    code, _, err = _cli(monkeypatch, tmp_path, capsys, "equipment", "remove", "9")
    assert code == 1 and "does not exist" in err
