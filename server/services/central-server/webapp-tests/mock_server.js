// Local screenshot server for the family web app: serves central_server/webapp/ at /app/ with the
// production CSP and answers the /v1/ routes the app reads from made-up data (no real home, no
// account, nothing stored). Loopback only.
//
//   node mock_server.js [port]          → prints a http://127.0.0.1:<port>/app/#dev-token=… address
//   node mock_server.js [port] --config → /app/config.json answers made-up Firebase values, so the
//                                         sign-in screen can be seen (signing in itself cannot work)
//
// The token is generated here at start: the app accepts it only on 127.0.0.1/localhost, and this
// server accepts any bearer token. Its subject picks the role: owner (default), member or viewer.

import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';

const WEBAPP = fileURLToPath(new URL('../central_server/webapp/', import.meta.url));
const PORT = Number(process.argv[2] || 8780);
const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.webmanifest': 'application/manifest+json', '.json': 'application/json',
  '.png': 'image/png', '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.txt': 'text/plain; charset=utf-8',
};
// Same policy as central_server/web_app.py APP_CSP.
const CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https://lh3.googleusercontent.com; "
  + "connect-src 'self' https://identitytoolkit.googleapis.com https://securetoken.googleapis.com https://firebaseinstallations.googleapis.com "
  + "https://fcmregistrations.googleapis.com https://www.googleapis.com; frame-src 'self'; worker-src 'self'; manifest-src 'self'; "
  + "frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'";

const now = () => Date.now() / 1000;
const START = now();
const AIRCON = 'a1c0a1c0a1c0a1c0a1c0a1c0a1c0a1c0', LIVING = 'c11a7e00c11a7e00c11a7e00c11a7e00',
  DOOR = 'd0042d0042d0042d0042d0042d0042d0', BEDROOM = 'bed500bed500bed500bed500bed500be';
const HOMES = [
  { id: 'home-test', name: '시험용 우리 집' },
  { id: 'home-parents', name: '부모님 댁' },
];
const devices = () => [
  { id: AIRCON, name: '거실 에어컨', room: '거실', type: 'air_conditioner', capabilities: ['power', 'setpoint', 'mode', 'fan', 'actions'],
    state: { power: true, mode: 'cool', setpoint_c: 24, fan: 'auto', inferred: true }, reported_at: START - 480, controllable: true },
  { id: LIVING, name: '거실 온습도', room: '거실', type: 'climate_sensor', capabilities: ['temperature', 'humidity', 'battery'],
    state: { temperature_c: 26.2, humidity_percent: 27, battery_percent: 76 }, reported_at: now() - 120, controllable: false },
  { id: DOOR, name: '현관문', room: '현관', type: 'door_sensor', capabilities: ['contact', 'battery'],
    state: { contact: 'closed', battery_percent: 87 }, reported_at: START - 1380, controllable: false },
  { id: BEDROOM, name: '안방 온습도', room: '안방', type: 'climate_sensor', capabilities: ['temperature', 'humidity', 'battery'],
    state: { temperature_c: 25.1, humidity_percent: 48, battery_percent: 15 }, reported_at: now() - 300, controllable: false },
];
let eventId = 100;
const event = (kind, ago, payload) => ({ id: eventId++, hub_id: 'hub-test', kind, payload, received_at: START - ago });
const EVENTS = [
  event('sensor.climate_report', 300, { temperature_c: 25.1, humidity_percent: 48, device_id: BEDROOM }),
  event('sensor.door_changed', 540, { state: 'closed', device_id: DOOR }),
  event('sensor.door_changed', 600, { state: 'open', device_id: DOOR }),
  event('sensor.climate_report', 900, { temperature_c: 26.4, humidity_percent: 28, device_id: LIVING }),
  event('hub.connection_test', 3600 * 5, {}),
  event('automation.warning_resolved', 86400 + 3600, {}),
  event('automation.warning_triggered', 86400 + 5400, {}),
  event('sensor.door_changed', 86400 * 2, { state: 'closed', device_id: DOOR }),
].sort((a, b) => b.received_at - a.received_at);
let latest = { id: randomUUID(), device_id: AIRCON, action: 'cool_24_auto', state: 'sent', created_at: START - 482, expires_at: START - 452, updated_at: START - 480 };

function role(request) {
  try {
    const token = (request.headers.authorization || '').split(' ')[1] || '';
    const subject = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString()).sub;
    return ['member', 'viewer'].includes(subject) ? subject : 'owner';
  } catch { return 'owner'; }
}
function send(response, status, body, headers = {}) {
  response.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', ...headers });
  response.end(JSON.stringify(body));
}
async function readBody(request) {
  let raw = '';
  for await (const chunk of request) raw += chunk;
  try { return JSON.parse(raw || '{}'); } catch { return null; }
}

async function api(request, response, url) {
  if (!/^Bearer \S+$/.test(request.headers.authorization || '')) return send(response, 401, { error: 'invalid_credentials' });
  const parts = url.pathname.split('/').slice(2).map(decodeURIComponent);
  const homeRole = (id) => (id === 'home-parents' ? 'viewer' : role(request));
  const method = request.method;
  if (method === 'GET' && parts.join('/') === 'homes') return send(response, 200, { homes: HOMES.map((home) => ({ ...home, role: homeRole(home.id) })) });
  if (method === 'POST' && parts.join('/') === 'homes') {
    const body = await readBody(request);
    if (!body || typeof body.name !== 'string' || !body.name.trim()) return send(response, 400, { error: 'invalid_body' });
    const home = { id: 'home-' + randomUUID().slice(0, 8), name: body.name.trim() };
    HOMES.push(home);
    return send(response, 201, { ...home, role: 'owner' });
  }
  if (method === 'POST' && parts.join('/') === 'invitations/accept') return send(response, 404, { error: 'invalid_invitation' });
  if (parts[0] === 'installations') return send(response, 200, { status: 'saved', binding: randomUUID() });
  if (parts[0] !== 'homes' || !HOMES.some((home) => home.id === parts[1])) return send(response, 404, { error: 'not_found' });
  const home = HOMES.find((item) => item.id === parts[1]);
  const test = home.id === 'home-test';
  const rest = parts.slice(2).join('/');
  if (method === 'GET' && rest === '') return send(response, 200, { ...home, role: homeRole(home.id) });
  if (method === 'GET' && rest === 'devices') {
    return send(response, 200, test ? { devices: devices(), updated_at: now() - 40, hub_online: true } : { devices: [], updated_at: null, hub_online: false });
  }
  if (method === 'GET' && rest === 'events') return send(response, 200, { events: test ? EVENTS : [] });
  if (method === 'GET' && rest === 'control') {
    const canControl = ['owner', 'member'].includes(homeRole(home.id));
    return send(response, 200, test
      ? { online: true, can_control: canControl, actions: [], devices: [{ id: AIRCON, name: '거실 에어컨' }], latest_command: latest }
      : { online: false, can_control: false, actions: [], devices: [], latest_command: null });
  }
  if (method === 'POST' && rest === 'control/commands') {
    const body = await readBody(request);
    if (!test || !body || typeof body.action !== 'string' || body.device_id !== AIRCON) return send(response, 400, { error: 'invalid_body' });
    if (homeRole(home.id) === 'viewer') return send(response, 403, { error: 'control_forbidden' });
    const at = now();
    latest = { id: body.request_id, device_id: AIRCON, action: body.action, state: 'queued', created_at: at, expires_at: at + 30, updated_at: at };
    return send(response, 202, latest);
  }
  if (method === 'GET' && parts[2] === 'control' && parts[3] === 'commands' && latest && parts[4] === latest.id) {
    // queued → dispatched → sent over about four seconds.
    const age = now() - latest.created_at;
    const next = age > 4 ? 'sent' : age > 2 ? 'dispatched' : 'queued';
    if (next !== latest.state) latest = { ...latest, state: next, updated_at: now() };
    return send(response, 200, latest);
  }
  if (method === 'POST' && rest === 'notifications/test') return send(response, 202, { status: 'queued', queued: 1, message_id: randomUUID() });
  return send(response, 404, { error: 'not_found' });
}

async function file(response, url) {
  if (url.pathname === '/app') { response.writeHead(308, { Location: '/app/' }); response.end(); return; }
  if (url.pathname === '/app/config.json') {
    if (!process.argv.includes('--config')) return send(response, 503, { error: 'web_not_configured' }, { 'Content-Security-Policy': CSP });
    return send(response, 200, {
      firebase: { apiKey: 'mock-web-api-key', authDomain: '127.0.0.1', projectId: 'mock-project', appId: '1:000:web:mock', messagingSenderId: '000' },
      server_version: 'mock',
    }, { 'Content-Security-Policy': CSP });
  }
  const name = url.pathname === '/app/' ? 'index.html' : decodeURIComponent(url.pathname.slice('/app/'.length));
  const target = normalize(join(WEBAPP, name));
  if (!target.startsWith(WEBAPP.endsWith(sep) ? WEBAPP : WEBAPP + sep) || !TYPES[extname(target)]) return send(response, 404, { error: 'not_found' });
  try {
    const data = await readFile(target);
    response.writeHead(200, { 'Content-Type': TYPES[extname(target)], 'Cache-Control': 'no-cache', 'Content-Security-Policy': CSP, 'Referrer-Policy': 'same-origin' });
    response.end(data);
  } catch {
    send(response, 404, { error: 'not_found' });
  }
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url, 'http://127.0.0.1');
  try {
    if (url.pathname.startsWith('/v1/')) await api(request, response, url);
    else if (url.pathname === '/app' || url.pathname.startsWith('/app/')) await file(response, url);
    else { response.writeHead(302, { Location: '/app/' }); response.end(); }
  } catch {
    send(response, 500, { error: 'mock_failed' });
  }
});
server.listen(PORT, '127.0.0.1', () => {
  const part = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');
  const token = (subject) => [part({ alg: 'none', typ: 'JWT' }), part({ sub: subject }), part('mock')].join('.');
  for (const subject of ['owner', 'viewer']) console.log(`${subject}: http://127.0.0.1:${PORT}/app/#dev-token=${token(subject)}`);
});
