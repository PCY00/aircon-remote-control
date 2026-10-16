/* Family web app service worker (scope /app/). Classic script, no Firebase SDK in here.
 * - push: always shows one notification (iOS requires it) with the generic per-category text;
 *   names and values never travel in a push.
 * - fetch: the app shell comes from a versioned cache; /v1/, /__/, config.json and anything with
 *   an Authorization header always go to the network and are never stored. */
'use strict';

const VERSION = '0.8.0-1';
const CACHE = 'family-web-' + VERSION;
const SCOPE = new URL('./', self.location.href).pathname; // "/app/"
const SHELL = [
  './',
  'index.html',
  'app.css',
  'manifest.webmanifest',
  'apple-touch-icon.png',
  'icon-192.png',
  'icon-512.png',
  'icon-maskable-512.png',
  'js/api.js',
  'js/app.js',
  'js/auth.js',
  'js/context.js',
  'js/dial.js',
  'js/icons.js',
  'js/push.js',
  'js/store.js',
  'js/ui.js',
  'js/logic/aircon.js',
  'js/logic/alerts.js',
  'js/logic/attention.js',
  'js/logic/dev.js',
  'js/logic/device.js',
  'js/logic/errors.js',
  'js/logic/homes.js',
  'js/logic/ids.js',
  'js/logic/plain.js',
  'js/logic/pushstate.js',
  'js/logic/timeline.js',
  'js/views/alerts.js',
  'js/views/device.js',
  'js/views/home.js',
  'js/views/settings.js',
  'js/views/start.js',
  'vendor/firebase-app.js',
  'vendor/firebase-auth.js',
  'vendor/firebase-messaging.js',
];

// ---- Notification texts (same as js/logic/alerts.js and the Android AlertLevels) ----

const TITLE = '우리 집 알림';
const CATEGORIES = ['safety', 'security', 'device', 'environment', 'report', 'automation', 'family', 'other'];
const BODIES = {
  safety: '안전 알림이 왔어요. 앱에서 바로 확인해 주세요.',
  security: '문이나 움직임에 변화가 있어요. 앱에서 확인해 주세요.',
  device: '기기 상태를 확인해 주세요.',
  environment: '온습도가 기준을 넘었어요. 앱에서 확인해 주세요.',
  report: '새 온습도 측정값이 도착했어요.',
  automation: '자동화 소식이 있어요. 앱에서 확인해 주세요.',
  family: '가족이 기기를 조작했어요.',
  other: '새 기록이 도착했어요. 앱에서 확인해 주세요.',
};
const TEST_BODY = '시험 알림이 도착했어요.';
const LEGACY = { door: 'security', climate: 'report', warning: 'automation' };

function categoryOf(data) {
  const alert = typeof data.alert_category === 'string' ? data.alert_category : '';
  if (alert) return CATEGORIES.includes(alert) ? alert : 'other';
  return LEGACY[data.category] || 'other';
}
/** FCM web payload: {data: {...}, from, fcmMessageId, ...}; anything unreadable still shows a notification. */
function notificationFor(event) {
  let payload = null;
  try { payload = event.data ? event.data.json() : null; } catch (error) { payload = null; }
  const data = payload && typeof payload === 'object' && payload.data && typeof payload.data === 'object' ? payload.data : {};
  const test = data.kind === 'test';
  const category = test ? 'other' : categoryOf(data);
  return {
    title: TITLE,
    options: {
      body: test ? TEST_BODY : BODIES[category],
      tag: 'family-' + category,
      renotify: true,
      lang: 'ko',
      icon: SCOPE + 'icon-192.png',
      badge: SCOPE + 'icon-192.png',
      data: { url: SCOPE + '#alerts' },
    },
  };
}

self.addEventListener('push', (event) => {
  const { title, options } = notificationFor(event);
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const wanted = event.notification.data && typeof event.notification.data.url === 'string' ? event.notification.data.url : SCOPE + '#alerts';
  const target = new URL(wanted, self.location.origin);
  const url = target.origin === self.location.origin && target.pathname.startsWith(SCOPE) ? target.href : new URL(SCOPE + '#alerts', self.location.origin).href;
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of windows) {
      if (new URL(client.url).pathname.startsWith(SCOPE)) {
        client.postMessage({ type: 'open', route: 'alerts' });
        if ('focus' in client) await client.focus();
        return;
      }
    }
    if (self.clients.openWindow) await self.clients.openWindow(url);
  })());
});

// ---- App shell ----

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    await cache.addAll(SHELL.map((path) => new Request(new URL(path, self.registration.scope), { cache: 'reload', credentials: 'omit' })));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const name of await caches.keys()) if (name.startsWith('family-web-') && name !== CACHE) await caches.delete(name);
    await self.clients.claim();
  })());
});

function cacheable(request) {
  if (request.method !== 'GET' || request.headers.has('Authorization')) return false;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || !url.pathname.startsWith(SCOPE)) return false;
  return url.pathname !== SCOPE + 'config.json' && url.pathname !== SCOPE + 'sw.js';
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (!cacheable(request)) return; // network as usual: API, auth proxy, config, other hosts
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const navigation = request.mode === 'navigate';
    const hit = await cache.match(navigation ? new URL(SCOPE, self.location.origin).href : request, { ignoreSearch: navigation });
    return hit || fetch(request);
  })());
});
