"""HTTP routes (web pages + JSON API)."""
from __future__ import annotations

import logging

from flask import Blueprint, abort, current_app, jsonify, render_template, request, send_from_directory

from . import db, scraper
from .categories import CATEGORIES, CATEGORIES_BY_SLUG, categorise

log = logging.getLogger(__name__)
bp = Blueprint("main", __name__)


def _row_to_dict(row):
    if not row:
        return None
    return {k: row[k] for k in row.keys()}


def _decorate(product: dict | None) -> dict | None:
    if not product:
        return None
    cat = CATEGORIES_BY_SLUG.get(product.get("category") or "other") or CATEGORIES_BY_SLUG["other"]
    product["category_label"] = cat.label
    product["category_icon"] = cat.icon
    return product


@bp.route("/sw.js")
def service_worker():
    # Served from root so its scope covers the whole site.
    return send_from_directory(current_app.static_folder, "sw.js", mimetype="application/javascript")


@bp.route("/")
def index():
    products = [_decorate(_row_to_dict(p)) for p in db.list_products()]

    present = {p["category"] for p in products}
    cats = [
        {"slug": c.slug, "label": c.label, "icon": c.icon,
         "count": sum(1 for p in products if p["category"] == c.slug)}
        for c in CATEGORIES if c.slug in present
    ]

    highlights = {
        "lows": [_decorate(_row_to_dict(r)) for r in db.at_historic_low(limit=6)],
        "drops": [_decorate(_row_to_dict(r)) for r in db.biggest_drops(days=30, limit=6)],
        "near_target": [_decorate(_row_to_dict(r)) for r in db.near_target(limit=6)],
    }

    return render_template(
        "index.html",
        products=products,
        categories=cats,
        highlights=highlights,
    )


@bp.route("/product/<int:product_id>")
def product_page(product_id: int):
    product = db.get_product(product_id)
    if not product:
        abort(404)
    return render_template("product.html", product=_decorate(_row_to_dict(product)))


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------

@bp.get("/api/products")
def api_list_products():
    return jsonify([_decorate(_row_to_dict(p)) for p in db.list_products()])


@bp.post("/api/products")
def api_add_product():
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    target = payload.get("target_price")

    if not scraper.is_valid_url(url):
        return jsonify({"error": "URL no válida. Solo se aceptan URLs de pccomponentes."}), 400

    try:
        scraped = scraper.scrape(url)
    except scraper.ScrapeError as exc:
        log.warning("scrape failed for %s: %s", url, exc)
        return jsonify({"error": str(exc)}), 502

    try:
        target_val = float(target) if target not in (None, "") else None
    except (TypeError, ValueError):
        target_val = None

    product_id = db.add_product(
        url, scraped.name, scraped.image_url, target_val, categorise(url)
    )
    db.record_price(product_id, scraped.price, scraped.in_stock)
    return jsonify(_decorate(_row_to_dict(db.get_product(product_id)))), 201


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
    return jsonify(_decorate(_row_to_dict(db.get_product(product_id))))


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
        "product": _decorate(_row_to_dict(product)),
        "lowest": db.lowest_price(product_id),
        "points": points,
    })


@bp.get("/api/categories")
def api_categories():
    counts = {r["category"]: r["n"] for r in db.category_counts()}
    return jsonify([
        {"slug": c.slug, "label": c.label, "icon": c.icon, "count": counts.get(c.slug, 0)}
        for c in CATEGORIES if counts.get(c.slug)
    ])


# ---------------------------------------------------------------------------
# Drops + notifications
# ---------------------------------------------------------------------------

@bp.get("/api/recent-drops")
def api_recent_drops():
    since = request.args.get("since")
    limit = int(request.args.get("limit", "20"))
    rows = db.recent_drops(limit=limit, since=since)
    return jsonify([
        {
            "id": r["id"],
            "product_id": r["product_id"],
            "name": r["name"],
            "url": r["url"],
            "image_url": r["image_url"],
            "category": r["category"],
            "previous_price": r["previous_price"],
            "new_price": r["new_price"],
            "percent": r["percent"],
            "is_new_low": bool(r["is_new_low"]),
            "in_stock": bool(r["in_stock"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ])


# ---------------------------------------------------------------------------
# Web Push (VAPID)
# ---------------------------------------------------------------------------

@bp.get("/api/push/public-key")
def api_push_public_key():
    from . import webpush  # local import to avoid hard dep during migrations
    return jsonify({"publicKey": webpush.public_key_b64() or ""})


@bp.post("/api/push/subscribe")
def api_push_subscribe():
    payload = request.get_json(silent=True) or {}
    endpoint = (payload.get("endpoint") or "").strip()
    keys = payload.get("keys") or {}
    p256dh = (keys.get("p256dh") or "").strip()
    auth = (keys.get("auth") or "").strip()
    ua = request.headers.get("User-Agent")

    if not (endpoint and p256dh and auth):
        return jsonify({"error": "Subscripción incompleta"}), 400

    db.save_push_subscription(endpoint, p256dh, auth, ua)
    return jsonify({"ok": True})


@bp.post("/api/push/unsubscribe")
def api_push_unsubscribe():
    payload = request.get_json(silent=True) or {}
    endpoint = (payload.get("endpoint") or "").strip()
    if not endpoint:
        return jsonify({"error": "Falta endpoint"}), 400
    db.delete_push_subscription(endpoint)
    return jsonify({"ok": True})
