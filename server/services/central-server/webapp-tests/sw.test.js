// Runs webapp/sw.js in a sandbox with a fake service-worker global and checks push, click and fetch.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import * as A from '../central_server/webapp/js/logic/alerts.js';

const SOURCE = readFileSync(new URL('../central_server/webapp/sw.js', import.meta.url), 'utf8');
const ORIGIN = 'https://roomrelay.top';

function worker({ windows = [] } = {}) {
  const listeners = {}, shown = [], opened = [], cacheStore = new Map();
  const self = {
    location: new URL(ORIGIN + '/app/sw.js'),
    registration: {
      scope: ORIGIN + '/app/',
      showNotification: (title, options) => { shown.push({ title, options }); return Promise.resolve(); },
    },
    clients: {
      matchAll: async () => windows,
      openWindow: async (url) => { opened.push(url); },
      claim: async () => {},
    },
    skipWaiting: async () => {},
    addEventListener: (type, handler) => { listeners[type] = handler; },
  };
  const caches = {
    open: async () => ({
      addAll: async (requests) => { for (const request of requests) cacheStore.set(request.url, 'cached'); },
      match: async (request) => cacheStore.get(typeof request === 'string' ? request : request.url) || undefined,
    }),
    keys: async () => [],
    delete: async () => true,
  };
  const context = vm.createContext({ self, caches, URL, Request, Response, Headers, fetch: async () => 'network', console });
  vm.runInContext(SOURCE, context, { filename: 'sw.js' });
  return { listeners, shown, opened, cacheStore };
}
async function push(sw, payload, { raw = false } = {}) {
  const waits = [];
  sw.listeners.push({
    data: payload === undefined ? null : { json: () => (raw ? JSON.parse(payload) : payload) },
    waitUntil: (promise) => waits.push(promise),
  });
  await Promise.all(waits);
  assert.equal(waits.length, 1, 'every push waits for its notification');
  return sw.shown.at(-1);
}
const fcm = (data) => ({ data, from: '1234', priority: 'high', fcmMessageId: 'x' });

test('every push shows exactly one generic notification per category', async () => {
  const sw = worker();
  for (const category of A.FILTERS) {
    const shown = await push(sw, fcm({ message_id: 'm', kind: 'event', category: 'other', alert_category: category, level: 'alert', binding: 'b', recipient: 'u' }));
    assert.equal(shown.title, A.NOTIFICATION_TITLE);
    assert.equal(shown.options.body, A.body(category, false), category);
    assert.equal(shown.options.tag, A.tag(category));
    assert.equal(shown.options.data.url, '/app/#alerts');
  }
  assert.equal(sw.shown.length, A.FILTERS.length);
});

test('test pushes, legacy categories, unknown categories and broken payloads still show', async () => {
  const sw = worker();
  assert.equal((await push(sw, fcm({ kind: 'test', alert_category: 'other' }))).options.body, '시험 알림이 도착했어요.');
  assert.equal((await push(sw, fcm({ kind: 'event', category: 'door' }))).options.body, A.body('security', false), 'older server');
  assert.equal((await push(sw, fcm({ kind: 'event', alert_category: 'weather', category: 'door' }))).options.tag, 'family-other');
  assert.equal((await push(sw, '{not json', { raw: true })).options.body, A.body('other', false));
  assert.equal((await push(sw, undefined)).options.body, A.body('other', false), 'a push without data');
  assert.equal((await push(sw, { notification: { title: '이름이 든 제목' } })).title, '우리 집 알림', 'never shows text from the payload');
});

test('a notification click focuses an open app window, or opens the alerts tab', async () => {
  const messages = [], focused = [];
  const client = { url: ORIGIN + '/app/#home', postMessage: (message) => messages.push(message), focus: async () => focused.push(true) };
  const sw = worker({ windows: [client] });
  const waits = [];
  const notification = { data: { url: '/app/#alerts' }, close: () => {} };
  sw.listeners.notificationclick({ notification, waitUntil: (promise) => waits.push(promise) });
  await Promise.all(waits);
  assert.equal(JSON.stringify(messages), JSON.stringify([{ type: 'open', route: 'alerts' }]), 'objects come from the sandbox realm'); assert.equal(focused.length, 1);

  const empty = worker();
  const later = [];
  empty.listeners.notificationclick({ notification: { data: { url: 'https://evil.example/' }, close: () => {} }, waitUntil: (promise) => later.push(promise) });
  await Promise.all(later);
  assert.deepEqual(empty.opened, [ORIGIN + '/app/#alerts'], 'only the app itself can be opened');
});

test('the API, the auth proxy, config.json and authorized requests are never served from the cache', async () => {
  const sw = worker();
  const handled = (url, init) => {
    let used = false;
    sw.listeners.fetch({ request: new Request(url, init), respondWith: () => { used = true; } });
    return used;
  };
  assert.equal(handled(ORIGIN + '/v1/homes'), false);
  assert.equal(handled(ORIGIN + '/__/auth/handler'), false);
  assert.equal(handled(ORIGIN + '/app/config.json'), false);
  assert.equal(handled(ORIGIN + '/app/sw.js'), false);
  assert.equal(handled(ORIGIN + '/app/app.css', { headers: { Authorization: 'Bearer x' } }), false);
  assert.equal(handled(ORIGIN + '/app/app.css', { method: 'POST', body: 'x' }), false);
  assert.equal(handled('https://www.gstatic.com/firebasejs/x.js'), false);
  assert.equal(handled(ORIGIN + '/app/app.css'), true);
  assert.equal(handled(ORIGIN + '/app/js/app.js'), true);
});

test('install precaches the whole shell under /app/', async () => {
  const sw = worker();
  const waits = [];
  sw.listeners.install({ waitUntil: (promise) => waits.push(promise) });
  await Promise.all(waits);
  assert.ok(sw.cacheStore.has(ORIGIN + '/app/'));
  assert.ok(sw.cacheStore.has(ORIGIN + '/app/vendor/firebase-messaging.js'));
  for (const url of sw.cacheStore.keys()) assert.ok(url.startsWith(ORIGIN + '/app/'), url);
});
