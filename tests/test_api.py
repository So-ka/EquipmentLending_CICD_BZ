"""HTTP-level tests: URLs, methods, status codes, JSON shapes."""
import re

import yaml
from openapi_spec_validator import validate

from app import create_app

API = "/api/v1"


def loan_body(eq_id, f="2026-11-01", t="2026-11-05"):
    return {"equipment_id": eq_id, "from_date": f, "to_date": t}


def assert_error(resp, status, code):
    assert resp.status_code == status
    body = resp.get_json()
    assert body["error"]["code"] == code
    assert body["error"]["message"] and isinstance(body["error"]["details"], dict)


def test_health(client):
    assert client.get(f"{API}/health").get_json() == {"status": "ok"}


# --------------------------------------------------------------- equipment
def test_equipment_crud_flow(client):
    r = client.post(f"{API}/equipment", json={"name": "Projector", "description": "HD"})
    assert r.status_code == 201
    assert r.get_json() == {"id": 1, "name": "Projector", "description": "HD"}
    assert r.headers["Location"].endswith("/api/v1/equipment/1")

    assert client.get(f"{API}/equipment/1").get_json()["name"] == "Projector"
    assert client.get(f"{API}/equipment").get_json() == {"items": [r.get_json()], "count": 1}

    r = client.patch(f"{API}/equipment/1", json={"name": "Beamer"})
    assert r.status_code == 200 and r.get_json()["name"] == "Beamer"

    assert client.delete(f"{API}/equipment/1").status_code == 204
    assert_error(client.get(f"{API}/equipment/1"), 404, "not_found")


def test_equipment_validation_errors(client):
    assert_error(client.post(f"{API}/equipment", json={}), 400, "validation_error")
    assert_error(client.post(f"{API}/equipment", json={"name": 5}), 400, "validation_error")
    assert_error(client.post(f"{API}/equipment", json={"name": "a", "colour": "red"}), 400, "validation_error")
    assert_error(client.post(f"{API}/equipment", json=["x"]), 400, "validation_error")
    assert_error(client.post(f"{API}/equipment", data="{bad", content_type="application/json"), 400, "validation_error")
    assert_error(client.post(f"{API}/equipment", data="name=a"), 415, "unsupported_media_type")
    assert_error(client.patch(f"{API}/equipment/99", json={"name": "x"}), 404, "not_found")


def test_unknown_route_and_method_return_json(client):
    assert_error(client.get(f"{API}/nope"), 404, "not_found")
    assert_error(client.get(f"{API}/equipment/abc"), 404, "not_found")
    r = client.put(f"{API}/equipment/1", json={})
    assert_error(r, 405, "method_not_allowed")
    assert "GET" in r.headers["Allow"]


def test_equipment_availability_query(client, projector):
    client.post(f"{API}/equipment", json={"name": "Camera"})
    assert client.post(f"{API}/loans", json=loan_body(projector["id"])).status_code == 201
    r = client.get(f"{API}/equipment?available_from=2026-11-03&available_to=2026-11-04")
    assert [e["name"] for e in r.get_json()["items"]] == ["Camera"]
    assert_error(client.get(f"{API}/equipment?available_from=2026-11-03"), 400, "validation_error")
    assert_error(client.get(f"{API}/equipment?available_from=x&available_to=y"), 400, "validation_error")


def test_delete_equipment_with_active_loan_is_409(client, projector):
    loan = client.post(f"{API}/loans", json=loan_body(projector["id"])).get_json()
    r = client.delete(f"{API}/equipment/{projector['id']}")
    assert_error(r, 409, "conflict")
    assert r.get_json()["error"]["details"]["active_loan_ids"] == [loan["id"]]


# ------------------------------------------------------------------- loans
def test_loan_lifecycle(client, projector):
    r = client.post(f"{API}/loans", json=loan_body(projector["id"]))
    assert r.status_code == 201
    loan = r.get_json()
    assert loan["status"] == "active" and r.headers["Location"].endswith(f"/loans/{loan['id']}")

    assert client.get(f"{API}/loans/{loan['id']}").get_json() == loan
    r = client.patch(f"{API}/loans/{loan['id']}", json={"to_date": "2026-11-07"})
    assert r.status_code == 200 and r.get_json()["to_date"] == "2026-11-07"

    r = client.post(f"{API}/loans/{loan['id']}/cancel")
    assert r.status_code == 200 and r.get_json()["status"] == "cancelled"
    assert client.post(f"{API}/loans/{loan['id']}/cancel").status_code == 200  # idempotent
    assert_error(client.patch(f"{API}/loans/{loan['id']}", json={"to_date": "2026-11-09"}), 409, "conflict")

    assert client.get(f"{API}/loans?status=cancelled").get_json()["count"] == 1
    assert client.get(f"{API}/loans?status=active").get_json()["count"] == 0
    assert client.get(f"{API}/loans?equipment_id={projector['id']}").get_json()["count"] == 1


def test_overlap_is_409_with_details(client, projector):
    first = client.post(f"{API}/loans", json=loan_body(projector["id"])).get_json()
    r = client.post(f"{API}/loans", json=loan_body(projector["id"], "2026-11-03", "2026-11-10"))
    assert_error(r, 409, "conflict")
    assert r.get_json()["error"]["details"]["conflicting_loan_id"] == first["id"]


def test_loan_validation_errors(client, projector):
    eq = projector["id"]
    assert_error(client.post(f"{API}/loans", json=loan_body(eq, "2026-11-09", "2026-11-01")), 400, "validation_error")
    assert_error(client.post(f"{API}/loans", json=loan_body(eq, "tomorrow", "2026-11-01")), 400, "validation_error")
    assert_error(client.post(f"{API}/loans", json={"equipment_id": eq}), 400, "validation_error")
    assert_error(client.post(f"{API}/loans", json=loan_body("1")), 400, "validation_error")
    assert_error(client.post(f"{API}/loans", json=loan_body(999)), 404, "not_found")
    assert_error(client.get(f"{API}/loans?status=weird"), 400, "validation_error")
    assert_error(client.get(f"{API}/loans?equipment_id=abc"), 400, "validation_error")
    assert_error(client.get(f"{API}/loans/999"), 404, "not_found")
    assert_error(client.post(f"{API}/loans/999/cancel"), 404, "not_found")
    assert_error(client.patch(f"{API}/loans/999", json={"to_date": "2026-11-09"}), 404, "not_found")


# ------------------------------------------------------- persistence + spec
def test_data_persists_across_app_restarts(tmp_path):
    path = str(tmp_path / "persist.db")
    c1 = create_app(path).test_client()
    c1.post(f"{API}/equipment", json={"name": "Drone"})
    c2 = create_app(path).test_client()  # a "restart": new app object, same file
    assert c2.get(f"{API}/equipment").get_json()["items"][0]["name"] == "Drone"


def test_openapi_spec_is_valid_and_served(client):
    spec = yaml.safe_load(client.get(f"{API}/openapi.yaml").data)
    validate(spec)


def test_every_api_route_is_documented(client):
    """Fails if a route is added/removed without updating openapi.yaml."""
    app = client.application
    spec = yaml.safe_load(app.config["OPENAPI_PATH"].read_text())
    documented = {
        (path, m.upper())
        for path, item in spec["paths"].items()
        for m in item
        if m in ("get", "post", "put", "patch", "delete")
    }
    skip = {f"{API}/docs", f"{API}/openapi.yaml"}
    actual = set()
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith(API) and rule.rule not in skip:
            path = re.sub(r"<int:(\w+)>", lambda m: "{" + {"equipment_id": "equipmentId", "loan_id": "loanId"}[m.group(1)] + "}", rule.rule[len(API):])
            for m in rule.methods - {"HEAD", "OPTIONS"}:
                actual.add((path, m))
    assert actual == documented
