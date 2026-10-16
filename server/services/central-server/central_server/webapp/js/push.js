// Web push for this phone: installation proof in IndexedDB, FCM web token from the vendored Firebase
// Messaging SDK with our own service worker, then PUT installation → levels → quiet hours. Every network
// step runs in one queue, like the Android PushSyncWorker, and nothing here is ever shown on screen
// except the Korean status from logic/pushstate.js.

import { api, path } from './api.js';
import { firebaseApp, isDev, vapidKey } from './auth.js';
import * as A from './logic/alerts.js';
import { describe, routeMissing } from './logic/errors.js';
import { INSTALLATION_ID, newInstallation, validInstallation } from './logic/ids.js';
import { isIOS, isStandalone, pushView } from './logic/pushstate.js';
import { kvGet, kvSet, readJson, writeJson } from './store.js';

const RECORD = 'push';
const LEVELS_KEY = 'family-web.levels', INTERVAL_KEY = 'family-web.report-interval', QUIET_KEY = 'family-web.quiet';
const TOKEN_FAILED = '알림 연결을 만들지 못했어요. 인터넷 연결을 확인한 뒤 ‘알림 연결 확인’을 눌러 주세요.';

let record = null;
let chain = Promise.resolve();
let messagingModule = null, messaging = null, tokenThisSession = false;
const listeners = new Set();

// ---- Choices saved on this phone ----

export function levels() { return A.normalizeLevels(readJson(LEVELS_KEY, null)); }
export function reportInterval() { return A.normalizeInterval(readJson(INTERVAL_KEY, A.DEFAULT_INTERVAL)); }
export function quiet() { const value = readJson(QUIET_KEY, null); return A.validQuiet(value) ? value : A.defaultQuiet(); }

// ---- Status ----

export function environment() {
  const supported = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  let displayMode = false;
  try { displayMode = window.matchMedia('(display-mode: standalone)').matches; } catch { displayMode = false; }
  return {
    dev: isDev(), supported, standalone: isStandalone(navigator.standalone, displayMode),
    ios: isIOS(navigator.userAgent, navigator.platform, navigator.maxTouchPoints),
    permission: 'Notification' in window ? Notification.permission : 'unsupported',
  };
}
export function view() { return pushView(environment(), record || {}); }
export function enabled() { return !!(record && record.enabled); }
export function installationId() { return record && INSTALLATION_ID.test(record.installation || '') ? record.installation : null; }
export function onChange(listener) { listeners.add(listener); }

async function load() {
  if (record === null) {
    const saved = await kvGet(RECORD);
    record = saved && typeof saved === 'object' ? { ...saved } : {};
  }
  return record;
}
async function save(patch) {
  record = { ...(await load()), ...patch };
  await kvSet(RECORD, record);
  for (const listener of listeners) listener();
}
function queue(task) {
  const run = chain.then(task, task);
  chain = run.catch(() => {});
  return run;
}
export async function ready() { await load(); }

// ---- Service worker and FCM token ----

/** Registers /app/sw.js (scope /app/) and waits for it to be active. */
export async function registerWorker() {
  await navigator.serviceWorker.register('sw.js', { scope: './' });
  return navigator.serviceWorker.ready;
}
async function fcmToken() {
  const app = firebaseApp();
  if (!app) throw new Error('firebase-not-started');
  if (!messagingModule) messagingModule = await import('../vendor/firebase-messaging.js');
  if (!(await messagingModule.isSupported())) throw new Error('messaging-unsupported');
  if (!messaging) messaging = messagingModule.getMessaging(app);
  const registration = await registerWorker();
  // Without a server-provided key the SDK uses its built-in default VAPID key.
  const token = await messagingModule.getToken(messaging, { serviceWorkerRegistration: registration, vapidKey: vapidKey() });
  tokenThisSession = true;
  return token;
}
async function dropFcmToken() {
  try { if (messaging && tokenThisSession) await messagingModule.deleteToken(messaging); } catch { /* best effort */ }
  tokenThisSession = false;
  try {
    const registration = 'serviceWorker' in navigator ? await navigator.serviceWorker.getRegistration('./') : null;
    const subscription = registration ? await registration.pushManager.getSubscription() : null;
    if (subscription) await subscription.unsubscribe();
  } catch { /* best effort: the server side is already unregistered */ }
}

// ---- Server registration ----

async function putLevels() {
  await api('PUT', path('installations', record.installation, 'notification-levels'),
    { secret: record.secret, levels: levels(), report_interval_minutes: reportInterval() });
}
async function putQuiet() {
  try {
    await api('PUT', path('installations', record.installation, 'quiet-hours'), A.quietHoursBody(record.secret, quiet(), new Date()));
  } catch (failure) {
    if (!routeMissing(failure)) throw failure; // an older server without the route: keep the local choice
  }
}
async function register() {
  let token;
  try { token = await fcmToken(); } catch { throw new Error(TOKEN_FAILED); }
  if (!record.binding || token !== record.token) {
    const reply = await api('PUT', path('installations', record.installation), { secret: record.secret, token });
    if (typeof reply.binding !== 'string' || !INSTALLATION_ID.test(reply.binding)) throw new Error(TOKEN_FAILED);
    await save({ token, binding: reply.binding });
  }
  await putLevels();
  await putQuiet();
  await save({ pending: false, error: null });
}
function failureText(failure) {
  return failure && failure.message === TOKEN_FAILED ? TOKEN_FAILED : describe(failure);
}

/** After the permission prompt (from the switch's click) was granted. */
export function enable(account) {
  return queue(async () => {
    await load();
    const ids = validInstallation(record) ? { installation: record.installation, secret: record.secret }
      : newInstallation((bytes) => crypto.getRandomValues(bytes));
    const fresh = record.account !== account || ids.installation !== record.installation;
    await save({ ...ids, enabled: true, account, pending: true, error: null, ...(fresh ? { binding: null, token: null } : {}) });
    try { await register(); } catch (failure) { await save({ error: failureText(failure) }); }
  });
}
/** App start and ‘알림 연결 확인’: the FCM token may have rotated, and the UTC offset may have moved. */
export function sync(account) {
  return queue(async () => {
    await load();
    if (!record.enabled) return;
    if (record.account !== account) { await save({ enabled: false, binding: null, token: null, pending: false, error: null }); return; }
    const env = environment();
    if (env.dev || !env.standalone || !env.supported || env.permission !== 'granted') { await save({}); return; }
    try { await register(); } catch (failure) { await save({ error: failureText(failure) }); }
  });
}
async function unregister() {
  if (!record.binding || !validInstallation(record)) return;
  try {
    await api('POST', path('installations', record.installation, 'unregister'), { secret: record.secret, binding: record.binding });
  } catch { /* offline: the token is dropped below, so nothing can arrive for long */ }
}
export function disable() {
  return queue(async () => {
    await load();
    await unregister();
    await dropFcmToken();
    await save({ enabled: false, binding: null, token: null, pending: false, error: null });
  });
}
/** Before signing out: unregister on the server while the ID token still works, then forget the account. */
export function signOutCleanup() {
  return queue(async () => {
    await load();
    if (record.enabled || record.binding) {
      await unregister();
      await dropFcmToken();
    }
    await save({ enabled: false, binding: null, token: null, pending: false, error: null, account: null });
  });
}

// ---- Choices: saved at once on this phone, then sent when this phone is registered ----

function resend(send) {
  return queue(async () => {
    await load();
    if (!record.enabled || !record.binding) return;
    await save({ pending: true, error: null });
    try { await send(); await save({ pending: false }); } catch (failure) { await save({ error: failureText(failure) }); }
  });
}
export function setLevel(category, level) {
  if (!A.valid(category, level)) return Promise.resolve();
  writeJson(LEVELS_KEY, { ...levels(), [category]: level });
  return resend(putLevels);
}
export function setReportInterval(minutes) {
  if (!A.validInterval(minutes)) return Promise.resolve();
  writeJson(INTERVAL_KEY, minutes);
  return resend(putLevels);
}
export function setQuiet(value) {
  if (!A.validQuiet(value)) return Promise.resolve();
  writeJson(QUIET_KEY, { enabled: value.enabled, start: value.start, end: value.end });
  return resend(putQuiet);
}
