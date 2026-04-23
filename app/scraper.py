"""Scraper for PcComponentes product pages.

Strategy:
1. Use cloudscraper to bypass Cloudflare challenges.
2. Prefer structured JSON-LD (<script type="application/ld+json">) because
   it exposes name, image and offers.price in a stable machine-readable form.
3. Fall back to HTML selectors if JSON-LD is missing.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

import cloudscraper
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

_URL_RE = re.compile(r"^https?://(?:www\.)?pccomponentes\.(?:com|pt|fr|it)/.+", re.I)


@dataclass
class ScrapedProduct:
    url: str
    name: str
    price: float
    image_url: Optional[str]
    in_stock: bool
    currency: str = "EUR"


class ScrapeError(Exception):
    pass


def is_valid_url(url: str) -> bool:
    return bool(_URL_RE.match(url or ""))


def _scraper():
    return cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "linux", "desktop": True},
        delay=5,
    )


def _fetch(url: str) -> str:
    ua = os.environ.get("USER_AGENT") or None
    timeout = int(os.environ.get("REQUEST_TIMEOUT", "20"))
    headers = {"Accept-Language": "es-ES,es;q=0.9,en;q=0.8"}
    if ua:
        headers["User-Agent"] = ua

    s = _scraper()
    r = s.get(url, headers=headers, timeout=timeout)
    if r.status_code != 200:
        raise ScrapeError(f"HTTP {r.status_code} fetching {url}")
    return r.text


def _parse_price(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace("\u00a0", " ").strip()
        cleaned = re.sub(r"[^\d,\.]", "", cleaned)
        if not cleaned:
            return None
        # European format: 1.234,56 -> 1234.56
        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _json_ld_products(soup: BeautifulSoup):
    for tag in soup.find_all("script", type="application/ld+json"):
        raw = tag.string or tag.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            t = item.get("@type")
            types = t if isinstance(t, list) else [t]
            if any((tt or "").lower() == "product" for tt in types):
                yield item


def _extract_from_jsonld(soup: BeautifulSoup) -> Optional[ScrapedProduct]:
    for item in _json_ld_products(soup):
        name = item.get("name")
        image = item.get("image")
        if isinstance(image, list) and image:
            image = image[0]
        offers = item.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}

        price = _parse_price(offers.get("price")) if isinstance(offers, dict) else None
        currency = (offers.get("priceCurrency") if isinstance(offers, dict) else None) or "EUR"
        availability = (offers.get("availability") or "") if isinstance(offers, dict) else ""
        in_stock = "instock" in availability.lower() or availability == ""

        if name and price is not None:
            return ScrapedProduct(
                url="",
                name=name.strip(),
                price=price,
                image_url=image if isinstance(image, str) else None,
                in_stock=in_stock,
                currency=currency,
            )
    return None


def _extract_from_html(soup: BeautifulSoup) -> Optional[ScrapedProduct]:
    name_tag = soup.select_one("h1[data-e2e='pdp-title']") or soup.select_one("h1")
    price_tag = soup.select_one("[data-e2e='pdp-price-current-integer']")
    price = None
    if price_tag:
        integer = price_tag.get_text(strip=True)
        decimal_tag = soup.select_one("[data-e2e='pdp-price-current-decimal']")
        decimal = decimal_tag.get_text(strip=True) if decimal_tag else "00"
        price = _parse_price(f"{integer},{decimal}")
    if price is None:
        meta_price = soup.find("meta", attrs={"itemprop": "price"}) or soup.find(
            "meta", attrs={"property": "product:price:amount"}
        )
        if meta_price and meta_price.get("content"):
            price = _parse_price(meta_price["content"])

    if not name_tag or price is None:
        return None

    img_tag = soup.select_one("img[data-e2e='pdp-image']") or soup.select_one("meta[property='og:image']")
    image_url = None
    if img_tag:
        image_url = img_tag.get("content") or img_tag.get("src")

    return ScrapedProduct(
        url="",
        name=name_tag.get_text(strip=True),
        price=price,
        image_url=image_url,
        in_stock=True,
    )


def scrape(url: str) -> ScrapedProduct:
    if not is_valid_url(url):
        raise ScrapeError("URL no válida — debe ser de pccomponentes.com/.pt/.fr/.it")
    html = _fetch(url)
    soup = BeautifulSoup(html, "lxml")

    product = _extract_from_jsonld(soup) or _extract_from_html(soup)
    if not product:
        raise ScrapeError("No se pudo extraer precio — la página puede haber cambiado.")

    product.url = url
    return product
