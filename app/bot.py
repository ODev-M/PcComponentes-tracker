"""Discord bot: notifications + slash commands.

Commands (slash):
  /add <url> [target_price]     Track a new PcComponentes product
  /list                         List tracked products
  /remove <product_id>          Stop tracking a product
  /check <product_id>           Force a price check right now

Only users whose IDs appear in DISCORD_ADMIN_IDS can use commands.
If that list is empty, anyone can use them (use with care).
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import discord
from discord import app_commands

from . import db, scraper
from .notifier import PriceDrop

log = logging.getLogger(__name__)


def _admin_ids() -> set[int]:
    raw = os.environ.get("DISCORD_ADMIN_IDS", "")
    out: set[int] = set()
    for piece in raw.split(","):
        piece = piece.strip()
        if piece.isdigit():
            out.add(int(piece))
    return out


def _is_admin(user: discord.abc.User) -> bool:
    admins = _admin_ids()
    return not admins or user.id in admins


def _euro(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _build_drop_embed(drop: PriceDrop) -> discord.Embed:
    emoji = "🔥" if drop.is_new_low else "📉"
    title = f"{emoji} ¡Bajada de precio!" if drop.delta > 0 else "📦 De nuevo disponible"
    embed = discord.Embed(
        title=title,
        description=f"**[{drop.name}]({drop.url})**",
        color=0xE54B4B if drop.is_new_low else 0xF5A524,
    )
    embed.add_field(name="Antes", value=_euro(drop.previous_price), inline=True)
    embed.add_field(name="Ahora", value=_euro(drop.new_price), inline=True)
    if drop.delta > 0:
        embed.add_field(
            name="Baja",
            value=f"**−{_euro(drop.delta)}** ({drop.percent:.1f}%)",
            inline=True,
        )
    if drop.lowest_ever is not None:
        footer = "🏆 Nuevo mínimo histórico" if drop.is_new_low else f"Mínimo histórico: {_euro(drop.lowest_ever)}"
        embed.set_footer(text=footer)
    if drop.image_url:
        embed.set_thumbnail(url=drop.image_url)
    return embed


class TrackerBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self._notify_queue: asyncio.Queue[PriceDrop] = asyncio.Queue()

    async def setup_hook(self) -> None:
        self._register_commands()
        await self.tree.sync()
        self.loop.create_task(self._notify_worker())

    async def on_ready(self) -> None:
        log.info("bot ready as %s", self.user)

    # ---- queue bridge (called from sync scheduler thread) ----
    def enqueue_drop(self, drop: PriceDrop) -> None:
        try:
            self.loop.call_soon_threadsafe(self._notify_queue.put_nowait, drop)
        except RuntimeError:
            log.warning("event loop not running yet; drop dropped")

    async def _notify_worker(self) -> None:
        await self.wait_until_ready()
        channel_id_raw = os.environ.get("DISCORD_NOTIFY_CHANNEL_ID", "").strip()
        if not channel_id_raw.isdigit():
            log.warning("DISCORD_NOTIFY_CHANNEL_ID not set — notifications disabled")
            return
        channel_id = int(channel_id_raw)

        while not self.is_closed():
            drop = await self._notify_queue.get()
            try:
                channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)
                await channel.send(embed=_build_drop_embed(drop))
            except Exception:
                log.exception("failed to deliver drop notification")

    def _register_commands(self) -> None:
        tree = self.tree

        @tree.command(name="add", description="Añadir un producto de PcComponentes")
        @app_commands.describe(url="URL del producto", target_price="Precio objetivo (opcional)")
        async def add(interaction: discord.Interaction, url: str, target_price: Optional[float] = None):
            if not _is_admin(interaction.user):
                await interaction.response.send_message("No autorizado.", ephemeral=True)
                return
            await interaction.response.defer(thinking=True, ephemeral=True)
            try:
                scraped = await asyncio.to_thread(scraper.scrape, url)
            except scraper.ScrapeError as exc:
                await interaction.followup.send(f"Error: {exc}", ephemeral=True)
                return
            pid = await asyncio.to_thread(db.add_product, url, scraped.name, scraped.image_url, target_price)
            await asyncio.to_thread(db.record_price, pid, scraped.price, scraped.in_stock)
            await interaction.followup.send(
                f"✅ Añadido **{scraped.name}** — {_euro(scraped.price)}", ephemeral=True
            )

        @tree.command(name="list", description="Listar productos rastreados")
        async def list_cmd(interaction: discord.Interaction):
            if not _is_admin(interaction.user):
                await interaction.response.send_message("No autorizado.", ephemeral=True)
                return
            rows = await asyncio.to_thread(db.list_products)
            if not rows:
                await interaction.response.send_message("No hay productos.", ephemeral=True)
                return
            embed = discord.Embed(title="Productos rastreados", color=0x2DDAFD)
            for r in rows[:25]:
                price = _euro(r["last_price"])
                target = f" · obj {_euro(r['target_price'])}" if r["target_price"] else ""
                embed.add_field(
                    name=f"#{r['id']} — {r['name'][:80]}",
                    value=f"{price}{target}\n{r['url']}",
                    inline=False,
                )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        @tree.command(name="remove", description="Dejar de rastrear un producto")
        @app_commands.describe(product_id="ID del producto")
        async def remove(interaction: discord.Interaction, product_id: int):
            if not _is_admin(interaction.user):
                await interaction.response.send_message("No autorizado.", ephemeral=True)
                return
            ok = await asyncio.to_thread(db.delete_product, product_id)
            msg = "✅ Eliminado" if ok else "❌ No encontrado"
            await interaction.response.send_message(msg, ephemeral=True)

        @tree.command(name="check", description="Forzar comprobación inmediata")
        @app_commands.describe(product_id="ID del producto")
        async def check(interaction: discord.Interaction, product_id: int):
            if not _is_admin(interaction.user):
                await interaction.response.send_message("No autorizado.", ephemeral=True)
                return
            await interaction.response.defer(thinking=True, ephemeral=True)
            product = await asyncio.to_thread(db.get_product, product_id)
            if not product:
                await interaction.followup.send("❌ No encontrado", ephemeral=True)
                return
            try:
                scraped = await asyncio.to_thread(scraper.scrape, product["url"])
            except scraper.ScrapeError as exc:
                await interaction.followup.send(f"Error: {exc}", ephemeral=True)
                return
            await asyncio.to_thread(db.record_price, product_id, scraped.price, scraped.in_stock)
            await interaction.followup.send(f"Precio actual: **{_euro(scraped.price)}**", ephemeral=True)


def run_bot_blocking(token: str) -> None:
    bot = TrackerBot()
    # Expose the enqueue method to the scheduler via module-level handle.
    globals()["_BOT_SINGLETON"] = bot

    from . import scheduler as sched_mod
    sched_mod.set_drop_callback(lambda drop: bot.enqueue_drop(drop))

    bot.run(token)


def get_bot() -> Optional[TrackerBot]:
    return globals().get("_BOT_SINGLETON")
