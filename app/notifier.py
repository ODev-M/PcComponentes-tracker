"""Outgoing notifications to Discord.

Messages are routed through the bot when it is running (to a configured channel),
so this module only builds the embed payload. The bot owns the actual send.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class PriceDrop:
    product_id: int
    url: str
    name: str
    image_url: Optional[str]
    previous_price: float
    new_price: float
    lowest_ever: Optional[float]
    in_stock: bool

    @property
    def delta(self) -> float:
        return self.previous_price - self.new_price

    @property
    def percent(self) -> float:
        if self.previous_price <= 0:
            return 0.0
        return (self.delta / self.previous_price) * 100.0

    @property
    def is_new_low(self) -> bool:
        return self.lowest_ever is not None and self.new_price <= self.lowest_ever + 1e-6
