# 💰 PcComponentes Price Tracker

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776ab.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/flask-3.0-000?logo=flask)](https://flask.palletsprojects.com/)
[![Discord.py](https://img.shields.io/badge/discord.py-2.4-5865f2?logo=discord&logoColor=white)](https://discordpy.readthedocs.io/)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

Price tracker self-hosted para [PcComponentes](https://www.pccomponentes.com) con:

- 🔎 **Scraper** que esquiva Cloudflare y lee el JSON-LD embebido
- ⏱ **Scheduler** (APScheduler) que revisa precios cada hora
- 🤖 **Bot de Discord** con slash commands (`/add`, `/list`, `/remove`, `/check`) y embeds bonitos
- 🌐 **Web frontend** responsive con dark mode, tarjetas y **gráfica Chart.js** del histórico
- 🔔 **Notificaciones inteligentes**: solo avisa si la bajada supera un umbral (`MIN_DROP_PERCENT`) o si el producto vuelve a estar disponible
- 🗄 **SQLite** — cero setup de BD
- 🛡 Preparado para **systemd** (o **PM2** si lo prefieres)

> Proyecto de portafolio open source. PRs e issues bienvenidos.

---

## 🚀 Instalación en un VPS con Ubuntu

### 1. Dependencias del sistema

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

### 2. Clonar e instalar

```bash
sudo mkdir -p /opt/pccomponentes-tracker
sudo chown "$USER:$USER" /opt/pccomponentes-tracker
git clone https://github.com/Odev-M/pccomponentes-tracker.git /opt/pccomponentes-tracker
cd /opt/pccomponentes-tracker

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configurar variables

```bash
cp .env.example .env
nano .env
```

Rellena como mínimo:

| Variable | Descripción |
|---|---|
| `DISCORD_BOT_TOKEN` | Token del bot ([Discord Developer Portal](https://discord.com/developers/applications)) |
| `DISCORD_NOTIFY_CHANNEL_ID` | ID del canal donde enviará las alertas |
| `DISCORD_ADMIN_IDS` | Tu ID de Discord (para usar los slash commands) |
| `CHECK_INTERVAL_MINUTES` | Cada cuántos minutos revisar precios (def. `60`) |
| `MIN_DROP_PERCENT` | Umbral mínimo de bajada para notificar (def. `1.0`) |

### 4. (Opcional) Invitar el bot a tu servidor

En el Developer Portal → OAuth2 → URL Generator:
- Scopes: `bot`, `applications.commands`
- Bot permissions: `Send Messages`, `Embed Links`, `Read Message History`

Pega la URL generada en tu navegador y autoriza el bot.

### 5. Arrancar (systemd, recomendado)

```bash
sudo useradd --system --home /opt/pccomponentes-tracker --shell /usr/sbin/nologin pctracker
sudo chown -R pctracker:pctracker /opt/pccomponentes-tracker
sudo mkdir -p /opt/pccomponentes-tracker/{data,logs}
sudo chown pctracker:pctracker /opt/pccomponentes-tracker/{data,logs}

sudo cp deploy/pccomponentes-tracker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pccomponentes-tracker
```

Logs en tiempo real:

```bash
sudo journalctl -u pccomponentes-tracker -f
```

### Alternativa: PM2

```bash
npm install -g pm2
pm2 start ecosystem.config.js
pm2 save && pm2 startup
```

### 6. Reverse proxy con Nginx (opcional)

```nginx
server {
    listen 80;
    server_name tracker.tudominio.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Después `certbot --nginx -d tracker.tudominio.com` y listo.

---

## 🧑‍💻 Desarrollo local

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

Abre http://127.0.0.1:5000

---

## 📂 Estructura

```
app/
 ├─ __init__.py        # Flask factory
 ├─ routes.py          # Web pages + JSON API
 ├─ db.py              # SQLite schema + helpers
 ├─ scraper.py         # cloudscraper + JSON-LD + fallback HTML
 ├─ scheduler.py       # APScheduler hourly job
 ├─ bot.py             # discord.py slash commands + embeds
 ├─ notifier.py        # PriceDrop dataclass
 ├─ templates/         # Jinja2 (base, index, product)
 └─ static/            # CSS + JS (Tailwind CDN + Chart.js)
run.py                 # Entrypoint: Flask + scheduler + bot
deploy/
 └─ pccomponentes-tracker.service   # systemd unit
ecosystem.config.js    # PM2 (alternativa)
```

---

## 🧠 Cómo funciona el scraper

1. `cloudscraper` abre la página simulando Chrome en Linux para pasar Cloudflare.
2. Se busca un `<script type="application/ld+json">` con `@type: Product`. Ahí PcComponentes publica `name`, `image` y `offers.price` de forma estable.
3. Si no hay JSON-LD (raro), caemos a selectores HTML (`[data-e2e="pdp-price-current-integer"]` + meta tags).
4. Los precios se guardan en `price_history` junto al timestamp UTC.

---

## 🤝 Contribuir

Lee [CONTRIBUTING.md](CONTRIBUTING.md). Tipos de contribuciones útiles:

- Nuevos sitios (AliExpress, Amazon, Coolmod, Vibbo…) → ampliar `scraper.py` con estrategia
- Mejoras UI
- Tests (`pytest` aún no está — ¡se agradece!)
- Traducciones del frontend

---

## 📄 Licencia

MIT © 2026 [Odev-M](https://github.com/Odev-M)
