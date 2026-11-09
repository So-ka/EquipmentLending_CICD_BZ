"""Server-rendered HTML forms for the same workflows as the API."""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from . import services
from .errors import ValidationError
from .errors import AppError

web = Blueprint("web", __name__)


def _form(*names):
    return {n: request.form.get(n, "") for n in names}


def _fail(template, e, **ctx):
    flash(e.message, "error")
    return render_template(template, **ctx), e.status


@web.get("/")
def index():
    return redirect(url_for("web.equipment_page"))


# -------------------------------------------------------------- equipment
def _equipment_ctx(form=None, search=None):
    avail_from = request.args.get("available_from", "").strip()
    avail_to = request.args.get("available_to", "").strip()
    return dict(
        form=form or {},
        search={"available_from": avail_from, "available_to": avail_to},
    )


@web.get("/equipment")
def equipment_page():
    ctx = _equipment_ctx()
    s = ctx["search"]
    try:
        if s["available_from"] or s["available_to"]:
            items = services.list_equipment(g.db, s["available_from"] or None, s["available_to"] or None)
            ctx["searching"] = True
        else:
            items = services.list_equipment(g.db)
    except AppError as e:
        flash(e.message, "error")
        items = services.list_equipment(g.db)
    return render_template("equipment.html", items=items, **ctx)


@web.post("/equipment")
def equipment_add():
    form = _form("name", "description")
    try:
        item = services.create_equipment(g.db, form["name"], form["description"])
    except AppError as e:
        return _fail("equipment.html", e, items=services.list_equipment(g.db), **_equipment_ctx(form))
    flash(f"Added equipment #{item['id']}: {item['name']}.", "ok")
    return redirect(url_for("web.equipment_page"))


@web.route("/equipment/<int:equipment_id>/edit", methods=["GET", "POST"])
def equipment_edit(equipment_id):
    try:
        item = services.get_equipment(g.db, equipment_id)
    except AppError as e:
        flash(e.message, "error")
        return redirect(url_for("web.equipment_page"))
    if request.method == "POST":
        form = _form("name", "description")
        try:
            services.update_equipment(g.db, equipment_id, form)
        except AppError as e:
            return _fail("equipment_edit.html", e, item=item, form=form)
        flash(f"Updated equipment #{equipment_id}.", "ok")
        return redirect(url_for("web.equipment_page"))
    return render_template("equipment_edit.html", item=item, form=item)


@web.post("/equipment/<int:equipment_id>/delete")
def equipment_delete(equipment_id):
    try:
        services.delete_equipment(g.db, equipment_id)
        flash(f"Removed equipment #{equipment_id}.", "ok")
    except AppError as e:
        flash(e.message, "error")
    return redirect(url_for("web.equipment_page"))


# ------------------------------------------------------------------ loans
def _loans_ctx(form=None):
    return dict(
        form=form or {},
        equipment=services.list_equipment(g.db),
        filter={"status": request.args.get("status", ""), "equipment_id": request.args.get("equipment_id", "")},
    )


@web.get("/loans")
def loans_page():
    ctx = _loans_ctx(form={"equipment_id": request.args.get("equipment_id", "")})
    try:
        eq = request.args.get("equipment_id", "")
        loans = services.list_loans(g.db, int(eq) if eq.isdigit() else None, request.args.get("status") or None)
    except AppError as e:
        flash(e.message, "error")
        loans = services.list_loans(g.db)
    names = {e["id"]: e["name"] for e in ctx["equipment"]}
    return render_template("loans.html", loans=loans, names=names, **ctx)


@web.post("/loans")
def loans_add():
    form = _form("equipment_id", "from_date", "to_date")
    try:
        eq = form["equipment_id"]
        if not eq.isdigit():
            raise ValidationError("Please choose equipment.", {"field": "equipment_id"})
        loan = services.create_loan(g.db, int(eq), form["from_date"], form["to_date"])
    except AppError as e:
        ctx = _loans_ctx(form)
        names = {x["id"]: x["name"] for x in ctx["equipment"]}
        return _fail("loans.html", e, loans=services.list_loans(g.db), names=names, **ctx)
    flash(f"Created loan #{loan['id']}.", "ok")
    return redirect(url_for("web.loans_page"))


@web.route("/loans/<int:loan_id>/edit", methods=["GET", "POST"])
def loan_edit(loan_id):
    try:
        loan = services.get_loan(g.db, loan_id)
        item = services.get_equipment(g.db, loan["equipment_id"])
    except AppError as e:
        flash(e.message, "error")
        return redirect(url_for("web.loans_page"))
    if request.method == "POST":
        form = _form("from_date", "to_date")
        try:
            services.change_loan(g.db, loan_id, form)
        except AppError as e:
            return _fail("loan_edit.html", e, loan=loan, item=item, form=form)
        flash(f"Updated loan #{loan_id}.", "ok")
        return redirect(url_for("web.loans_page"))
    return render_template("loan_edit.html", loan=loan, item=item, form=loan)


@web.post("/loans/<int:loan_id>/cancel")
def loan_cancel(loan_id):
    try:
        services.cancel_loan(g.db, loan_id)
        flash(f"Cancelled loan #{loan_id}.", "ok")
    except AppError as e:
        flash(e.message, "error")
    return redirect(url_for("web.loans_page"))
