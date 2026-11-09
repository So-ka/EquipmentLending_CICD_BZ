"""JSON REST API, mounted at /api/v1. See openapi.yaml for the contract."""
from flask import Blueprint, Response, current_app, g, jsonify, request, url_for
from werkzeug.exceptions import HTTPException, InternalServerError

from . import services
from .errors import AppError, ValidationError

api = Blueprint("api", __name__)


def error_response(status, code, message, details=None):
    body = {"error": {"code": code, "message": message, "details": details or {}}}
    return jsonify(body), status


@api.errorhandler(AppError)
def _app_error(e):
    return error_response(e.status, e.code, e.message, e.details)


def _is_api():
    return request.path.startswith("/api/")


def register_error_handlers(app):
    """App-level so that routing errors (unknown URL, wrong method) under
    /api/ also get the JSON envelope; HTML pages keep Flask's default pages."""

    @app.errorhandler(AppError)
    def _app_error(e):
        return error_response(e.status, e.code, e.message, e.details)

    @app.errorhandler(HTTPException)
    def _http(e):
        if not _is_api():
            return e
        codes = {404: "not_found", 405: "method_not_allowed"}
        msg = {404: "No such resource.", 405: "Method not allowed for this resource."}
        body, status = error_response(
            e.code, codes.get(e.code, "bad_request" if e.code < 500 else "internal_error"),
            msg.get(e.code, e.name),
        )
        if e.code == 405 and e.valid_methods:
            body.headers["Allow"] = ", ".join(sorted(e.valid_methods))
        return body, status

    @app.errorhandler(Exception)
    def _unexpected(e):
        app.logger.exception("Unhandled error")
        if not _is_api():
            return InternalServerError()
        return error_response(500, "internal_error", "Unexpected server error.")


def json_body():
    if not request.is_json:
        raise _unsupported()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object.")
    return data


def _unsupported():
    e = AppError("Content-Type must be application/json.")
    e.status, e.code = 415, "unsupported_media_type"
    return e


def reject_unknown(data, allowed):
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise ValidationError(f"Unknown field(s): {', '.join(unknown)}.", {"fields": unknown})


def int_arg(name):
    raw = request.args.get(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        raise ValidationError(f"'{name}' must be an integer.", {"field": name}) from None


# ------------------------------------------------------------------- misc
@api.get("/health")
def health():
    g.db.execute("SELECT 1")
    return jsonify({"status": "ok"})


@api.get("/openapi.yaml")
def openapi_yaml():
    text = current_app.config["OPENAPI_PATH"].read_text(encoding="utf-8")
    return Response(text, mimetype="application/yaml")


@api.get("/docs")
def docs():
    html = """<!doctype html><html><head><meta charset="utf-8"><title>API docs</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui.css"></head>
<body><div id="ui"></div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui-bundle.js"></script>
<script>SwaggerUIBundle({url: "%s", dom_id: "#ui"});</script></body></html>""" % url_for("api.openapi_yaml")
    return Response(html, mimetype="text/html")


# -------------------------------------------------------------- equipment
@api.get("/equipment")
def equipment_list():
    items = services.list_equipment(
        g.db, request.args.get("available_from"), request.args.get("available_to")
    )
    return jsonify({"items": items, "count": len(items)})


@api.post("/equipment")
def equipment_create():
    data = json_body()
    reject_unknown(data, ("name", "description"))
    item = services.create_equipment(g.db, data.get("name"), data.get("description"))
    resp = jsonify(item)
    resp.status_code = 201
    resp.headers["Location"] = url_for("api.equipment_get", equipment_id=item["id"])
    return resp


@api.get("/equipment/<int:equipment_id>")
def equipment_get(equipment_id):
    return jsonify(services.get_equipment(g.db, equipment_id))


@api.patch("/equipment/<int:equipment_id>")
def equipment_update(equipment_id):
    return jsonify(services.update_equipment(g.db, equipment_id, json_body()))


@api.delete("/equipment/<int:equipment_id>")
def equipment_delete(equipment_id):
    services.delete_equipment(g.db, equipment_id)
    return "", 204


# ------------------------------------------------------------------ loans
@api.get("/loans")
def loans_list():
    items = services.list_loans(g.db, int_arg("equipment_id"), request.args.get("status"))
    return jsonify({"items": items, "count": len(items)})


@api.post("/loans")
def loans_create():
    data = json_body()
    reject_unknown(data, ("equipment_id", "from_date", "to_date"))
    loan = services.create_loan(
        g.db, data.get("equipment_id"), data.get("from_date"), data.get("to_date")
    )
    resp = jsonify(loan)
    resp.status_code = 201
    resp.headers["Location"] = url_for("api.loans_get", loan_id=loan["id"])
    return resp


@api.get("/loans/<int:loan_id>")
def loans_get(loan_id):
    return jsonify(services.get_loan(g.db, loan_id))


@api.patch("/loans/<int:loan_id>")
def loans_change(loan_id):
    return jsonify(services.change_loan(g.db, loan_id, json_body()))


@api.post("/loans/<int:loan_id>/cancel")
def loans_cancel(loan_id):
    return jsonify(services.cancel_loan(g.db, loan_id))
