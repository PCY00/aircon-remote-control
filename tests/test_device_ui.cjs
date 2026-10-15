const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = readFileSync(path.join(__dirname, '../app/static/index.html'), 'utf8');

function applicationFunction(name) {
  const start = source.search(new RegExp(`^      const ${name} = `, 'm'));
  assert.notEqual(start, -1, `Missing application function ${name}`);
  const tail = source.slice(start);
  const firstLine = tail.split('\n')[0];
  if (firstLine.endsWith(';')) return firstLine;
  const end = tail.search(/^      };$/m);
  assert.notEqual(end, -1, `Missing function end ${name}`);
  return tail.slice(0, end + '      };'.length);
}

class Element {
  constructor(tag) {
    this.tag = tag;
    this.dataset = {};
    this.children = [];
    this.attributes = new Map();
    this.listeners = new Map();
    this.textContent = '';
    this.hidden = false;
    this.disabled = false;
    this.classList = { toggle() {} };
  }
  append(...nodes) { this.children.push(...nodes); }
  setAttribute(name, value) { this.attributes.set(name, value); }
  getAttribute(name) { return this.attributes.get(name); }
  querySelector(tag) { return this.children.find((node) => node.tag === tag); }
  addEventListener(type, listener) { this.listeners.set(type, listener); }
}

const PROFILE_ID = 'air_conditioner/Carrier/CS-A061GS';
const BASE_FUNCTIONS = ['newAirconState', 'isH2Tile', 'deviceRecordTime', 'isOutdatedRecord', 'rememberDeviceRecord', 'rememberSkippedRecord',
  'applyApiState', 'renderAirconState', 'sendAirconState', 'executeAirconCommand', 'changeAirconState',
  'sceneDeviceKey', 'findSceneTile', 'migrateSceneDeviceKey', 'applySceneAction',
  'upsertAirconTile', 'restoreRegisteredAircons', 'resyncAircons', 'applyLiveDeviceEvent'];

function environment(apiCall, { extraFunctions = [], globals = {} } = {}) {
  const tiles = [];
  const rooms = [];
  const statuses = [];
  const stubs = new Map();
  const context = vm.createContext({
    tiles, rooms, apiCall, statuses, PROFILE_ID, File, FormData,
    airconStates: new Map(), pendingDeviceCommands: new Set(), deviceRecordTimes: new Map(), skippedDeviceRecords: new Map(), sceneConfigs: new Map(),
    activeDeviceId: '', activeAirconTile: null, airconState: null, currentInventoryRoom: '전체',
    supportedProfiles: [{ id: 'carrier', device_type: 'air_conditioner' }],
    modeToApi: { '냉방': 'cool', '자동': 'auto' }, modeFromApi: { cool: '냉방', auto: '자동' },
    fanToApi: { '자동': 'auto', '강풍': 'high', '약풍': 'low' }, fanFromApi: { auto: '자동', high: '강풍', low: '약풍' },
    document: { createElement: (tag) => new Element(tag), createTextNode: (text) => ({ tag: '#text', textContent: text }) },
    window: { setTimeout: (callback) => { callback(); return 1; }, clearTimeout() {} },
    root: {
      querySelectorAll: () => tiles,
      querySelector(selector) {
        if (selector === '.device-grid') return { append: (tile) => tiles.push(tile) };
        if (selector === '.room-tabs') return { append: (room) => rooms.push(room) };
        if (selector.includes('device-tile')) return tiles.find((tile) => tile.dataset.deviceId);
        if (!stubs.has(selector)) stubs.set(selector, new Element(selector));
        return stubs.get(selector);
      }
    },
    announcer: { textContent: '' },
    createIconNode: () => new Element('i'),
    replaceElementIcon: (tile, icon) => { tile.dataset.icon = icon; },
    attachDeviceBehavior() {}, attachRoomBehavior() {},
    getNames: () => rooms.map((room) => room.querySelector('span').textContent),
    refreshIcons() {}, updateCounts() {}, updateAirconView() {}, renderDevicesView() {}, populateProfileSelect() {},
    setApiStatus: (message, state = 'ready') => statuses.push({ message, state }),
    ...globals
  });
  const names = [...BASE_FUNCTIONS, ...extraFunctions];
  vm.runInContext(names.map(applicationFunction).join('\n')
    + '\nObject.assign(globalThis, { ' + names.join(', ') + ' });', context);
  return context;
}

const flush = () => new Promise((resolve) => setImmediate(resolve));

const devices = [
  { id: 'living-ac', name: '거실 에어컨', room: '거실', profile_id: 'carrier', icon: 'snowflake',
    last_desired_state: { power: true, temperature_c: 24, mode: 'cool', fan: 'high' } },
  { id: 'bedroom-ac', name: '침실 에어컨', room: '침실', profile_id: 'carrier', icon: 'wind',
    last_desired_state: { power: false, temperature_c: 27, mode: 'auto', fan: 'low' } }
];

function transmitted(power) {
  return { device: { last_desired_state: { power } }, transmission: { hardware_output: false } };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

test('reload restores every registered air conditioner, its room, and its own desired state', () => {
  const context = environment();
  context.restoreRegisteredAircons(devices);
  assert.equal(context.tiles.length, 2);
  assert.deepEqual(context.tiles.map((tile) => tile.dataset.deviceId), ['living-ac', 'bedroom-ac']);
  assert.deepEqual(context.rooms.map((room) => room.querySelector('span').textContent), ['거실', '침실']);
  assert.equal(context.airconStates.get('living-ac').temperature, 24);
  assert.equal(context.airconStates.get('bedroom-ac').temperature, 27);
  assert.equal(context.airconStates.get('bedroom-ac').power, false);
  assert.notEqual(context.airconStates.get('living-ac'), context.airconStates.get('bedroom-ac'));
  context.restoreRegisteredAircons(devices);
  assert.equal(context.tiles.length, 2, 'Reload must not duplicate cards');
  assert.equal(context.rooms.length, 2, 'Reload must not duplicate room tabs');
});

test('scene command targets the scene device even when a different detail was last opened', async () => {
  const calls = [];
  const context = environment(async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return transmitted(false);
  });
  context.restoreRegisteredAircons(devices);
  context.activeDeviceId = 'bedroom-ac';
  context.activeAirconTile = context.tiles[1];
  context.airconState = context.airconStates.get('bedroom-ac');
  await context.applySceneAction('거실 에어컨', { action: 'off' });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/v1/devices/living-ac/commands');
  assert.equal(calls[0].body.power, false);
  assert.equal(context.activeDeviceId, 'bedroom-ac');
  assert.equal(context.airconState.temperature, 27);
});

test('command failure after navigating to another device rolls back only the original device', async () => {
  const request = deferred();
  const context = environment(() => request.promise);
  context.restoreRegisteredAircons(devices);
  const command = context.changeAirconState({ temperature: 19 }, { tile: context.tiles[0] });
  context.activeDeviceId = 'bedroom-ac';
  context.activeAirconTile = context.tiles[1];
  context.airconState = context.airconStates.get('bedroom-ac');
  request.reject(new Error('offline'));
  await assert.rejects(command, /offline/);
  assert.equal(context.airconStates.get('living-ac').temperature, 24);
  assert.equal(context.airconState.temperature, 27);
  assert.equal(context.pendingDeviceCommands.size, 0);
});

test('rapid repeats cannot overlap a command for the same device', async () => {
  const request = deferred();
  let calls = 0;
  const context = environment(() => { calls += 1; return request.promise; });
  context.restoreRegisteredAircons(devices);
  const first = context.changeAirconState({ power: false }, { tile: context.tiles[0] });
  await assert.rejects(context.changeAirconState({ power: true }, { tile: context.tiles[0] }), /이전 명령/);
  assert.equal(calls, 1);
  request.resolve(transmitted(false));
  await first;
  assert.equal(context.airconStates.get('living-ac').power, false);
  assert.equal(context.pendingDeviceCommands.size, 0);
});

test('H2 air conditioner can send cooling, captured feature, and explicit off commands', async () => {
  const calls = [];
  const context = environment(async (url, options) => {
    const body = JSON.parse(options.body);
    calls.push({ url, body });
    return { ...transmitted(body.power ?? false), transmission: { hardware_output: true } };
  });
  context.restoreRegisteredAircons([{
    ...devices[0],
    zigbee_binding: { type: 'h2_ir', friendly_name: 'h2_ir_01' }
  }]);
  const tile = context.tiles[0];
  assert.equal(tile.dataset.irTransport, 'h2_ir');
  assert.equal(tile.querySelector('small').textContent, 'Zigbee IR · 실제 상태 미확인');
  await context.changeAirconState({ power: true, temperature: 24 }, { tile });
  assert.deepEqual(calls[0].body, {
    action: 'set_state', power: true, mode: 'cool', temperature_c: 24, fan: 'high'
  });
  await context.changeAirconState({ swing: false }, { tile, commandId: 'swing_toggle' });
  assert.deepEqual(calls[1].body, { action: 'execute', command_id: 'swing_toggle' });
  await context.changeAirconState({ power: false }, { tile });
  assert.equal(calls.length, 3);
  assert.deepEqual(calls[2].body, { action: 'set_state', power: false });
});

test('late successful response updates the originating device after navigation', async () => {
  const request = deferred();
  const context = environment(() => request.promise);
  context.restoreRegisteredAircons(devices);
  const command = context.changeAirconState({ power: false }, { tile: context.tiles[0] });
  context.activeDeviceId = 'bedroom-ac';
  context.activeAirconTile = context.tiles[1];
  context.airconState = context.airconStates.get('bedroom-ac');
  request.resolve(transmitted(false));
  await command;
  assert.equal(context.airconStates.get('living-ac').power, false);
  assert.equal(context.airconState.temperature, 27);
  assert.equal(context.activeAirconTile.dataset.deviceId, 'bedroom-ac');
});

function commanded(device, desired, updatedAt) {
  return { type: 'device.commanded', data: { device: { ...device, last_desired_state: desired, updated_at: updatedAt } } };
}

test('device.commanded from another client updates the tile and the next +/- starts from the server temperature', async () => {
  const calls = [];
  const context = environment(async (url, options) => {
    const body = JSON.parse(options.body);
    calls.push(body);
    return { device: { id: 'living-ac', last_desired_state: { power: true, mode: 'cool', temperature_c: body.temperature_c, fan: body.fan } },
      transmission: { hardware_output: false } };
  });
  context.restoreRegisteredAircons(devices);
  context.activeDeviceId = 'living-ac';
  context.applyLiveDeviceEvent(commanded(devices[0], { power: true, mode: 'cool', temperature_c: 26, fan: 'low' }, '2026-10-13T01:00:00+00:00'));
  const state = context.airconStates.get('living-ac');
  assert.equal(state.temperature, 26);
  assert.equal(state.fan, '약풍');
  assert.equal(context.tiles[0].querySelector('small').textContent, '냉방 · 26°C · 약풍');
  await context.changeAirconState((current) => ({ power: true, temperature: Math.min(30, current.temperature + 1) }), { tile: context.tiles[0] });
  assert.deepEqual(calls[0], { action: 'set_state', power: true, mode: 'cool', temperature_c: 27, fan: 'low' });
});

test('an older device record arriving late cannot overwrite a newer one', () => {
  const context = environment();
  context.restoreRegisteredAircons(devices);
  context.activeDeviceId = 'living-ac';
  context.applyLiveDeviceEvent(commanded(devices[0], { power: true, mode: 'cool', temperature_c: 26, fan: 'low' }, '2026-10-13T01:00:02+00:00'));
  context.applyLiveDeviceEvent(commanded(devices[0], { power: true, mode: 'cool', temperature_c: 20, fan: 'high' }, '2026-10-13T01:00:01+00:00'));
  assert.equal(context.airconStates.get('living-ac').temperature, 26);
  context.restoreRegisteredAircons([{ ...devices[0], updated_at: '2026-10-13T01:00:00+00:00', last_desired_state: { power: false } }]);
  assert.equal(context.airconStates.get('living-ac').power, true, 'A stale reconnect snapshot must not win either');
});

test('device.commanded is ignored while this client is still sending to that device', async () => {
  const request = deferred();
  const context = environment(() => request.promise);
  context.restoreRegisteredAircons(devices);
  context.activeDeviceId = 'living-ac';
  const command = context.changeAirconState({ temperature: 19 }, { tile: context.tiles[0] });
  context.applyLiveDeviceEvent(commanded(devices[0], { power: true, mode: 'cool', temperature_c: 28, fan: 'low' }, '2026-10-13T01:00:00+00:00'));
  assert.equal(context.airconStates.get('living-ac').temperature, 19);
  request.resolve({ device: { id: 'living-ac', updated_at: '2026-10-13T01:00:01+00:00',
    last_desired_state: { power: true, mode: 'cool', temperature_c: 19, fan: 'high' } }, transmission: { hardware_output: false } });
  await command;
  assert.equal(context.airconStates.get('living-ac').temperature, 19);
});

test('stream.ready re-reads registered devices and adds one registered by another client', async () => {
  const bedroom = { ...devices[1], updated_at: '2026-10-13T02:00:00+00:00', last_desired_state: { power: true, temperature_c: 22, mode: 'cool', fan: 'low' } };
  const study = { id: 'study-ac', name: '서재 에어컨', room: '서재', profile_id: 'carrier', icon: 'snowflake', last_desired_state: null };
  const urls = [];
  const context = environment(async (url) => { urls.push(url); return { items: [devices[0], bedroom, study] }; });
  context.restoreRegisteredAircons(devices);
  context.activeDeviceId = 'living-ac';
  context.applyLiveDeviceEvent({ type: 'stream.ready', data: {} });
  await flush();
  assert.deepEqual(urls, ['/api/v1/devices']);
  assert.equal(context.airconStates.get('bedroom-ac').temperature, 22);
  assert.equal(context.airconStates.get('bedroom-ac').power, true);
  assert.equal(context.tiles.length, 3);
});

test('live events and re-sync keep a locally renamed or deleted room', async () => {
  const later = (device, time, desired) => ({ ...device, updated_at: time, last_desired_state: desired });
  const context = environment(async () => ({ items: [
    later(devices[0], '2026-10-13T05:00:02+00:00', { power: true, mode: 'cool', temperature_c: 23, fan: 'high' }),
    later(devices[1], '2026-10-13T05:00:02+00:00', { power: true, mode: 'cool', temperature_c: 21, fan: 'low' })
  ] }));
  context.restoreRegisteredAircons(devices);
  context.activeDeviceId = 'living-ac';
  // Local edits: rename 거실 → 안방 (tab and tile) and delete the 침실 tab.
  context.rooms[0].querySelector('span').textContent = '안방';
  context.tiles[0].dataset.room = '안방';
  context.rooms.splice(1, 1);
  context.applyLiveDeviceEvent(commanded(devices[0], { power: true, mode: 'cool', temperature_c: 26, fan: 'low' }, '2026-10-13T05:00:01+00:00'));
  context.applyLiveDeviceEvent(commanded(devices[1], { power: false }, '2026-10-13T05:00:01+00:00'));
  assert.equal(context.tiles[0].dataset.room, '안방');
  assert.equal(context.airconStates.get('living-ac').temperature, 26, 'State still follows the server');
  await context.resyncAircons();
  assert.equal(context.tiles[0].dataset.room, '안방');
  assert.equal(context.tiles[1].dataset.room, '침실');
  assert.equal(context.airconStates.get('living-ac').temperature, 23);
  assert.deepEqual(context.rooms.map((room) => room.querySelector('span').textContent), ['안방'],
    'Neither 거실 nor the deleted 침실 tab may be recreated');
});

test('a newer command from another client that arrives while this client is sending is applied afterwards', async () => {
  const request = deferred();
  const context = environment(() => request.promise);
  context.restoreRegisteredAircons(devices);
  context.activeDeviceId = 'living-ac';
  const command = context.changeAirconState({ power: true, temperature: 19 }, { tile: context.tiles[0] });
  // Phone command B is recorded after kiosk command A, but its event arrives before A's response.
  context.applyLiveDeviceEvent(commanded(devices[0], { power: true, mode: 'cool', temperature_c: 28, fan: 'low' }, '2026-10-13T06:00:05+00:00'));
  request.resolve({ device: { id: 'living-ac', updated_at: '2026-10-13T06:00:04+00:00',
    last_desired_state: { power: true, mode: 'cool', temperature_c: 19, fan: 'high' } }, transmission: { hardware_output: false } });
  await command;
  assert.equal(context.airconStates.get('living-ac').temperature, 28);
  assert.equal(context.tiles[0].querySelector('small').textContent, '냉방 · 28°C · 약풍');
  assert.equal(context.skippedDeviceRecords.size, 0);
});

test('a re-sync snapshot skipped during a command is also applied afterwards when newer', async () => {
  const request = deferred();
  const context = environment((url, options = {}) => (options.method === 'POST' ? request.promise : Promise.resolve({ items: [
    { ...devices[0], updated_at: '2026-10-13T07:00:05+00:00', last_desired_state: { power: false } }
  ] })));
  context.restoreRegisteredAircons(devices);
  context.activeDeviceId = 'living-ac';
  const command = context.changeAirconState({ power: true, temperature: 20 }, { tile: context.tiles[0] });
  await context.resyncAircons();
  assert.equal(context.airconStates.get('living-ac').temperature, 20, 'Not applied while sending');
  request.resolve({ device: { id: 'living-ac', updated_at: '2026-10-13T07:00:04+00:00',
    last_desired_state: { power: true, mode: 'cool', temperature_c: 20, fan: 'high' } }, transmission: { hardware_output: false } });
  await command;
  assert.equal(context.airconStates.get('living-ac').power, false);
});

test('saving a scene before air conditioners are bound keeps stored device actions', () => {
  const field = (selector, value) => Object.assign(new Element(selector), { value });
  const row = (deviceKey, action, kind = 'switch') => {
    const element = new Element('section');
    element.dataset.sceneDevice = deviceKey;
    element.dataset.sceneDeviceKind = kind;
    element.append(field('[data-scene-action-choice]', action));
    return element;
  };
  // Bootstrap is still retrying: the AC card is the unbound '에어컨' placeholder, keyed by name.
  const rows = [row('에어컨', 'keep', 'aircon'), row('TV', 'on')];
  const context = environment(undefined, {
    extraFunctions: ['collectSceneActions'],
    globals: { root: { querySelectorAll: () => rows } }
  });
  const stored = { 'device:living-ac': { action: 'off' }, TV: { action: 'off' } };
  context.sceneConfigs.set('외출', { icon: 'door-open', actions: stored });
  const plain = (value) => JSON.parse(JSON.stringify(value));
  const actions = context.collectSceneActions('외출');
  assert.deepEqual(plain(actions['device:living-ac']), { action: 'off' });
  assert.deepEqual(plain(actions.TV), { action: 'on' });
  assert.deepEqual(stored.TV, { action: 'off' }, 'The stored config is not mutated before saving');
  context.sceneConfigs.set('외출', { icon: 'door-open', actions });
  context.migrateSceneDeviceKey('에어컨', 'device:living-ac');
  assert.deepEqual(plain(context.sceneConfigs.get('외출').actions), { 'device:living-ac': { action: 'off' }, TV: { action: 'on' } });
});

test('economy updates displayed temperature and fan from the command response', async () => {
  const calls = [];
  const context = environment(async (url, options) => {
    calls.push(JSON.parse(options.body));
    return { device: { id: 'living-ac', updated_at: '2026-10-13T03:00:00+00:00',
      last_desired_state: { power: true, mode: 'cool', temperature_c: 24, fan: 'auto' } }, transmission: { hardware_output: false } };
  });
  context.restoreRegisteredAircons(devices);
  await context.changeAirconState({}, { tile: context.tiles[0], commandId: 'economy' });
  assert.deepEqual(calls, [{ action: 'execute', command_id: 'economy' }]);
  const state = context.airconStates.get('living-ac');
  assert.equal(state.fan, '자동');
  assert.equal(state.temperature, 24);
  assert.equal(state.economy, undefined, 'Economy is a one-shot command, not a local on/off flag');
  assert.equal(context.tiles[0].querySelector('small').textContent, '냉방 · 24°C · 자동');
});

test('a rejected economy command surfaces the server detail and re-syncs the recorded state', async () => {
  const calls = [];
  const context = environment(async (url, options = {}) => {
    calls.push(`${options.method || 'GET'} ${url}`);
    if (options.method === 'POST') throw new Error('economy is available only while cooling');
    return { items: [{ ...devices[0], updated_at: '2026-10-13T04:00:00+00:00', last_desired_state: { power: false } }] };
  });
  context.restoreRegisteredAircons(devices);
  await assert.rejects(context.changeAirconState({}, { tile: context.tiles[0], commandId: 'economy' }), /only while cooling/);
  await flush();
  assert.deepEqual(calls, ['POST /api/v1/devices/living-ac/commands', 'GET /api/v1/devices']);
  assert.equal(context.airconStates.get('living-ac').power, false);
  assert.equal(context.tiles[0].querySelector('small').textContent, '꺼짐');
});

function detailHarness() {
  const named = (tag, text = '', data = {}) => Object.assign(new Element(tag), { textContent: text, dataset: { ...data } });
  const modeButtons = ['자동', '냉방', '제습', '송풍'].map((text) => named('button', text));
  const fanButtons = ['자동', '약풍', '중풍', '강풍'].map((text) => named('button', text));
  const features = ['swing', 'economy', 'turbo', 'led'].map((key) => named('button', '', { airconFeature: key }));
  const registry = {
    '[data-aircon-hero]': named('div'), '[data-aircon-power]': named('button'), '[data-h2-power-off]': named('button'),
    '[data-h2-connection-status]': named('p'), '[data-aircon-power-label]': named('span'),
    '[data-target-temperature]': named('output'), '[data-aircon-summary]': named('p'),
    '[data-aircon-feature="swing"] span': named('span'), '[data-temp-down]': named('button'), '[data-temp-up]': named('button'),
    '[data-aircon-mode] button': modeButtons, '[data-aircon-fan] button': fanButtons, '[data-aircon-feature]': features,
    '[data-aircon-feature]:not([data-aircon-feature="economy"])': features.filter((button) => button.dataset.airconFeature !== 'economy'),
    '[data-aircon-feature="economy"]': features[1], '[data-economy-note]': named('p')
  };
  const context = vm.createContext({
    registry, activeDeviceId: 'living-ac', activeAirconTile: null, pendingDeviceCommands: new Set(),
    airconState: { power: true, temperature: 17, mode: '자동', fan: '강풍', swing: true, turbo: false, led: true },
    root: {
      querySelector: (selector) => [].concat(registry[selector])[0],
      querySelectorAll: (selector) => selector.split(', ').flatMap((part) => [].concat(registry[part] || []))
    }
  });
  vm.runInContext(['isH2Tile', 'updateAirconView'].map(applicationFunction).join('\n')
    + '\nObject.assign(globalThis, { updateAirconView });', context);
  return context;
}

test('temperature, fan and economy controls are disabled outside 냉방', () => {
  const context = detailHarness();
  const { registry } = context;
  context.updateAirconView();
  assert.equal(registry['[data-temp-down]'].disabled, true);
  assert.equal(registry['[data-temp-up]'].disabled, true);
  assert.ok(registry['[data-aircon-fan] button'].every((button) => button.disabled && button.dataset.locked === 'true'));
  assert.ok(registry['[data-aircon-mode] button'].every((button) => !button.disabled), 'Mode buttons stay usable');
  assert.equal(registry['[data-aircon-feature="economy"]'].disabled, true);
  assert.match(registry['[data-aircon-summary]'].textContent, /온도·풍량 고정/);
  assert.match(registry['[data-economy-note]'].textContent, /냉방 중에만/);
  assert.equal(registry['[data-aircon-feature="economy"]'].attributes.has('aria-pressed'), false);

  context.airconState.mode = '냉방';
  context.updateAirconView();
  assert.equal(registry['[data-temp-up]'].disabled, false);
  assert.ok(registry['[data-aircon-fan] button'].every((button) => !button.disabled && button.dataset.locked === 'false'));
  assert.equal(registry['[data-aircon-feature="economy"]'].disabled, false);

  context.airconState.power = false;
  context.updateAirconView();
  assert.equal(registry['[data-aircon-feature="economy"]'].disabled, true, 'Economy needs the AC to be cooling');
  assert.equal(registry['[data-temp-up]'].disabled, false, 'Temperature can still turn cooling on');
});

test('scene editor hides temperature and fan unless the scene mode is 냉방', () => {
  const context = environment(undefined, { extraFunctions: ['createSceneSelect', 'renderSceneActionRow'] });
  context.restoreRegisteredAircons(devices);
  const row = context.renderSceneActionRow(context.tiles[0], { action: 'on', mode: '자동' });
  assert.equal(row.dataset.sceneDevice, 'device:living-ac');
  const [modeField, temperatureField, fanField] = row.children[1].children[1].children;
  assert.equal(temperatureField.hidden, true);
  assert.equal(fanField.hidden, true);
  const modeSelect = modeField.querySelector('select');
  modeSelect.value = '냉방';
  modeSelect.listeners.get('change')();
  assert.equal(temperatureField.hidden, false);
  assert.equal(fanField.hidden, false);
});

test('scene actions are keyed by device id, and the default AC key follows the first registered device', async () => {
  const calls = [];
  const context = environment(async (url, options) => { calls.push(url); return transmitted(JSON.parse(options.body).power); });
  const legacyTile = new Element('button');
  legacyTile.dataset.deviceKind = 'aircon';
  legacyTile.append(new Element('i'), Object.assign(new Element('strong'), { textContent: '에어컨' }), new Element('small'));
  context.tiles.push(legacyTile);
  context.sceneConfigs.set('외출', { icon: 'door-open', actions: { '에어컨': { action: 'off' }, TV: { action: 'off' } } });
  context.restoreRegisteredAircons(devices);
  assert.deepEqual(Object.keys(context.sceneConfigs.get('외출').actions), ['TV', 'device:living-ac']);
  assert.equal(await context.applySceneAction('device:living-ac', { action: 'off' }), true);
  assert.deepEqual(calls, ['/api/v1/devices/living-ac/commands']);
  assert.equal(await context.applySceneAction('device:removed-ac', { action: 'off' }), false);
  assert.equal(await context.applySceneAction('device:living-ac', { action: 'keep' }), true);
});

test('scene targeting a missing device reports partial failure instead of 완료', async () => {
  const timers = [];
  const context = environment(async (url, options) => transmitted(JSON.parse(options.body).power), {
    extraFunctions: ['getSceneActionCount', 'runScene'],
    globals: { window: { setTimeout: (callback) => timers.push(callback) }, updateSceneCardSummary() {} }
  });
  context.restoreRegisteredAircons(devices);
  context.sceneConfigs.set('외출', { icon: 'door-open', actions: { 'device:living-ac': { action: 'off' }, 'device:removed-ac': { action: 'off' } } });
  const status = new Element('[data-scene-status]');
  const button = new Element('button');
  button.dataset.name = '외출';
  button.append(status);
  context.runScene(button);
  await timers.shift()();
  assert.equal(status.textContent, '일부 기기 없음');
  assert.match(context.announcer.textContent, /1개를 찾지 못함/);
  assert.equal(context.statuses.at(-1).state, 'error');
  assert.equal(context.airconStates.get('living-ac').power, false, 'Resolvable devices still run');
});

test('model request drops empty optional file parts but keeps attached files', () => {
  const context = environment(undefined, { extraFunctions: ['dropEmptyFileParts'] });
  const formData = new FormData();
  formData.append('brand', 'Carrier');
  formData.append('product_photo', new File([Buffer.from([0xff, 0xd8, 0xff])], 'p.jpg', { type: 'image/jpeg' }));
  formData.append('remote_photo', new File([], ''));
  formData.append('manual', new File([], ''));
  context.dropEmptyFileParts(formData);
  assert.deepEqual([...formData.keys()], ['brand', 'product_photo']);
});

function bootstrapEnvironment(handler) {
  const calls = [];
  const retries = [];
  const context = environment(async (url, options = {}) => {
    calls.push(`${options.method || 'GET'} ${url}`);
    return handler(url, options, calls);
  }, {
    extraFunctions: ['wait', 'scheduleBootstrapRetry', 'runBootstrap', 'bootstrapApi', 'refreshSystemStatus'],
    globals: {
      supportedProfiles: [], transmitterInfo: { transport: 'unknown', hardware_output: false },
      bootstrapPromise: null, bootstrapRetryTimer: null, bootstrapFailures: 0,
      window: {
        setTimeout: (callback, delay) => { if (delay < 5000) callback(); else retries.push(delay); return retries.length; },
        clearTimeout() {}
      }
    }
  });
  return { context, calls, retries };
}

const carrierProfile = { items: [{ id: PROFILE_ID, device_type: 'air_conditioner' }] };
const primaryDevice = { ...devices[0], profile_id: PROFILE_ID };

test('다시 확인 retries a failed bootstrap and does not report Mock IR after a failure', async () => {
  let online = false;
  const { context, retries } = bootstrapEnvironment(async (url) => {
    if (!online && url !== '/health') throw new Error('offline');
    if (url === '/api/v1/device-profiles') return carrierProfile;
    if (url === '/api/v1/ir/transmitter') return { transport: 'h2', hardware_output: true };
    if (url === '/api/v1/devices') return { items: [primaryDevice] };
    return { status: 'ok' };
  });
  assert.equal(await context.bootstrapApi(), false);
  assert.match(context.statuses.at(-1).message, /API 연결 실패/);
  assert.deepEqual(retries, [5000], 'A failed bootstrap schedules an automatic retry');
  context.statuses.length = 0;
  await context.refreshSystemStatus();
  assert.ok(context.statuses.every(({ message }) => !message.includes('Mock IR')), 'Must not paint a healthy Mock IR status over a failure');
  assert.match(context.statuses.at(-1).message, /API 연결 실패/);
  online = true;
  await context.refreshSystemStatus();
  assert.equal(context.activeDeviceId, 'living-ac');
  assert.equal(context.statuses.at(-1).message, 'IR 송신기 연결됨');
});

test('concurrent bootstrap triggers share one request and a stream.ready during startup does not start another', async () => {
  const { context, calls } = bootstrapEnvironment(async (url) => {
    if (url === '/api/v1/device-profiles') return carrierProfile;
    if (url === '/api/v1/ir/transmitter') return { hardware_output: false };
    return { items: [primaryDevice] };
  });
  const first = context.bootstrapApi();
  context.applyLiveDeviceEvent({ type: 'stream.ready', data: {} });
  assert.equal(context.bootstrapApi(), first);
  assert.equal(await first, true);
  assert.equal(calls.filter((call) => call === 'GET /api/v1/device-profiles').length, 1);
});

test('first load re-checks the registry before creating the default air conditioner', async () => {
  let listCalls = 0;
  const { context, calls } = bootstrapEnvironment(async (url) => {
    if (url === '/api/v1/device-profiles') return carrierProfile;
    if (url === '/api/v1/ir/transmitter') return { hardware_output: false };
    listCalls += 1;
    return { items: listCalls === 1 ? [] : [primaryDevice] };
  });
  assert.equal(await context.bootstrapApi(), true);
  assert.equal(calls.some((call) => call.startsWith('POST')), false, 'Another client already created it');
  assert.equal(context.activeDeviceId, 'living-ac');
});

test('when two first loads both create a device, every client uses the oldest one', async () => {
  const older = { ...primaryDevice, id: 'older-ac', created_at: '2026-10-13T00:00:00+00:00' };
  const mine = { ...primaryDevice, id: 'mine-ac', created_at: '2026-10-13T00:00:01+00:00' };
  const { context, calls } = bootstrapEnvironment(async (url, options, history) => {
    if (url === '/api/v1/device-profiles') return carrierProfile;
    if (url === '/api/v1/ir/transmitter') return { hardware_output: false };
    if (options.method === 'POST') return mine;
    return { items: history.some((call) => call.startsWith('POST')) ? [older, mine] : [] };
  });
  assert.equal(await context.bootstrapApi(), true);
  assert.equal(calls.filter((call) => call.startsWith('POST')).length, 1);
  assert.equal(context.activeDeviceId, 'older-ac');
});
