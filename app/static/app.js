// Homepage interactions: add form + delete buttons + toasts.

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
    }, 2600);
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

document.querySelectorAll('.delete-btn').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
        e.preventDefault();
        if (!confirm('¿Eliminar este producto?')) return;
        const id = btn.dataset.id;
        try {
            await api(`/api/products/${id}`, { method: 'DELETE' });
            btn.closest('article').style.transition = 'opacity 180ms';
            btn.closest('article').style.opacity = '0';
            setTimeout(() => btn.closest('article').remove(), 200);
            toast('Eliminado', 'ok');
        } catch (err) {
            toast(err.message, 'error');
        }
    });
});
