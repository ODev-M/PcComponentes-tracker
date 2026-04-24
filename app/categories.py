"""Auto-categorise a PcComponentes URL based on its slug.

PcComponentes URLs look like:
  https://www.pccomponentes.com/<category-slug>/<product-slug>
  https://www.pccomponentes.com/gaming/tarjetas-graficas/<product-slug>

We match the path against a list of (slug_fragment, category) pairs, first
match wins. Keep the list ordered from most specific to most generic.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class Category:
    slug: str      # internal id
    label: str     # shown in UI
    icon: str      # emoji / glyph

CATEGORIES: list[Category] = [
    Category("gpu",        "Tarjetas gráficas",  "🎮"),
    Category("cpu",        "Procesadores",       "🧠"),
    Category("ram",        "Memoria RAM",        "🧩"),
    Category("ssd",        "SSD",                "💾"),
    Category("hdd",        "Discos duros",       "🗄️"),
    Category("psu",        "Fuentes",            "🔌"),
    Category("mobo",       "Placas base",        "🔧"),
    Category("case",       "Cajas",              "📦"),
    Category("cooling",    "Refrigeración",      "❄️"),
    Category("monitor",    "Monitores",          "🖥️"),
    Category("laptop",     "Portátiles",         "💻"),
    Category("desktop",    "Sobremesa",          "🖥️"),
    Category("peripheral", "Periféricos",        "🖱️"),
    Category("audio",      "Audio",              "🎧"),
    Category("phone",      "Smartphones",        "📱"),
    Category("tablet",     "Tablets",            "📟"),
    Category("tv",         "TV",                 "📺"),
    Category("networking", "Red",                "📡"),
    Category("console",    "Consolas",           "🎮"),
    Category("other",      "Otros",              "🔖"),
]

CATEGORIES_BY_SLUG = {c.slug: c for c in CATEGORIES}

# Order matters — longer/more specific matches go first.
_PATH_RULES: list[tuple[str, str]] = [
    # GPU
    ("tarjetas-graficas",                "gpu"),
    ("tarjeta-grafica",                  "gpu"),
    # CPU
    ("procesadores",                     "cpu"),
    ("procesador",                       "cpu"),
    # RAM
    ("memoria-ram",                      "ram"),
    ("memorias",                         "ram"),
    # Storage
    ("discos-ssd",                       "ssd"),
    ("ssd-nvme",                         "ssd"),
    ("unidades-ssd",                     "ssd"),
    ("disco-duro",                       "hdd"),
    ("discos-duros",                     "hdd"),
    ("hdd",                              "hdd"),
    # PSU / Mobo / Case / Cooling
    ("fuentes-de-alimentacion",          "psu"),
    ("placas-base",                      "mobo"),
    ("cajas-de-ordenador",               "case"),
    ("cajas-pc",                         "case"),
    ("refrigeracion",                    "cooling"),
    ("ventiladores",                     "cooling"),
    # Monitors
    ("monitores",                        "monitor"),
    # Laptops / desktops
    ("portatiles",                       "laptop"),
    ("ordenadores-portatiles",           "laptop"),
    ("ordenadores-sobremesa",            "desktop"),
    ("sobremesa",                        "desktop"),
    # Peripherals
    ("teclados",                         "peripheral"),
    ("ratones",                          "peripheral"),
    ("alfombrillas",                     "peripheral"),
    ("perifericos",                      "peripheral"),
    # Audio
    ("auriculares",                      "audio"),
    ("altavoces",                        "audio"),
    ("audio",                            "audio"),
    # Smartphone / tablet / tv
    ("smartphones",                      "phone"),
    ("moviles",                          "phone"),
    ("tablets",                          "tablet"),
    ("tv-television",                    "tv"),
    ("television",                       "tv"),
    # Networking
    ("redes",                            "networking"),
    ("routers",                          "networking"),
    ("wifi",                             "networking"),
    # Consoles
    ("consolas",                         "console"),
    ("videojuegos-consolas",             "console"),
]


def categorise(url: str) -> str:
    """Return the category slug that best matches the URL path."""
    try:
        path = urlparse(url).path.lower()
    except Exception:
        return "other"

    for fragment, slug in _PATH_RULES:
        if fragment in path:
            return slug
    return "other"
