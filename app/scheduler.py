"""Background scheduler that re-scrapes tracked products."""
from __future__ import annotations

import logging
import os
from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from . import db, scraper
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

        if _drop_callback is None:
            continue

        # Notify on price drop
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
                try:
                    _drop_callback(drop)
                except Exception:
                    log.exception("drop_callback failed")

        # Notify when product comes back in stock
        if notify_stock and prev_status == "out_of_stock" and scraped.in_stock:
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
            try:
                _drop_callback(drop)
            except Exception:
                log.exception("drop_callback (restock) failed")


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
