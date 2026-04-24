"""Background scheduler that re-scrapes tracked products."""
from __future__ import annotations

import logging
import os
from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from . import db, scraper, webpush
from .notifier import PriceDrop

log = logging.getLogger(__name__)

# Callback signature: (PriceDrop) -> None. Set by bot on startup so the
# scheduler can hand off embeds without importing discord.py.
_drop_callback: Optional[Callable[[PriceDrop], None]] = None


def set_drop_callback(cb: Callable[[PriceDrop], None]) -> None:
    global _drop_callback
    _drop_callback = cb


def _min_drop_percent() -> float:
    try:
        return float(os.environ.get("MIN_DROP_PERCENT", "1.0"))
    except ValueError:
        return 1.0


def _notify_on_stock_change() -> bool:
    return os.environ.get("NOTIFY_ON_STOCK_CHANGE", "true").lower() in {"1", "true", "yes", "on"}


def _fan_out_webpush(drop: PriceDrop) -> None:
    """Send a push to every subscribed browser."""
    subs = db.list_push_subscriptions()
    if not subs:
        return

    payload = {
        "title": "¡Bajada de precio!" if drop.delta > 0 else "De nuevo disponible",
        "body": f"{drop.name[:80]} — {drop.new_price:.2f} €"
                + (f" (antes {drop.previous_price:.2f} €)" if drop.delta > 0 else ""),
        "icon": drop.image_url or "",
        "url": f"/product/{drop.product_id}",
        "tag": f"product-{drop.product_id}",
        "is_new_low": drop.is_new_low,
    }

    for row in subs:
        sub_info = {
            "endpoint": row["endpoint"],
            "keys": {"p256dh": row["p256dh"], "auth": row["auth"]},
        }
        try:
            webpush.send(sub_info, payload)
        except webpush.SubscriptionGone:
            log.info("pruning dead push subscription: %s", row["endpoint"][:60])
            db.delete_push_subscription(row["endpoint"])
        except Exception:
            log.exception("webpush fan-out error")


def check_all() -> None:
    products = db.list_products()
    log.info("scheduler: checking %d products", len(products))

    threshold = _min_drop_percent()
    notify_stock = _notify_on_stock_change()

    for p in products:
        try:
            scraped = scraper.scrape(p["url"])
        except scraper.ScrapeError as exc:
            log.warning("scrape failed for product %s: %s", p["id"], exc)
            continue

        prev_price = p["last_price"]
        prev_status = p["last_status"]
        db.record_price(p["id"], scraped.price, scraped.in_stock)

        drop: PriceDrop | None = None

        # Price drop
        if prev_price is not None and scraped.price < prev_price:
            delta = prev_price - scraped.price
            pct = (delta / prev_price) * 100.0 if prev_price > 0 else 0.0
            target = p["target_price"]
            if pct >= threshold or (target is not None and scraped.price <= target):
                drop = PriceDrop(
                    product_id=p["id"],
                    url=p["url"],
                    name=p["name"],
                    image_url=p["image_url"],
                    previous_price=prev_price,
                    new_price=scraped.price,
                    lowest_ever=db.lowest_price(p["id"]),
                    in_stock=scraped.in_stock,
                )

        # Restock event
        elif notify_stock and prev_status == "out_of_stock" and scraped.in_stock:
            drop = PriceDrop(
                product_id=p["id"],
                url=p["url"],
                name=p["name"],
                image_url=p["image_url"],
                previous_price=prev_price or scraped.price,
                new_price=scraped.price,
                lowest_ever=db.lowest_price(p["id"]),
                in_stock=True,
            )

        if drop is not None:
            # Persist event so the website can show a badge / recent drops feed.
            try:
                db.record_drop_event(
                    drop.product_id, drop.previous_price, drop.new_price,
                    drop.percent, drop.is_new_low, drop.in_stock,
                )
            except Exception:
                log.exception("failed to persist drop event")

            # Fan-out: Discord bot (if registered) and Web Push subscribers.
            if _drop_callback is not None:
                try:
                    _drop_callback(drop)
                except Exception:
                    log.exception("drop_callback failed")
            try:
                _fan_out_webpush(drop)
            except Exception:
                log.exception("webpush fan-out failed")


def start() -> BackgroundScheduler:
    interval = int(os.environ.get("CHECK_INTERVAL_MINUTES", "60"))
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(
        check_all,
        IntervalTrigger(minutes=interval),
        id="check_all",
        next_run_time=None,
        misfire_grace_time=300,
        coalesce=True,
    )
    sched.start()
    log.info("scheduler started — checking every %d minutes", interval)
    return sched
