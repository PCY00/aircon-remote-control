// Ported from DeviceTest, DeviceTextTest and InventoryTest of the Android family app 0.6.2.
import test from 'node:test';
import assert from 'node:assert/strict';
import { AppEvent, ControlStatus, Device, DeviceCategory, DeviceText, Inventory, AIRCON_CAPABILITIES } from '../central_server/webapp/js/logic/device.js';
import { clean } from '../central_server/webapp/js/logic/plain.js';
import { AIRCON, CLIMATE, DOOR, NOW, aircon, climate, device, door, event, inventory } from './helpers.js';

test('parses the contract entry into plain values', () => {
  const d = Device.from(device(DOOR, '현관문', '현관', 'door_sensor', ['contact', 'battery'],
    { contact: 'closed', battery_percent: 87, battery_low: false }, 1792130000.0));
  assert.equal(d.id, DOOR); assert.equal(d.name, '현관문'); assert.equal(d.room, '현관'); assert.equal(d.type, 'door_sensor');
  assert.deepEqual([...d.capabilities], ['contact', 'battery']);
  assert.equal(d.state.battery_percent, 87); assert.equal(d.state.battery_low, false);
  assert.equal(d.reportedAt, 1792130000.0); assert.equal(d.controllable, false);
  assert.equal(Device.from(device(AIRCON, '에어컨', '', 'air_conditioner', [], {}, null)).controllable, true);
});

test('unknown types, blocks and state keys are kept but malformed ones dropped', () => {
  const state = { illuminance_lux: 120, 'Bad-Key': 'x', nan: NaN, label: '  \u0007켜짐​ ', list: [1], none: null };
  const d = Device.from(device(DOOR, '센서', '', 'air_purifier', ['filter', 'filter', 'Bad Cap', 7, 'pm25'], state, -5));
  assert.equal(d.type, 'air_purifier'); assert.equal(d.category(), 'other');
  assert.deepEqual([...d.capabilities], ['filter', 'pm25']);
  assert.equal(d.state.illuminance_lux, 120);
  assert.ok(!('Bad-Key' in d.state)); assert.ok(!('nan' in d.state)); assert.ok(!('list' in d.state));
  assert.equal(d.state.label, '켜짐');
  assert.ok('none' in d.state); assert.equal(d.state.none, null);
  assert.equal(d.reportedAt, null, 'Non-positive report times mean never reported');
  assert.equal(Device.from(device(DOOR, 'x', '', 'Not A Type', [], {}, null)).type, 'unknown');
});

test('entries without a usable id are skipped and duplicates keep the first', () => {
  const devices = Device.list([
    device('', 'a', '', 'door_sensor', [], {}, null),
    device('../x', 'b', '', 'door_sensor', [], {}, null),
    'not a map',
    device(DOOR, 'first', '', 'door_sensor', [], {}, null),
    device(DOOR, 'second', '', 'door_sensor', [], {}, null)]);
  assert.equal(devices.length, 1); assert.equal(devices[0].name, 'first');
  assert.equal(Device.from({ name: 'no id', type: 'light' }), null);
  assert.deepEqual(Device.list(null), []);
});

test('state keeps at most sixteen entries and capabilities sixteen', () => {
  const state = {}; const capabilities = [];
  for (let i = 0; i < 20; i++) { state['k' + i] = i; capabilities.push('c' + i); }
  const d = Device.from(device(DOOR, 'x', '', 'door_sensor', capabilities, state, null));
  assert.equal(Object.keys(d.state).length, 16); assert.equal(d.capabilities.length, 16);
});

test('missing name falls back to the type name', () => {
  assert.equal(Device.from(device(AIRCON, '', '', 'air_conditioner', [], {}, null)).name, '에어컨');
  assert.equal(Device.from(device(DOOR, null, null, 'door_sensor', [], {}, null)).name, '문');
  assert.equal(Device.from(device(DOOR, null, null, 'door_sensor', [], {}, null)).room, '');
});

test('category of each type follows the chosen groups', () => {
  assert.equal(DeviceCategory.of('air_conditioner'), 'hvac');
  assert.equal(DeviceCategory.of('light'), 'light');
  assert.equal(DeviceCategory.of('door_sensor'), 'security'); assert.equal(DeviceCategory.of('motion_sensor'), 'security');
  assert.equal(DeviceCategory.of('climate_sensor'), 'environment');
  assert.equal(DeviceCategory.of('leak_sensor'), 'safety'); assert.equal(DeviceCategory.of('smoke_sensor'), 'safety');
  assert.equal(DeviceCategory.of('plug'), 'power');
  assert.equal(DeviceCategory.of('robot_vacuum'), 'other'); assert.equal(DeviceCategory.of(null), 'other');
  assert.equal(DeviceCategory.label('hvac'), '냉난방'); assert.equal(DeviceCategory.label('security'), '보안');
  assert.equal(DeviceCategory.label('environment'), '환경'); assert.equal(DeviceCategory.label('safety'), '안전');
  assert.equal(DeviceCategory.label('power'), '전력'); assert.equal(DeviceCategory.label('light'), '조명'); assert.equal(DeviceCategory.label('other'), '기타');
});

test('present categories keep the chip order', () => {
  const plug = Device.from(device('p1', '플러그', '', 'plug', [], {}, null));
  assert.deepEqual(DeviceCategory.present([plug, door('closed', null, null), climate(25.0, 50.0, null), aircon({})]),
    ['hvac', 'security', 'environment', 'power']);
});

test('short name drops only a separate room word', () => {
  assert.equal(aircon({}).shortName(), '에어컨');
  assert.equal(Device.from(device(AIRCON, '거실에어컨', '거실', 'air_conditioner', [], {}, null)).shortName(), '거실에어컨');
  assert.equal(Device.from(device(AIRCON, '거실', '거실', 'air_conditioner', [], {}, null)).shortName(), '거실');
  assert.equal(Device.from(device(AIRCON, '안방 에어컨', '거실', 'air_conditioner', [], {}, null)).shortName(), '안방 에어컨');
  assert.equal(Device.from(device(DOOR, '현관문', '', 'door_sensor', [], {}, null)).shortName(), '현관문');
  assert.equal(Device.from(device(DOOR, '현관문', '현관', 'door_sensor', [], {}, null)).shortName(), '현관문');
});

test('battery sensors go stale after six hours but mains devices never', () => {
  const now = 1_800_000_000;
  assert.equal(door('closed', 80, now - 6 * 3600).stale(now), false);
  assert.equal(door('closed', 80, now - 6 * 3600 - 1).stale(now), true);
  assert.equal(door('closed', 80, null).stale(now), false, 'Never reported is not judged');
  const mains = Device.from(device('plug', '플러그', '', 'plug', ['power'], { power: true }, now - 86400));
  assert.equal(mains.stale(now), false);
  const lowFlag = Device.from(device(DOOR, '문', '', 'door_sensor', ['contact'], { battery_low: true }, now));
  assert.equal(lowFlag.hasBattery(), true, 'A battery_low key alone makes it a battery sensor');
});

test('low battery is the flag or twenty percent or less', () => {
  assert.equal(door('closed', 20, null).batteryLow(), true); assert.equal(door('closed', 21, null).batteryLow(), false);
  assert.equal(door('closed', 12.4, null).batteryPercent(), 12);
  assert.equal(door('closed', null, null).batteryLow(), false);
  assert.equal(Device.from(device(DOOR, '문', '', 'door_sensor', ['battery'], { battery_low: true, battery_percent: 60 }, null)).batteryLow(), true);
});

test('power understands booleans, strings and a mode without power', () => {
  assert.equal(aircon({ power: true }).power(), true);
  assert.equal(aircon({ power: 'off' }).power(), false);
  assert.equal(aircon({ mode: 'cool' }).power(), true);
  assert.equal(aircon({}).power(), null);
  assert.equal(door('open', null, null).contact(), 'open'); assert.equal(door(null, null, null).contact(), null);
});

// ---- DeviceTextTest ----

const of = (type, state) => Device.from(device('d' + type, '기기', '', type, [], state, null));

test('aircon tile shows mode and setpoint, or off, or unknown', () => {
  assert.equal(DeviceText.summary(aircon({ power: true, mode: 'cool', setpoint_c: 24, inferred: true }), NOW, null), '냉방 24°');
  assert.equal(DeviceText.summary(aircon({ power: 'on', mode: 'heat', setpoint_c: 22.5 }), NOW, null), '난방 22.5°');
  assert.equal(DeviceText.summary(aircon({ power: true, mode: 'dry', setpoint_c: 24 }), NOW, null), '제습');
  assert.equal(DeviceText.summary(aircon({ power: true, mode: 'fan_only' }), NOW, null), '송풍');
  assert.equal(DeviceText.summary(aircon({ power: true }), NOW, null), '켜짐');
  assert.equal(DeviceText.summary(aircon({ power: false, mode: 'cool' }), NOW, null), '꺼짐');
  assert.equal(DeviceText.summary(aircon({}), NOW, null), '상태 모름');
});

test('door tile shows the state and how long ago', () => {
  assert.equal(DeviceText.summary(door('closed', 90, NOW - 3600), NOW, NOW - 200), '닫힘 · 3분 전');
  assert.equal(DeviceText.summary(door('open', 90, NOW - 3600), NOW, null), '열림 · 1시간 전', 'Without a record the report time is used');
  assert.equal(DeviceText.summary(door('closed', 90, NOW - 20), NOW, null), '닫힘 · 방금');
  assert.equal(DeviceText.summary(door('closed', 90, null), NOW, null), '닫힘');
  assert.equal(DeviceText.summary(door(null, 90, null), NOW, null), '상태 모름');
});

test('sensor and power tiles', () => {
  assert.equal(DeviceText.summary(climate(25.14, 48.0, NOW), NOW, null), '25.1° · 48%');
  assert.equal(DeviceText.summary(climate(25.0, null, NOW), NOW, null), '25°');
  assert.equal(DeviceText.summary(climate(null, null, NOW), NOW, null), '측정값 없음');
  assert.equal(DeviceText.summary(of('light', { power: true, brightness_percent: 70 }), NOW, null), '켜짐 · 70%');
  assert.equal(DeviceText.summary(of('light', { power: false, brightness_percent: 70 }), NOW, null), '꺼짐');
  assert.equal(DeviceText.summary(of('plug', { power: true, power_w: 312 }), NOW, null), '켜짐 · 312W');
  assert.equal(DeviceText.summary(of('motion_sensor', { motion: true }), NOW, null), '움직임 감지');
  assert.equal(DeviceText.summary(of('leak_sensor', { leak: true }), NOW, null), '누수 감지');
  assert.equal(DeviceText.summary(of('smoke_sensor', { smoke: false }), NOW, null), '이상 없음');
});

test('unknown types show their first state value', () => {
  assert.equal(DeviceText.summary(of('lux_meter', { illuminance_lux: 120, battery_percent: 50 }), NOW, null), '120');
  assert.equal(DeviceText.summary(of('air_purifier', { status: '필터 교체' }), NOW, null), '필터 교체');
  assert.equal(DeviceText.summary(of('fan', { running: true }), NOW, null), '켜짐');
  assert.equal(DeviceText.summary(of('fan', {}), NOW, null), '상태 모름');
});

test('stale tiles say no response', () => {
  assert.equal(DeviceText.tile(door('closed', 90, NOW - 7 * 3600), NOW, null), '응답 없음');
  assert.equal(DeviceText.tile(door('closed', 90, NOW - 3600), NOW, null), '닫힘 · 1시간 전');
});

test('numbers, times and particles', () => {
  assert.equal(DeviceText.number(24.0), '24'); assert.equal(DeviceText.number(25.14), '25.1'); assert.equal(DeviceText.number(25.96), '26');
  assert.equal(DeviceText.number(-3.5), '-3.5'); assert.equal(DeviceText.number(-0.04), '0');
  assert.equal(DeviceText.ago(59), '방금'); assert.equal(DeviceText.ago(60), '1분 전'); assert.equal(DeviceText.ago(3599), '59분 전');
  assert.equal(DeviceText.ago(2 * 3600 + 5), '2시간 전'); assert.equal(DeviceText.ago(3 * 86400), '3일 전');
  assert.equal(DeviceText.duration(10), '1분'); assert.equal(DeviceText.duration(7 * 3600 + 100), '7시간');
  assert.equal(DeviceText.subject('현관문'), '현관문이'); assert.equal(DeviceText.subject('문 센서'), '문 센서가');
  assert.equal(DeviceText.subject('창문 1'), '창문 1이'); assert.equal(DeviceText.subject('창문 2'), '창문 2가');
  assert.equal(DeviceText.subject('Door'), 'Door가'); assert.equal(DeviceText.subject('Room'), 'Room이');
});

test('category chips summarise their devices', () => {
  const on = aircon({ power: true, mode: 'cool', setpoint_c: 24 });
  const off = Device.from(device('bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', '안방 에어컨', '안방', 'air_conditioner', [], { power: false }, null));
  assert.equal(DeviceText.category('hvac', [on, off], NOW), '냉방 24°');
  assert.equal(DeviceText.category('hvac', [off], NOW), '꺼짐');
  assert.equal(DeviceText.category('hvac', [aircon({})], NOW), '상태 모름');
  assert.equal(DeviceText.category('hvac', [on, Device.from(device('c2', '작은방 에어컨', '', 'air_conditioner', [], { power: true }, null))], NOW), '2대 켜짐');
  assert.equal(DeviceText.category('security', [door('closed', null, null)], NOW), '문 닫힘');
  const second = Device.from(device('d2', '창문', '', 'door_sensor', [], { contact: 'open' }, null));
  assert.equal(DeviceText.category('security', [door('closed', null, null), second], NOW), '문 1개 열림');
  const other = Device.from(device('c9', '안방 온습도', '안방', 'climate_sensor', [], { temperature_c: 26.2, humidity_percent: 52 }, null));
  assert.equal(DeviceText.category('environment', [climate(25.0, 48.0, NOW), other], NOW), '25.6° · 50%');
  assert.equal(DeviceText.category('light', [of('light', { power: true }),
    Device.from(device('l2', '전등', '', 'light', [], { power: true }, null))], NOW), '2개 켜짐');
  assert.equal(DeviceText.category('power', [of('plug', { power: false })], NOW), '모두 꺼짐');
  assert.equal(DeviceText.category('safety', [of('leak_sensor', { leak: false })], NOW), '이상 없음');
});

test('rooms keep first appearance and show their climate', () => {
  const hall = door('closed', null, null), living = climate(26.2, 52.0, NOW), noRoom = Device.from(device('x1', '플러그', '', 'plug', [], {}, null));
  const rooms = DeviceText.rooms([hall, noRoom, living, aircon({})]);
  assert.deepEqual([...rooms.keys()], ['현관', '', '거실']);
  assert.equal(rooms.get('거실').length, 2);
  assert.equal(DeviceText.roomClimate(rooms.get('거실')), '26.2° · 52%');
  assert.equal(DeviceText.roomClimate(rooms.get('현관')), null);
  assert.equal(DeviceText.roomLabel(''), '공간 미지정'); assert.equal(DeviceText.roomLabel('거실'), '거실');
  assert.equal(DeviceText.roomLabel('공간 미지정'), '공간 미지정', "The Pi's own default name is shown as it is");
});

test('clean drops control and format characters and cuts', () => {
  assert.equal(clean('  a‮b\u0000c  ', 80), 'abc');
  assert.equal(clean('가나다라', 2), '가나'); assert.equal(clean(null, 5), ''); assert.equal(clean(7, 5), '');
});

// ---- InventoryTest ----

const control = (online, latest, ...devices) => ControlStatus.from({ online, can_control: true, devices, latest_command: latest });
const command = (deviceId, action, state, at) => ({ id: 'c1', device_id: deviceId, action, state, created_at: at - 2, updated_at: at, expires_at: at + 30 });

test('reads the device list reply', () => {
  const inv = Inventory.from({ devices: [device(DOOR, '현관문', '현관', 'door_sensor', ['contact'], { contact: 'open' }, NOW)], updated_at: NOW - 30, hub_online: true });
  assert.equal(inv.devices.length, 1); assert.equal(inv.updatedAt, NOW - 30); assert.equal(inv.hubOnline, true);
  assert.equal(inv.fallback, false); assert.equal(inv.neverReported(), false);
  assert.equal(inv.find(DOOR).name, '현관문'); assert.equal(inv.find('missing'), null);
  assert.equal(inv.names().get(DOOR), '현관문');
  const empty = Inventory.from({ devices: [], updated_at: null, hub_online: false });
  assert.equal(empty.neverReported(), true, 'A hub that never sent a list');
});

test('events and control status parse from plain values', () => {
  const e = AppEvent.from({ id: 7, kind: 'sensor.door_changed', received_at: NOW, payload: { state: 'open', device_id: DOOR } });
  assert.equal(e.id, 7); assert.equal(e.deviceId, DOOR); assert.equal(e.doorState(), 'open'); assert.equal(e.alertCategory(), 'security');
  assert.equal(AppEvent.from({ kind: '', received_at: NOW }), null);
  assert.equal(AppEvent.from({ kind: 'sensor.climate_report', payload: { temperature_c: 25 } }).deviceId, null, 'Older records have no device_id');
  const sorted = AppEvent.list([{ id: 1, kind: 'a', received_at: NOW - 10 }, { id: 2, kind: 'b', received_at: NOW }, 'junk']);
  assert.equal(sorted[0].kind, 'b'); assert.equal(sorted.length, 2);
  const c = control(true, command(AIRCON, 'cool_24_auto', 'sent', NOW), { id: AIRCON, name: '거실 에어컨' });
  assert.equal(c.online, true); assert.equal(c.canControl, true); assert.equal(c.has(AIRCON), true);
  assert.equal(c.deviceName(AIRCON), '거실 에어컨'); assert.equal(c.latest.time(), NOW);
  assert.notEqual(c.latestFor(AIRCON), null); assert.equal(c.latestFor('other'), null);
  assert.equal(control(false, null).latest, null);
});

test('older server fallback uses the control list and the latest records', () => {
  const events = [
    event(5, 'sensor.climate_report', NOW - 60, { temperature_c: 25.1, humidity_percent: 48 }),
    event(4, 'sensor.door_changed', NOW - 120, { state: 'open' }),
    event(3, 'sensor.door_changed', NOW - 600, { state: 'closed' })];
  const inv = Inventory.effective(null, control(true, command(AIRCON, 'cool_24_low', 'sent', NOW), { id: AIRCON, name: '거실 에어컨' }), events);
  assert.equal(inv.fallback, true); assert.equal(inv.devices.length, 3);
  const a = inv.devices[0];
  assert.equal(a.type, 'air_conditioner'); assert.equal(a.controllable, true); assert.equal(a.room, '');
  assert.deepEqual([...a.capabilities], [...AIRCON_CAPABILITIES]);
  assert.equal(DeviceText.aircon(a), '냉방 24°', 'Last sent command is the inferred state');
  assert.equal(a.state.inferred, true);
  const d = inv.devices[1], c = inv.devices[2];
  assert.equal(d.id, Inventory.FALLBACK_DOOR); assert.equal(d.type, 'door_sensor'); assert.equal(d.contact(), 'open');
  assert.equal(d.reportedAt, NOW - 120); assert.equal(d.name, '문');
  assert.equal(d.hasBattery(), false, 'No battery block, so a quiet door is never 응답 없음');
  assert.equal(c.id, Inventory.FALLBACK_CLIMATE); assert.equal(c.number('temperature_c'), 25.1);
});

test('fallback sensors take the record device id when the Pi sends it', () => {
  const inv = Inventory.fallback(control(true, null), [event(1, 'sensor.door_changed', NOW, { state: 'closed', device_id: DOOR })]);
  assert.equal(inv.devices[0].id, DOOR);
});

test('unsent or unknown commands leave the aircon state unknown', () => {
  const entry = { id: AIRCON, name: '에어컨' };
  assert.equal(DeviceText.aircon(Inventory.fallback(control(true, command(AIRCON, 'cool_24_auto', 'failed', NOW), entry), []).devices[0]), '상태 모름');
  assert.equal(DeviceText.aircon(Inventory.fallback(control(true, command('other', 'power_off', 'sent', NOW), entry), []).devices[0]), '상태 모름');
  assert.equal(DeviceText.aircon(Inventory.fallback(control(true, command(AIRCON, 'power_off', 'sent', NOW), entry), []).devices[0]), '꺼짐');
  assert.equal(DeviceText.aircon(Inventory.fallback(control(true, command(AIRCON, 'mode_dry', 'sent', NOW), entry), []).devices[0]), '제습');
  assert.equal(Inventory.inferred('swing_toggle'), null, 'A toggle says nothing about the state');
  assert.equal(Inventory.inferred('cool_x_auto'), null);
});

test('a server list wins unless the Pi never sent one', () => {
  const server = inventory(NOW, true, door('closed', 90, NOW));
  assert.equal(Inventory.effective(server, control(true, null), []), server);
  const never = Inventory.from({ devices: [], updated_at: null, hub_online: true });
  const used = Inventory.effective(never, control(true, null, { id: AIRCON, name: '에어컨' }), []);
  assert.equal(used.fallback, true, '0.7 server with a 0.6 Pi still shows the aircon'); assert.equal(used.devices.length, 1);
  assert.equal(Inventory.effective(null, null, []).devices.length, 0);
});

test('hub problem means offline or a list older than ten minutes', () => {
  assert.equal(inventory(NOW - 600, true).hubProblem(NOW), false);
  assert.equal(inventory(NOW - 601, true).hubProblem(NOW), true);
  assert.equal(inventory(NOW, false).hubProblem(NOW), true);
  assert.equal(inventory(NOW, null).hubProblem(NOW), false, 'Unknown is not a problem');
  assert.equal(Inventory.fallback(control(false, null, { id: AIRCON, name: '에어컨' }), []).hubProblem(NOW), true, 'Fallback: Pi offline with aircons');
  assert.equal(Inventory.fallback(control(false, null), []).hubProblem(NOW), false, 'Fallback: a home without any hub sign');
  assert.equal(Inventory.fallback(null, [event(1, 'hub.connection_test', NOW, {})]).hubProblem(NOW), false, 'Fallback before the control answer');
});

test('climate fixtures use the shared ids', () => { assert.equal(climate(1, 2, NOW).id, CLIMATE); });
