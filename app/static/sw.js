// Service Worker — receives Web Push and surfaces OS notifications.

self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener('push', (event) => {
    let payload = {};
    try {
        payload = event.data ? event.data.json() : {};
    } catch (e) {
        payload = { title: 'Tracker', body: event.data && event.data.text() || '' };
    }

    const title = payload.title || 'Bajada de precio';
    const options = {
        body: payload.body || '',
        icon: payload.icon || '/static/icon-192.png',
        badge: '/static/badge-72.png',
        tag: payload.tag || 'tracker-notification',
        renotify: true,
        data: { url: payload.url || '/' },
        vibrate: payload.is_new_low ? [200, 100, 200] : [120],
    };

    event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const url = (event.notification.data && event.notification.data.url) || '/';
    event.waitUntil((async () => {
        const clientsList = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
        for (const c of clientsList) {
            if (c.url.endsWith(url) && 'focus' in c) return c.focus();
        }
        if (self.clients.openWindow) return self.clients.openWindow(url);
    })());
});
