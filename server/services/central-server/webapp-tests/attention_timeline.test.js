// Ported from AttentionTest and TimelineTest of the Android family app 0.6.2.
import test from 'node:test';
import assert from 'node:assert/strict';
import * as Attention from '../central_server/webapp/js/logic/attention.js';
import * as Timeline from '../central_server/webapp/js/logic/timeline.js';
import { ControlStatus, Device } from '../central_server/webapp/js/logic/device.js';
import { AIRCON, CLIMATE, DOOR, NOW, aircon, climate, device, door, event, inventory } from './helpers.js';

const control = (state, at) => ControlStatus.from({ online: true, can_control: true, devices: [{ id: AIRCON, name: '거실 에어컨' }],
  latest_command: { id: 'c1', device_id: AIRCON, action: 'cool_24_auto', state, created_at: at, updated_at: at } });
const keys = (items) => items.map((item) => item.key);

test('an open door counts from its latest open record', () => {
  const events = [event(2, 'sensor.door_changed', NOW - 12 * 60, { state: 'open', device_id: DOOR }),
    event(1, 'sensor.door_changed', NOW - 3600, { state: 'closed', device_id: DOOR })];
  const items = Attention.compute(inventory(NOW, true, door('open', 90, NOW - 30)), events, null, NOW);
  assert.equal(items.length, 1);
  const item = items[0];
  assert.equal(item.title, '현관문이 열려 있어요'); assert.equal(item.detail, '12분째');
  assert.equal(item.tone, Attention.DANGER); assert.equal(item.deviceId, DOOR); assert.equal(item.category, 'security');
  assert.equal(Attention.compute(inventory(NOW, true, door('open', 90, NOW - 180)), [], null, NOW)[0].detail, '3분째',
    'Without a matching record the report time is used');
  assert.equal(Attention.compute(inventory(NOW, true, door('open', 90, NOW - 10)), [], null, NOW)[0].detail, '방금 열렸어요');
  assert.equal(Attention.compute(inventory(NOW, true, door('closed', 90, NOW)), [], null, NOW).length, 0, 'A closed door needs nothing');
});

test('older records without device id still time the door', () => {
  const events = [event(1, 'sensor.door_changed', NOW - 7200, { state: 'open' })];
  assert.equal(Attention.compute(inventory(NOW, true, door('open', null, null)), events, null, NOW)[0].detail, '2시간째');
});

test('low battery is a warning', () => {
  const item = Attention.compute(inventory(NOW, true, door('closed', 12, NOW)), [], null, NOW)[0];
  assert.equal(item.title, '현관문'); assert.equal(item.detail, '배터리 12%'); assert.equal(item.tone, Attention.WARNING);
  assert.equal(item.category, 'device');
});

test('stale sensors are neutral unless the hub is down', () => {
  const quiet = climate(25.0, 50.0, NOW - 7 * 3600);
  const item = Attention.compute(inventory(NOW, true, quiet), [], null, NOW)[0];
  assert.equal(item.title, '거실 온습도'); assert.equal(item.detail, '응답 없음 · 7시간'); assert.equal(item.tone, Attention.NEUTRAL);
  const hubDown = Attention.compute(inventory(NOW - 3600, true, quiet), [], null, NOW);
  assert.deepEqual(keys(hubDown), ['hub']);
  assert.equal(hubDown[0].title, 'Pi와 연결이 끊겼어요'); assert.equal(hubDown[0].detail, '마지막 연결 1시간 전');
  assert.deepEqual(keys(Attention.compute(inventory(NOW, false), [], null, NOW)), ['hub']);
});

test('a failed or unknown command stays for ten minutes', () => {
  const inv = inventory(NOW, true, aircon({}));
  const failed = Attention.compute(inv, [], control('failed', NOW - 120), NOW)[0];
  assert.equal(failed.title, '거실 에어컨 명령이 전달되지 않았어요'); assert.equal(failed.detail, '냉방 24°C · 자동 · 2분 전');
  assert.equal(failed.deviceId, AIRCON); assert.equal(failed.tone, Attention.DANGER);
  assert.equal(Attention.compute(inv, [], control('unknown', NOW - 600), NOW).length, 1);
  assert.equal(Attention.compute(inv, [], control('unknown', NOW - 601), NOW).length, 0);
  assert.equal(Attention.compute(inv, [], control('sent', NOW), NOW).length, 0);
  assert.equal(Attention.compute(inv, [], control('queued', NOW), NOW).length, 0);
});

test('an automation warning counts only until it is resolved', () => {
  const active = [event(2, 'automation.warning_triggered', NOW - 300, {}), event(1, 'automation.warning_resolved', NOW - 900, {})];
  const item = Attention.compute(inventory(NOW, true), active, null, NOW)[0];
  assert.equal(item.title, '자동화 경고가 켜져 있어요'); assert.equal(item.detail, '5분 전'); assert.equal(item.deviceId, null);
  assert.equal(item.category, 'automation');
  const resolved = [event(3, 'automation.warning_resolved', NOW - 60, {}), event(2, 'automation.warning_triggered', NOW - 300, {})];
  assert.equal(Attention.compute(inventory(NOW, true), resolved, null, NOW).length, 0);
});

test('danger comes first, then warnings, then neutral items', () => {
  const quiet = Device.from(device('cccccccccccccccccccccccccccccccc', '창문', '', 'door_sensor', ['battery'], { contact: 'closed', battery_percent: 80 }, NOW - 8 * 3600));
  const items = Attention.compute(inventory(NOW, true, quiet, door('open', 10, NOW)),
    [event(1, 'automation.warning_triggered', NOW, {})], control('failed', NOW), NOW);
  assert.deepEqual(keys(items), ['door:' + DOOR, 'command:c1', 'automation:1', 'battery:' + DOOR, 'stale:cccccccccccccccccccccccccccccccc']);
  assert.equal(Attention.filter(items, 'security').length, 1); assert.equal(Attention.filter(items, 'device').length, 3);
  assert.equal(Attention.filter(items, 'all').length, 5);
  assert.equal(Attention.compute(null, [], null, NOW).length, 0);
  assert.deepEqual(items.map(Attention.iconOf), ['door', 'aircon', 'warning', 'battery', 'wifi_off']);
});

test('changedAt is the door\'s latest record', () => {
  const events = [event(3, 'sensor.climate_report', NOW, { device_id: CLIMATE }), event(2, 'sensor.door_changed', NOW - 40, { state: 'closed', device_id: DOOR })];
  assert.equal(Attention.changedAt(door('closed', null, null), events), NOW - 40);
  assert.equal(Attention.changedAt(climate(25.0, 50.0, NOW), events), null);
  assert.equal(Attention.changedAt(door('closed', null, null), []), null);
});

// ---- TimelineTest (Asia/Seoul) ----

const SEOUL = 'Asia/Seoul';
/** 2026-10-16 15:00 in Seoul. */
const T = Date.UTC(2026, 9, 16, 6, 0, 0) / 1000;
const NAMES = new Map([[DOOR, '현관문'], [CLIMATE, '거실 온습도']]);
const doorEvent = (id, at, state, deviceId) => event(id, 'sensor.door_changed', at, deviceId ? { state, device_id: deviceId } : { state });

test('day headers are today, yesterday or the date', () => {
  assert.equal(Timeline.dayLabel(T - 3600, T, SEOUL), '오늘');
  assert.equal(Timeline.dayLabel(T - 15 * 3600, T, SEOUL), '오늘');
  assert.equal(Timeline.dayLabel(T - 15 * 3600 - 1, T, SEOUL), '어제');
  assert.equal(Timeline.dayLabel(T - 2 * 86400, T, SEOUL), '10월 14일');
  assert.equal(Timeline.dayLabel(Date.UTC(2025, 11, 31, 0, 0, 0) / 1000, T, SEOUL), '2025년 12월 31일');
  assert.equal(Timeline.dayLabel(0, T, SEOUL), '시각 정보 없음');
  assert.equal(Timeline.clock(T - 55 * 60, SEOUL), '14:05');
  assert.equal(Timeline.clock(Date.UTC(2026, 9, 15, 15, 7, 0) / 1000, SEOUL), '00:07', 'Midnight is 00, not 24');
});

test('consecutive records of one device and kind collapse within a day', () => {
  const events = [
    doorEvent(9, T - 60, 'closed', DOOR), doorEvent(8, T - 120, 'open', DOOR), doorEvent(7, T - 600, 'closed', DOOR),
    event(6, 'sensor.climate_report', T - 700, { temperature_c: 25.1, humidity_percent: 48, device_id: CLIMATE }),
    doorEvent(5, T - 800, 'open', DOOR),
    doorEvent(4, T - 16 * 3600, 'closed', DOOR), doorEvent(3, T - 16 * 3600 - 60, 'open', DOOR)];
  const days = Timeline.build(events, NAMES, SEOUL, T);
  assert.equal(days.length, 2);
  assert.equal(days[0].label, '오늘'); assert.equal(days[1].label, '어제');
  const today = days[0].rows;
  assert.equal(today.length, 3);
  assert.equal(today[0].count(), 3);
  assert.equal(Timeline.rowTitle(today[0], NAMES), '현관문 열림·닫힘 3번');
  assert.equal(Timeline.rowTime(today[0], SEOUL), '14:50–14:59');
  assert.equal(Timeline.rowTitle(today[1], NAMES), '거실 온습도 · 25.1° · 48%');
  assert.equal(Timeline.rowTitle(today[2], NAMES), '현관문 열림', 'A different record in between starts a new row');
  assert.equal(days[1].rows[0].count(), 2, 'The day boundary splits runs');
});

test('different devices of the same kind do not collapse', () => {
  const window = 'cccccccccccccccccccccccccccccccc';
  const days = Timeline.build([doorEvent(2, T - 60, 'open', DOOR), doorEvent(1, T - 120, 'open', window)], NAMES, SEOUL, T);
  assert.equal(days[0].rows.length, 2);
  assert.equal(Timeline.rowTitle(days[0].rows[1], NAMES), '문 열림', 'Unknown ids fall back to the generic title');
});

test('older records keep their generic titles', () => {
  assert.equal(Timeline.title(doorEvent(1, T, 'closed', null), null), '문 닫힘');
  assert.equal(Timeline.title(event(1, 'sensor.climate_report', T, { temperature_c: 25.1, humidity_percent: 48 }), null), '온습도 측정 · 25.1° · 48%');
  assert.equal(Timeline.title(event(1, 'hub.connection_test', T, {}), null), '기기 연결 시험');
  assert.equal(Timeline.title(event(1, 'automation.warning_triggered', T, {}), null), '자동화 경고 발생');
  assert.equal(Timeline.title(event(1, 'automation.warning_resolved', T, {}), null), '자동화 경고 해제');
  assert.equal(Timeline.title(event(1, 'sensor.open', T, {}), null), '문 열림');
  assert.equal(Timeline.title(event(1, 'sensor.motion_detected', T, {}), '현관'), '현관 움직임 감지');
  assert.equal(Timeline.title(event(1, 'sensor.leak_detected', T, {}), null), '누수 감지');
  assert.equal(Timeline.title(event(1, 'family.control', T, {}), null), '가족 활동');
  assert.equal(Timeline.title(event(1, 'something.else', T, {}), null), '집의 새 기록');
});

test('collapsed titles for single states, climate and warnings', () => {
  const doors = Timeline.build([doorEvent(2, T - 60, 'open', null), doorEvent(1, T - 90, 'open', null)], NAMES, SEOUL, T);
  assert.equal(Timeline.rowTitle(doors[0].rows[0], NAMES), '문 열림 2번');
  const climates = Timeline.build([event(2, 'sensor.climate_report', T - 60, { device_id: CLIMATE }),
    event(1, 'sensor.climate_report', T - 120, { device_id: CLIMATE })], NAMES, SEOUL, T);
  assert.equal(Timeline.rowTitle(climates[0].rows[0], NAMES), '거실 온습도 측정 2번');
  const warnings = Timeline.build([event(2, 'automation.warning_resolved', T - 60, {}),
    event(1, 'automation.warning_triggered', T - 120, {})], NAMES, SEOUL, T);
  assert.equal(Timeline.rowTitle(warnings[0].rows[0], NAMES), '자동화 경고 발생·해제 2번');
  assert.notEqual(doors[0].rows[0].key(), climates[0].rows[0].key());
});

test('records belong to a device by id, or by kind when older', () => {
  const d = door('closed', null, null), c = climate(25.0, 50.0, null);
  assert.equal(Timeline.belongsTo(doorEvent(1, T, 'open', DOOR), d), true);
  assert.equal(Timeline.belongsTo(doorEvent(1, T, 'open', 'cccccccccccccccccccccccccccccccc'), d), false);
  assert.equal(Timeline.belongsTo(doorEvent(1, T, 'open', null), d), true);
  assert.equal(Timeline.belongsTo(doorEvent(1, T, 'open', null), c), false);
  assert.equal(Timeline.belongsTo(event(1, 'sensor.climate_report', T, {}), c), true);
  assert.equal(Timeline.belongsTo(event(1, 'hub.connection_test', T, {}), aircon({})), false);
});

test('timeline icons per alert category', () => {
  assert.equal(Timeline.icon('safety'), 'droplet'); assert.equal(Timeline.icon('security'), 'door');
  assert.equal(Timeline.icon('family'), 'family'); assert.equal(Timeline.icon('other'), 'hub');
});
