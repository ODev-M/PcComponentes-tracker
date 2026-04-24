// Homepage interactions: add form + delete + category filter
// + recent-drops badge + web push subscription.

// ---------------------------------------------------------------------------
// Toast helper
// ---------------------------------------------------------------------------
function toast(message, kind = 'ok') {
    const root = document.getElementById('toast-root');
    if (!root) return;
    const el = document.createElement('div');
    el.className = `toast ${kind}`;
    el.textContent = message;
    root.appendChild(el);
    setTimeout(() => {
        el.style.transition = 'opacity 200ms, transform 200ms';
        el.style.opacity = '0';
        el.style.transform = 'translateY(6px)';
        setTimeout(() => el.remove(), 220);
    }, 2800);
}

async function api(path, opts = {}) {
    const res = await fetch(path, {
        headers: { 'Content-Type': 'application/json' },
        ...opts,
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
    return body;
}

// ---------------------------------------------------------------------------
// Add form
// ---------------------------------------------------------------------------
const form = document.getElementById('add-form');
if (form) {
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const url = document.getElementById('url-input').value.trim();
        const target = document.getElementById('target-input').value.trim();
        const btn = form.querySelector('button[type="submit"]');
        btn.disabled = true; btn.textContent = 'Añadiendo…';
        try {
            await api('/api/products', {
                method: 'POST',
                body: JSON.stringify({ url, target_price: target || null }),
            });
            toast('Producto añadido', 'ok');
            setTimeout(() => location.reload(), 400);
        } catch (err) {
            toast(err.message, 'error');
            btn.disabled = false; btn.textContent = 'Añadir';
        }
    });
}

// ---------------------------------------------------------------------------
// Delete
// ---------------------------------------------------------------------------
document.querySelectorAll('.delete-btn').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
        e.preventDefault();
        if (!confirm('¿Eliminar este producto?')) return;
        const id = btn.dataset.id;
        try {
            await api(`/api/products/${id}`, { method: 'DELETE' });
            const article = btn.closest('article');
            article.style.transition = 'opacity 180ms';
            article.style.opacity = '0';
            setTimeout(() => article.remove(), 200);
            toast('Eliminado', 'ok');
        } catch (err) {
            toast(err.message, 'error');
        }
    });
});

// ---------------------------------------------------------------------------
// Category filter
// ---------------------------------------------------------------------------
const tabs = document.getElementById('category-tabs');
if (tabs) {
    tabs.addEventListener('click', (e) => {
        const chip = e.target.closest('.cat-chip');
        if (!chip) return;
        tabs.querySelectorAll('.cat-chip').forEach((c) => c.classList.remove('active'));
        chip.classList.add('active');
        const slug = chip.dataset.slug;
        document.querySelectorAll('.product-item').forEach((item) => {
            const show = slug === 'all' || item.dataset.category === slug;
            item.style.display = show ? '' : 'none';
        });
    });
}

// ---------------------------------------------------------------------------
// Recent drops badge (poll every 60s)
// ---------------------------------------------------------------------------
const DROPS_KEY = 'tracker:lastSeenDrop';
const dropsBadge = document.getElementById('drops-badge');
const dropsCount = document.getElementById('drops-badge-count');
const dropsLabel = document.getElementById('drops-badge-label');
let dropsPanel = null;

function fmtEuro(v) {
    if (v == null) return '—';
    return new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' }).format(v);
}

function timeAgo(iso) {
    const diff = (Date.now() - new Date(iso).getTime()) / 1000;
    if (diff < 60) return 'hace unos seg.';
    if (diff < 3600) return `hace ${Math.floor(diff / 60)} min`;
    if (diff < 86400) return `hace ${Math.floor(diff / 3600)} h`;
    return `hace ${Math.floor(diff / 86400)} d`;
}

async function refreshDrops() {
    if (!dropsBadge) return;
    try {
        const drops = await api('/api/recent-drops?limit=12');
        if (!drops.length) return;
        dropsBadge.classList.remove('hidden');
        dropsBadge.classList.add('flex');

        const lastSeen = localStorage.getItem(DROPS_KEY);
        const unseen = drops.filter((d) => !lastSeen || d.created_at > lastSeen);
        if (unseen.length) {
            dropsCount.textContent = unseen.length;
            dropsCount.classList.remove('hidden');
            dropsLabel.textContent = `${unseen.length} bajada${unseen.length === 1 ? '' : 's'} nueva${unseen.length === 1 ? '' : 's'}`;
        } else {
            dropsLabel.textContent = `${drops.length} bajada${drops.length === 1 ? '' : 's'} reciente${drops.length === 1 ? '' : 's'}`;
        }
        dropsBadge._drops = drops;
    } catch (err) {
        // silent
    }
}

function renderDropsPanel(drops) {
    if (dropsPanel) { dropsPanel.remove(); dropsPanel = null; return; }
    dropsPanel = document.createElement('div');
    dropsPanel.className = 'drops-panel';
    dropsPanel.innerHTML = `<div class="drops-panel-header">Bajadas recientes</div>`;
    if (!drops.length) {
        dropsPanel.innerHTML += `<div style="padding:20px;color:#64748b;font-size:12px;text-align:center">Nada de momento.</div>`;
    } else {
        drops.forEach((d) => {
            const pct = d.percent ? `<span class="drop-pct">−${d.percent.toFixed(1)}%</span>` : '';
            const low = d.is_new_low ? `<span class="drop-low">🏆 nuevo mínimo</span>` : '';
            const img = d.image_url
                ? `<img src="${d.image_url}" alt="">`
                : `<div style="width:44px;height:44px;background:#161b2b;border-radius:8px;flex-shrink:0"></div>`;
            const el = document.createElement('a');
            el.href = `/product/${d.product_id}`;
            el.className = 'drop-item';
            el.innerHTML = `
                ${img}
                <div style="flex:1;min-width:0">
                    <div class="drop-name">${d.name}</div>
                    <div class="drop-meta">
                        ${fmtEuro(d.new_price)} ${pct}
                        <span style="color:#64748b">· ${timeAgo(d.created_at)}</span>
                        ${low}
                    </div>
                </div>`;
            dropsPanel.appendChild(el);
        });
    }
    dropsBadge.appendChild(dropsPanel);
    if (drops.length) {
        localStorage.setItem(DROPS_KEY, drops[0].created_at);
        dropsCount.classList.add('hidden');
        dropsLabel.textContent = `${drops.length} bajada${drops.length === 1 ? '' : 's'} reciente${drops.length === 1 ? '' : 's'}`;
    }
}

if (dropsBadge) {
    dropsBadge.addEventListener('click', (e) => {
        e.stopPropagation();
        renderDropsPanel(dropsBadge._drops || []);
    });
    document.addEventListener('click', (e) => {
        if (dropsPanel && !dropsBadge.contains(e.target)) {
            dropsPanel.remove();
            dropsPanel = null;
        }
    });
    refreshDrops();
    setInterval(refreshDrops, 60_000);
}

// ---------------------------------------------------------------------------
// Web Push subscription
// ---------------------------------------------------------------------------
const pushBtn = document.getElementById('enable-push');
const pushBtnLabel = document.getElementById('push-btn-label');

function urlB64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = window.atob(base64);
    return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
}

async function initPush() {
    if (!pushBtn) return;
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;

    let keyRes;
    try { keyRes = await api('/api/push/public-key'); } catch { return; }
    if (!keyRes.publicKey) return; // not configured server-side

    pushBtn.classList.remove('hidden');
    pushBtn.classList.add('inline-flex');

    const reg = await navigator.serviceWorker.register('/sw.js');
    const existing = await reg.pushManager.getSubscription();
    if (existing) {
        pushBtnLabel.textContent = 'Notificaciones activadas';
        pushBtn.title = 'Click para desactivar';
    }

    pushBtn.addEventListener('click', async () => {
        try {
            const cur = await reg.pushManager.getSubscription();
            if (cur) {
                await api('/api/push/unsubscribe', {
                    method: 'POST',
                    body: JSON.stringify({ endpoint: cur.endpoint }),
                });
                await cur.unsubscribe();
                pushBtnLabel.textContent = 'Activar notificaciones';
                toast('Notificaciones desactivadas');
                return;
            }
            const sub = await reg.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlB64ToUint8Array(keyRes.publicKey),
            });
            await api('/api/push/subscribe', {
                method: 'POST',
                body: JSON.stringify(sub.toJSON()),
            });
            pushBtnLabel.textContent = 'Notificaciones activadas';
            toast('¡Listo! Te avisaremos cuando baje un precio', 'ok');
        } catch (err) {
            console.error(err);
            toast(err.message || 'Error al activar notificaciones', 'error');
        }
    });
}
initPush();
