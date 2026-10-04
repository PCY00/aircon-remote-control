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
    this.textContent = '';
  }
  append(...nodes) { this.children.push(...nodes); }
  setAttribute(name, value) { this.attributes.set(name, value); }
  querySelector(tag) { return this.children.find((node) => node.tag === tag); }
}

function environment(apiCall) {
  const tiles = [];
  const rooms = [];
  const context = vm.createContext({
    tiles, rooms, apiCall,
    airconStates: new Map(), pendingDeviceCommands: new Set(),
    activeDeviceId: '', activeAirconTile: null, airconState: null,
    supportedProfiles: [{ id: 'carrier', device_type: 'air_conditioner' }],
    modeToApi: { '냉방': 'cool', '자동': 'auto' }, modeFromApi: { cool: '냉방', auto: '자동' },
    fanToApi: { '강풍': 'high', '약풍': 'low' }, fanFromApi: { high: '강풍', low: '약풍' },
    document: { createElement: (tag) => new Element(tag) },
    root: {
      querySelectorAll: () => tiles,
      querySelector(selector) {
        if (selector === '.device-grid') return { append: (tile) => tiles.push(tile) };
        if (selector === '.room-tabs') return { append: (room) => rooms.push(room) };
        return tiles.find((tile) => tile.dataset.deviceId);
      }
    },
    createIconNode: () => new Element('i'),
    replaceElementIcon: (tile, icon) => { tile.dataset.icon = icon; },
    attachDeviceBehavior() {}, attachRoomBehavior() {},
    getNames: () => rooms.map((room) => room.querySelector('span').textContent),
    refreshIcons() {}, updateCounts() {}, updateAirconView() {}, setApiStatus() {}
  });
  const names = ['newAirconState', 'isH2Tile', 'applyApiState', 'renderAirconState', 'sendAirconState',
    'executeAirconCommand', 'changeAirconState', 'applySceneAction', 'upsertAirconTile', 'restoreRegisteredAircons'];
  vm.runInContext(names.map(applicationFunction).join('\n')
    + '\nObject.assign(globalThis, { ' + names.join(', ') + ' });', context);
  return context;
}

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
