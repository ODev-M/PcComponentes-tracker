// Product detail page: price history chart + force-check button.

const EURO = (v) =>
    v == null ? '—' : new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' }).format(v);

async function loadHistory() {
    const status = document.getElementById('history-status');
    try {
        const res = await fetch(`/api/products/${window.PRODUCT_ID}/history`);
        const body = await res.json();
        if (!res.ok) throw new Error(body.error || 'Error cargando historial');

        if (body.lowest != null) {
            document.getElementById('min-price').textContent = EURO(body.lowest);
        }

        const points = body.points.filter((p) => p.price > 0);
        if (points.length === 0) {
            status.textContent = 'Sin datos todavía';
            return;
        }

        status.textContent = `${points.length} muestras`;

        const ctx = document.getElementById('history-chart');
        const gradient = ctx.getContext('2d').createLinearGradient(0, 0, 0, 280);
        gradient.addColorStop(0, 'rgba(124, 155, 255, 0.35)');
        gradient.addColorStop(1, 'rgba(124, 155, 255, 0)');

        new Chart(ctx, {
            type: 'line',
            data: {
                datasets: [
                    {
                        label: 'Precio',
                        data: points.map((p) => ({ x: p.t, y: p.price })),
                        borderColor: '#7c9bff',
                        backgroundColor: gradient,
                        borderWidth: 2.5,
                        fill: true,
                        tension: 0.45,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        pointHoverBorderWidth: 2,
                        pointHoverBorderColor: '#fff',
                        pointHoverBackgroundColor: '#7c9bff',
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(10, 13, 20, 0.95)',
                        borderColor: 'rgba(255,255,255,0.08)',
                        borderWidth: 1,
                        padding: 10,
                        titleColor: '#cbd5e1',
                        bodyColor: '#e2e8f0',
                        displayColors: false,
                        callbacks: {
                            label: (ctx) => EURO(ctx.parsed.y),
                        },
                    },
                },
                scales: {
                    x: {
                        type: 'time',
                        time: { tooltipFormat: 'dd MMM yyyy HH:mm' },
                        grid: { color: 'rgba(255,255,255,0.04)', drawBorder: false },
                        ticks: { color: '#64748b', font: { size: 10 }, maxRotation: 0 },
                    },
                    y: {
                        grid: { color: 'rgba(255,255,255,0.05)', drawBorder: false },
                        ticks: {
                            color: '#64748b',
                            font: { size: 10 },
                            callback: (v) => `${v} €`,
                        },
                    },
                },
            },
        });
    } catch (err) {
        status.textContent = err.message;
    }
}

loadHistory();

const checkBtn = document.getElementById('check-now');
if (checkBtn) {
    checkBtn.addEventListener('click', async () => {
        checkBtn.disabled = true;
        const original = checkBtn.textContent;
        checkBtn.textContent = 'Comprobando…';
        try {
            const res = await fetch(`/api/products/${window.PRODUCT_ID}/check`, { method: 'POST' });
            const body = await res.json();
            if (!res.ok) throw new Error(body.error || 'Error');
            document.getElementById('current-price').textContent = EURO(body.last_price);
            checkBtn.textContent = '✓ Actualizado';
            setTimeout(() => {
                checkBtn.textContent = original;
                checkBtn.disabled = false;
                location.reload();
            }, 900);
        } catch (err) {
            checkBtn.textContent = original;
            checkBtn.disabled = false;
            alert(err.message);
        }
    });
}
