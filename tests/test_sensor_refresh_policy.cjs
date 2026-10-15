const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const test = require('node:test');
const vm = require('node:vm');

const sensorSource = readFileSync(path.join(__dirname, '../app/static/sensors.js'), 'utf8');
const automationSource = readFileSync(path.join(__dirname, '../app/static/automations.js'), 'utf8');

// Run the shipped functions, not a second implementation of their policy.
function extractFunction(source, name) {
  const start = source.search(new RegExp(`^  (?:async )?function ${name}\\(`, 'm'));
  assert.notEqual(start, -1, `Missing application function: ${name}`);
  const tail = source.slice(start);
  const end = tail.search(/^  }$/m);
  assert.notEqual(end, -1, `Missing function boundary after ${name}`);
  return tail.slice(0, end + 3);
}

const policySource = ['minutesOfDay', 'isPauseTime', 'climateRefreshAllowed']
  .map((name) => extractFunction(sensorSource, name)).join('\n');

function policyContext(overrides = {}, lastRefresh = null) {
  const context = vm.createContext({
    DISPLAY_TIME_ZONE: 'Asia/Seoul',
    settings: {
      enabled: true,
      pauseStart: '07:00',
      pauseEnd: '19:00',
      intervalMinutes: 5,
      ...overrides
    },
    lastClimateRefreshAt: lastRefresh
  });
  vm.runInContext(policySource, context);
  return context;
}

function kst(time) {
  return new Date(`2026-09-08T${time}+09:00`);
}

test('default pause begins at exactly 07:00 KST', () => {
  const context = policyContext();
  assert.equal(context.isPauseTime(kst('06:59:59')), false);
  assert.equal(context.isPauseTime(kst('07:00:00')), true);
  assert.equal(context.climateRefreshAllowed(true, kst('07:00:00')), false);
});

test('default pause ends at exactly 19:00 KST', () => {
  const context = policyContext();
  assert.equal(context.isPauseTime(kst('18:59:59')), true);
  assert.equal(context.isPauseTime(kst('19:00:00')), false);
  assert.equal(context.climateRefreshAllowed(true, kst('19:00:00')), true);
});

test('disabled automatic refresh cannot refresh even outside pause hours', () => {
  const context = policyContext({ enabled: false });
  assert.equal(context.climateRefreshAllowed(true, kst('20:00:00')), false);
  assert.equal(context.climateRefreshAllowed(true, kst('12:00:00')), false);
});

test('five minute interval allows first refresh and rejects early repeats', () => {
  const context = policyContext();
  assert.equal(context.climateRefreshAllowed(true, kst('20:00:00')), true);
  context.lastClimateRefreshAt = kst('20:00:00').getTime();
  assert.equal(context.climateRefreshAllowed(true, kst('20:00:00')), false);
  assert.equal(context.climateRefreshAllowed(true, kst('20:04:59')), false);
  assert.equal(context.climateRefreshAllowed(true, kst('20:05:00')), true);
});

test('manual refresh bypasses disabled state, pause hours, and interval', () => {
  const context = policyContext({ enabled: false }, kst('12:00:00').getTime());
  assert.equal(context.climateRefreshAllowed(false, kst('12:00:00')), true);
  context.settings.enabled = true;
  assert.equal(context.climateRefreshAllowed(false, kst('12:00:00')), true);
  context.lastClimateRefreshAt = kst('20:00:00').getTime();
  assert.equal(context.climateRefreshAllowed(false, kst('20:00:01')), true);
});

test('pause intervals crossing midnight include both sides of midnight', () => {
  const context = policyContext({ pauseStart: '22:00', pauseEnd: '06:00' });
  for (const time of ['22:00:00', '23:59:59', '00:00:00', '05:59:59']) {
    assert.equal(context.isPauseTime(kst(time)), true, time);
  }
  for (const time of ['06:00:00', '12:00:00', '21:59:59']) {
    assert.equal(context.isPauseTime(kst(time)), false, time);
  }
});

test('equal pause boundaries fail closed for automatic refresh', () => {
  const context = policyContext({ pauseStart: '07:00', pauseEnd: '07:00' });
  assert.equal(context.climateRefreshAllowed(true, kst('01:00:00')), false);
  assert.equal(context.climateRefreshAllowed(true, kst('12:00:00')), false);
  assert.equal(context.climateRefreshAllowed(false, kst('12:00:00')), true);
});

test('browser default timezone cannot change KST pause boundaries', () => {
  const childSource = `
    const vm = require('node:vm');
    const context = vm.createContext({
      DISPLAY_TIME_ZONE: 'Asia/Seoul',
      settings: { enabled: true, pauseStart: '07:00', pauseEnd: '19:00', intervalMinutes: 5 },
      lastClimateRefreshAt: null
    });
    vm.runInContext(${JSON.stringify(policySource)}, context);
    console.log(JSON.stringify({
      localHour: new Date('2026-09-08T07:00:00+09:00').getHours(),
      before: context.isPauseTime(new Date('2026-09-08T06:59:59+09:00')),
      start: context.isPauseTime(new Date('2026-09-08T07:00:00+09:00')),
      end: context.isPauseTime(new Date('2026-09-08T19:00:00+09:00'))
    }));
  `;
  const localHours = new Set();
  for (const timezone of ['UTC', 'America/Los_Angeles', 'Asia/Seoul']) {
    const child = spawnSync(process.execPath, ['-e', childSource], {
      env: { ...process.env, TZ: timezone }, encoding: 'utf8'
    });
    assert.equal(child.status, 0, child.stderr);
    const result = JSON.parse(child.stdout);
    localHours.add(result.localHour);
    assert.equal(result.before, false, timezone);
    assert.equal(result.start, true, timezone);
    assert.equal(result.end, false, timezone);
  }
  assert.equal(localHours.size, 3, 'The checks must actually use different local timezones');
});

test('live climate events do not change displayed state or trigger rendering', async () => {
  const original = { device_id: 'climate-test', kind: 'temperature_humidity', state: { temperature_c: 22 } };
  const context = vm.createContext({ sensors: [original] });
  vm.runInContext(extractFunction(sensorSource, 'applyLiveSensorUpdate'), context);
  // No DOM/API stubs: falling through the climate guard would throw here.
  await context.applyLiveSensorUpdate({ ...original, state: { temperature_c: 30 } });
  assert.equal(context.sensors.length, 1);
  assert.equal(context.sensors[0], original);
});

test('door SSE still updates state, history, and the currently open detail', async () => {
  const calls = [];
  const received = { device_id: 'door-test', kind: 'door_contact', event_recorded: true,
    last_received_at: '2026-09-08T10:00:00Z', state: { door_state: 'open' } };
  const history = [{ state: 'open', previous_state: 'closed' }];
  const lastRefresh = { textContent: '' };
  const context = vm.createContext({
    sensors: [], currentSensorId: 'door-test', eventHistory: new Map(),
    historyRequests: new Map(), historyErrors: new Map(),
    managerDialog: { open: false },
    apiCall: async (url) => { calls.push(url); return { items: history }; },
    updateBridgeView: () => calls.push('bridge'),
    renderOverview: () => calls.push('overview'),
    syncDeviceTiles: () => calls.push('tiles'),
    renderSensorDetail: () => calls.push('detail'),
    root: { querySelector: () => lastRefresh },
    formatTime: () => '19:00'
  });
  vm.runInContext(['mergeSensorSnapshot', 'refreshDoorHistory', 'applyLiveSensorUpdate']
    .map((name) => extractFunction(sensorSource, name)).join('\n'), context);
  await context.applyLiveSensorUpdate(received);
  assert.equal(context.sensors[0], received);
  assert.equal(context.eventHistory.get('door-test'), history);
  assert.deepEqual(calls, ['/api/v1/sensors/door-test/events?limit=20', 'bridge', 'overview', 'tiles', 'detail']);
  assert.equal(lastRefresh.textContent, '19:00 실시간');
});

test('automatic REST refresh consults climate policy even on forced reconnect', () => {
  const refreshSource = extractFunction(sensorSource, 'refreshSensors');
  assert.match(refreshSource, /climateRefreshAllowed\(automatic/);
  assert.doesNotMatch(refreshSource, /climateRefreshAllowed\(automatic\s*&&\s*!force/);
});

test('automation listener restores server state on stream.ready reconnect', () => {
  assert.match(automationSource, /type\s*===\s*['"]stream\.ready['"]\s*\|\|\s*type\.startsWith\(['"]automation\.['"]\)/);
});

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function sensorRuntime(apiCall) {
  const context = vm.createContext({
    sensors: [], currentSensorId: '', eventHistory: new Map(),
    historyRequests: new Map(), historyErrors: new Map(),
    refreshInFlight: false, bridgeStatus: null, lastClimateRefreshAt: null,
    managerDialog: { open: false }, announcer: { textContent: '' }, apiCall,
    setLoading() {}, isPauseTime: () => false, climateRefreshAllowed: () => true,
    updateBridgeView() {}, renderOverview() {}, syncDeviceTiles() {}, renderSensorDetail() {},
    updatePolicyText() {}, root: { querySelector: () => ({ textContent: '' }) }, formatTime: String
  });
  vm.runInContext(['mergeSensorSnapshot', 'refreshDoorHistory', 'refreshSensors', 'applyLiveSensorUpdate']
    .map((name) => extractFunction(sensorSource, name)).join('\n'), context);
  return context;
}

test('a delayed REST snapshot cannot overwrite a newer live door update or remove a new sensor', async () => {
  const snapshot = deferred();
  const context = sensorRuntime(async (url) => {
    if (url === '/api/v1/sensors') return snapshot.promise;
    return { items: [] };
  });
  const stale = { device_id: 'door-test', kind: 'door_contact', last_received_at: '2026-09-08T10:00:00Z', state: { door_state: 'closed' } };
  context.sensors = [stale];
  const refresh = context.refreshSensors();
  const live = { ...stale, last_received_at: '2026-09-08T10:01:00Z', state: { door_state: 'open' } };
  await context.applyLiveSensorUpdate(live);
  await context.applyLiveSensorUpdate({ ...live, device_id: 'new-door' });
  snapshot.resolve({ items: [stale] });
  await refresh;
  assert.equal(context.sensors.find((item) => item.device_id === 'door-test').state.door_state, 'open');
  assert.equal(context.sensors.length, 2);
});

test('out-of-order history responses cannot replace more recent history', async () => {
  const first = deferred();
  const second = deferred();
  let requests = 0;
  const context = sensorRuntime(() => (++requests === 1 ? first.promise : second.promise));
  const oldRequest = context.refreshDoorHistory('door-test');
  const newRequest = context.refreshDoorHistory('door-test');
  const latest = [{ state: 'closed' }, { state: 'open' }];
  second.resolve({ items: latest });
  await newRequest;
  first.resolve({ items: [{ state: 'open' }] });
  await oldRequest;
  assert.equal(context.eventHistory.get('door-test'), latest);
});

test('SSE received during REST wins even when both server timestamps round to the same millisecond', async () => {
  const snapshot = deferred();
  const context = sensorRuntime(async (url) => url === '/api/v1/sensors' ? snapshot.promise : { items: [] });
  const stale = { device_id: 'door-test', kind: 'door_contact', last_received_at: '2026-09-08T10:00:00.000100Z', state: { door_state: 'closed' } };
  context.sensors = [stale];
  const refresh = context.refreshSensors();
  await context.applyLiveSensorUpdate({ ...stale, last_received_at: '2026-09-08T10:00:00.000900Z', state: { door_state: 'open' } });
  snapshot.resolve({ items: [stale] });
  await refresh;
  assert.equal(context.sensors[0].state.door_state, 'open');
});

test('history network failure preserves confirmed events and marks a retry', async () => {
  const context = sensorRuntime(async () => { throw new Error('offline'); });
  const confirmed = [{ state: 'closed' }];
  context.eventHistory.set('door-test', confirmed);
  await context.refreshDoorHistory('door-test');
  assert.equal(context.eventHistory.get('door-test'), confirmed);
  assert.equal(context.historyErrors.has('door-test'), true);
});

test('a stale state snapshot still accepts newer display metadata without reverting contact state', () => {
  const context = sensorRuntime();
  const current = { device_id: 'door-test', last_received_at: '2026-09-08T10:01:00Z',
    state: { door_state: 'open' }, metadata: { display_name: 'old', updated_at: '2026-09-08T09:00:00Z' } };
  const incoming = { ...current, last_received_at: '2026-09-08T10:00:00Z',
    state: { door_state: 'closed' }, metadata: { display_name: 'new', updated_at: '2026-09-08T11:00:00Z' } };
  const result = context.mergeSensorSnapshot(incoming, current);
  assert.equal(result.state.door_state, 'open');
  assert.equal(result.metadata.display_name, 'new');
});

test('a scheduled tick with lower latency than the previous one still refreshes climate', () => {
  // Previous refresh finished 180 ms after its tick; this one only took 120 ms.
  const context = policyContext({}, kst('20:00:00.180').getTime());
  const tick = kst('20:05:00.120');
  assert.equal(context.climateRefreshAllowed(true, tick), false, 'Unscheduled reconnects keep the interval guard');
  assert.equal(context.climateRefreshAllowed(true, tick, true), true);
  assert.equal(context.climateRefreshAllowed(true, kst('12:00:00'), true), false, 'Pause hours still apply');
  context.settings.enabled = false;
  assert.equal(context.climateRefreshAllowed(true, kst('20:10:00'), true), false, 'Disabled refresh still applies');
});

test('the interval timer marks its refreshes as scheduled', () => {
  assert.match(extractFunction(sensorSource, 'scheduleAutoRefresh'), /refreshSensors\(\{ automatic: true, scheduled: true \}\)/);
  assert.match(extractFunction(sensorSource, 'refreshSensors'), /climateRefreshAllowed\(automatic, new Date\(\), scheduled\)/);
});

function joinRuntime(apiCall) {
  const element = () => ({ textContent: '', dataset: {}, hidden: false, disabled: false, value: '120' });
  const elements = new Map();
  const timers = new Set();
  let nextTimer = 0;
  const context = vm.createContext({
    apiCall, elements, timers,
    joinStatus: null, joinRequestInFlight: false, joinCountdownTimer: null, joinPollTimer: null, joinDeadlineMs: 0,
    zigbeeDevices: [], managerDialog: { open: true }, announcer: { textContent: '' },
    renderZigbeeDevices() {}, refreshSensors: async () => {},
    root: { querySelector: (selector) => { if (!elements.has(selector)) elements.set(selector, element()); return elements.get(selector); } },
    window: {
      setInterval: () => { nextTimer += 1; timers.add(nextTimer); return nextTimer; },
      clearInterval: (id) => timers.delete(id)
    }
  });
  vm.runInContext(['stopJoinTimers', 'renderJoinStatus', 'startJoinTimers', 'joinRemainingSeconds', 'refreshJoinPanel', 'openJoin', 'closeJoin']
    .map((name) => extractFunction(sensorSource, name)).join('\n'), context);
  return context;
}

test('closing the sensor manager while permit-join POST is pending sends DELETE after it resolves', async () => {
  const post = deferred();
  const requests = [];
  const context = joinRuntime((url, options = {}) => {
    requests.push(`${options.method || 'GET'} ${url}`);
    if (options.method === 'POST') return post.promise;
    return Promise.resolve({ supported: true, permit_join: false, remaining_seconds: 0, max_duration_seconds: 120 });
  });
  const opening = context.openJoin();
  await context.closeJoin({ silent: true });
  context.managerDialog.open = false;
  post.resolve({ supported: true, permit_join: true, remaining_seconds: 120, max_duration_seconds: 120 });
  await opening;
  assert.deepEqual(requests, ['POST /api/v1/zigbee/join', 'DELETE /api/v1/zigbee/join']);
  assert.equal(context.joinStatus.permit_join, false);
  assert.equal(context.timers.size, 0);
});

test('a failed permit-join close is retried once', async () => {
  let deletes = 0;
  const context = joinRuntime(async (url, options = {}) => {
    if (options.method !== 'DELETE') throw new Error(`unexpected ${url}`);
    deletes += 1;
    if (deletes === 1) throw new Error('temporary');
    return { supported: true, permit_join: false, remaining_seconds: 0, max_duration_seconds: 120 };
  });
  context.joinStatus = { supported: true, permit_join: true };
  await context.closeJoin({ silent: true });
  assert.equal(deletes, 2);
  assert.equal(context.joinStatus.permit_join, false);
});

test('millisecond permit_join_end from Zigbee2MQTT cannot show more than the allowed window', async () => {
  const context = joinRuntime(async (url) => url === '/api/v1/zigbee/devices'
    ? { items: [] }
    : { supported: true, permit_join: true, remaining_seconds: 1_757_000_000_000, max_duration_seconds: 120 });
  await context.refreshJoinPanel({ silent: true });
  assert.ok(context.joinDeadlineMs - Date.now() <= 120_000);
  assert.match(context.elements.get('[data-zigbee-join-status]').textContent, /(119|120)초 남음/);
});

test('sensor editor preserves a saved room that is not a local tab', () => {
  const option = () => ({ value: '', textContent: '' });
  const roomSelect = { options: [], value: '', replaceChildren() { this.options = []; }, append(node) { this.options.push(node); } };
  const context = vm.createContext({
    sensors: [{ device_id: 'door-test', kind: 'door_contact', metadata: { display_name: '현관문', room: '현관', icon: 'door-open' } }],
    ALLOWED_ICONS: new Set(['door-open', 'activity']),
    editorForm: { hidden: true, elements: { device_id: {}, display_name: { focus() {} }, room: roomSelect, icon: {} } },
    document: { createElement: option },
    root: {
      querySelectorAll: () => [{ textContent: '거실' }, { textContent: '침실' }],
      querySelector: () => ({ textContent: '' })
    }
  });
  vm.runInContext(['defaultMetadata', 'sensorMetadata', 'roomNames', 'openSensorEditor']
    .map((name) => extractFunction(sensorSource, name)).join('\n'), context);
  context.openSensorEditor('door-test');
  assert.deepEqual(roomSelect.options.map((item) => item.value), ['공간 미지정', '거실', '침실', '현관']);
  assert.equal(roomSelect.value, '현관');
});

test('automation event during an in-flight refresh triggers one follow-up refresh', async () => {
  const pending = [];
  const context = vm.createContext({
    loading: false, refreshQueued: false, rules: [], events: [],
    apiCall: () => { const request = deferred(); pending.push(request); return request.promise; },
    renderRules() {}, renderEvents() {}, count: { textContent: '' }, list: { replaceChildren() {}, append() {} },
    document: { createElement: () => ({}) }
  });
  vm.runInContext(extractFunction(automationSource, 'refresh'), context);
  const first = context.refresh();
  context.refresh();
  context.refresh();
  assert.equal(pending.length, 2, 'Only the first GET pair runs while loading');
  pending.splice(0).forEach((request) => request.resolve({ items: [] }));
  await first;
  assert.equal(pending.length, 2, 'Queued events coalesce into exactly one follow-up refresh');
  pending.splice(0).forEach((request) => request.resolve({ items: [] }));
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(pending.length, 0);
  assert.equal(context.loading, false);
});

test('editing invalid pause times clears custom validity so the corrected form can submit', () => {
  let error = '시작과 종료 시각은 다르게 설정해 주세요.';
  const context = vm.createContext({
    settingsForm: { elements: { pause_start: { value: '07:00' },
      pause_end: { value: '19:00', setCustomValidity(value) { error = value; } },
      interval_minutes: { value: '5' }, enabled: { checked: true } } },
    root: { querySelector: () => ({ textContent: '' }) }
  });
  vm.runInContext(extractFunction(sensorSource, 'updateSettingsPreview'), context);
  context.updateSettingsPreview();
  assert.equal(error, '');
});
