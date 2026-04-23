"""HTTP routes (web pages + JSON API)."""
from __future__ import annotations

import logging

from flask import Blueprint, abort, jsonify, render_template, request

from . import db, scraper

log = logging.getLogger(__name__)
bp = Blueprint("main", __name__)


def _row_to_dict(row):
    return {k: row[k] for k in row.keys()} if row else None


@bp.route("/")
def index():
    products = [_row_to_dict(p) for p in db.list_products()]
    return render_template("index.html", products=products)


@bp.route("/product/<int:product_id>")
def product_page(product_id: int):
    product = db.get_product(product_id)
    if not product:
        abort(404)
    return render_template("product.html", product=_row_to_dict(product))


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------

@bp.get("/api/products")
def api_list_products():
    return jsonify([_row_to_dict(p) for p in db.list_products()])


@bp.post("/api/products")
def api_add_product():
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    target = payload.get("target_price")

    if not scraper.is_valid_url(url):
        return jsonify({"error": "URL no válida. Debe ser de pccomponentes."}), 400

    try:
        scraped = scraper.scrape(url)
    except scraper.ScrapeError as exc:
        log.warning("scrape failed for %s: %s", url, exc)
        return jsonify({"error": str(exc)}), 502

    try:
        target_val = float(target) if target not in (None, "",) else None
    except (TypeError, ValueError):
        target_val = None

    product_id = db.add_product(url, scraped.name, scraped.image_url, target_val)
    db.record_price(product_id, scraped.price, scraped.in_stock)
    return jsonify(_row_to_dict(db.get_product(product_id))), 201


@bp.delete("/api/products/<int:product_id>")
def api_delete_product(product_id: int):
    if not db.delete_product(product_id):
        return jsonify({"error": "No encontrado"}), 404
    return jsonify({"ok": True})


@bp.post("/api/products/<int:product_id>/check")
def api_check_product(product_id: int):
    product = db.get_product(product_id)
    if not product:
        return jsonify({"error": "No encontrado"}), 404

    try:
        scraped = scraper.scrape(product["url"])
    except scraper.ScrapeError as exc:
        return jsonify({"error": str(exc)}), 502

    db.record_price(product_id, scraped.price, scraped.in_stock)
    return jsonify(_row_to_dict(db.get_product(product_id)))


@bp.get("/api/products/<int:product_id>/history")
def api_history(product_id: int):
    product = db.get_product(product_id)
    if not product:
        return jsonify({"error": "No encontrado"}), 404

    points = [
        {"price": r["price"], "in_stock": bool(r["in_stock"]), "t": r["checked_at"]}
        for r in db.price_history(product_id)
    ]
    return jsonify({
        "product": _row_to_dict(product),
        "lowest": db.lowest_price(product_id),
        "points": points,
    })
