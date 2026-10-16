// Ported from AlertLevelsTest, AirconUiTest, CommandPollTest, FanLevelsTest and TemperatureDialTest.
import test from 'node:test';
import assert from 'node:assert/strict';
import * as A from '../central_server/webapp/js/logic/alerts.js';
import * as U from '../central_server/webapp/js/logic/aircon.js';

const { SAFETY, SECURITY, DEVICE, ENVIRONMENT, REPORT, AUTOMATION, FAMILY, OTHER, URGENT, ALERT, QUIET, OFF } = A;

test('event kinds map to the contract categories', () => {
  assert.equal(A.categoryOf('safety.gas'), SAFETY); assert.equal(A.categoryOf('sensor.leak_detected'), SAFETY); assert.equal(A.categoryOf('sensor.smoke_detected'), SAFETY);
  for (const kind of ['sensor.door_changed', 'sensor.open', 'sensor.closed', 'sensor.motion_detected']) assert.equal(A.categoryOf(kind), SECURITY, kind);
  assert.equal(A.categoryOf('device.battery_low'), DEVICE);
  assert.equal(A.categoryOf('environment.too_hot'), ENVIRONMENT); assert.equal(A.categoryOf('sensor.climate_threshold'), ENVIRONMENT);
  assert.equal(A.categoryOf('sensor.climate_report'), REPORT);
  assert.equal(A.categoryOf('automation.warning_triggered'), AUTOMATION); assert.equal(A.categoryOf('automation.ran'), AUTOMATION);
  assert.equal(A.categoryOf('family.control'), FAMILY);
  assert.equal(A.categoryOf('hub.connection_test'), OTHER); assert.equal(A.categoryOf('sensor.unknown'), OTHER); assert.equal(A.categoryOf(null), OTHER);
});

test('legacy FCM categories map to alert categories', () => {
  assert.equal(A.fromLegacy('door'), SECURITY); assert.equal(A.fromLegacy('climate'), REPORT);
  assert.equal(A.fromLegacy('warning'), AUTOMATION); assert.equal(A.fromLegacy('other'), OTHER); assert.equal(A.fromLegacy(null), OTHER);
  assert.equal(A.incomingCategory('safety', 'other'), SAFETY, 'alert_category wins over the legacy value');
  assert.equal(A.incomingCategory(null, 'door'), SECURITY); assert.equal(A.incomingCategory('', 'climate'), REPORT);
  assert.equal(A.incomingCategory('weather', 'door'), OTHER, 'Unknown new categories are shown as other');
});

test('safety cannot be silenced and other is not configurable', () => {
  assert.deepEqual(A.allowed(SAFETY), [URGENT, ALERT]);
  for (const category of [SECURITY, DEVICE, ENVIRONMENT, REPORT, AUTOMATION, FAMILY]) assert.deepEqual(A.allowed(category), [URGENT, ALERT, QUIET, OFF], category);
  assert.equal(A.allowed(OTHER).length, 0); assert.equal(A.configurable(OTHER), false);
  assert.equal(A.valid(SAFETY, QUIET), false); assert.equal(A.valid(SAFETY, OFF), false); assert.equal(A.valid(REPORT, OFF), true); assert.equal(A.valid(SECURITY, 'loud'), false);
  assert.equal(A.CATEGORIES.length, 7);
});

test('defaults follow the contract and normalizing always sends all seven', () => {
  const levels = A.defaults();
  assert.equal(levels[SAFETY], URGENT); assert.equal(levels[SECURITY], ALERT); assert.equal(levels[DEVICE], ALERT);
  assert.equal(levels[ENVIRONMENT], QUIET); assert.equal(levels[REPORT], OFF); assert.equal(levels[AUTOMATION], ALERT);
  assert.equal(levels[FAMILY], QUIET); assert.equal(Object.keys(levels).length, 7);
  assert.deepEqual(A.normalizeLevels(null), A.defaults());
  const fixed = A.normalizeLevels({ safety: 'off', report: 'alert', other: 'urgent', bogus: 'x' });
  assert.equal(fixed.safety, URGENT, 'safety cannot be off'); assert.equal(fixed.report, ALERT);
  assert.deepEqual(Object.keys(fixed), [...A.CATEGORIES]);
  assert.equal(A.normalizeInterval(15), 15); assert.equal(A.normalizeInterval(10), 5);
});

test('report interval and the 전체 list follow the level', () => {
  assert.equal(A.reportIntervalVisible(ALERT), true); assert.equal(A.reportIntervalVisible(URGENT), true); assert.equal(A.reportIntervalVisible(QUIET), false);
  assert.equal(A.validInterval(15), true); assert.equal(A.validInterval(10), false);
  assert.equal(A.showsInAll(SECURITY, QUIET), true); assert.equal(A.showsInAll(SECURITY, OFF), false); assert.equal(A.showsInAll(OTHER, null), true);
});

test('quiet hours handle ranges crossing midnight', () => {
  const start = 23 * 60, end = 7 * 60;
  assert.equal(A.inQuietHours(start, end, 23 * 60), true); assert.equal(A.inQuietHours(start, end, 2 * 60), true); assert.equal(A.inQuietHours(start, end, 7 * 60 - 1), true);
  assert.equal(A.inQuietHours(start, end, 7 * 60), false); assert.equal(A.inQuietHours(start, end, 12 * 60), false); assert.equal(A.inQuietHours(start, end, 23 * 60 - 1), false);
  assert.equal(A.inQuietHours(13 * 60, 14 * 60, 13 * 60 + 30), true); assert.equal(A.inQuietHours(13 * 60, 14 * 60, 14 * 60), false); assert.equal(A.inQuietHours(13 * 60, 14 * 60, 12 * 60), false);
  assert.equal(A.inQuietHours(600, 600, 600), false, 'An empty range is never quiet');
  assert.equal(A.QUIET_START, 23 * 60); assert.equal(A.QUIET_END, 7 * 60);
});

test('quiet-hours body, clock texts and the UTC offset', () => {
  assert.equal(A.parseClock('07:30'), 450); assert.equal(A.parseClock('23:59'), 1439); assert.equal(A.parseClock('00:00'), 0);
  for (const bad of ['24:00', '7:30', '07:60', '', null, '07:30:00']) assert.equal(A.parseClock(bad), null, String(bad));
  assert.equal(A.formatClock(450), '07:30'); assert.equal(A.formatClock(0), '00:00'); assert.equal(A.formatClock(1439), '23:59');
  const seoul = { getTimezoneOffset: () => -540 }, utc = { getTimezoneOffset: () => 0 }, newYork = { getTimezoneOffset: () => 240 };
  assert.equal(A.utcOffsetMinutes(seoul), 540); assert.equal(Object.is(A.utcOffsetMinutes(utc), 0), true); assert.equal(A.utcOffsetMinutes(newYork), -240);
  assert.deepEqual(A.quietHoursBody('s'.repeat(64), { enabled: true, start: 1380, end: 420 }, seoul),
    { secret: 's'.repeat(64), enabled: true, start_minute: 1380, end_minute: 420, utc_offset_minutes: 540 });
  assert.deepEqual(A.quietHoursBody('x', { enabled: true, start: 1440, end: 0 }, utc),
    { secret: 'x', enabled: false, start_minute: 1380, end_minute: 420, utc_offset_minutes: 0 }, 'Invalid saved values fall back to the default (off)');
  assert.equal(A.validQuiet(A.defaultQuiet()), true);
});

test('notification text is generic per category and tags do not mix', () => {
  assert.equal(A.body(OTHER, true), '시험 알림이 도착했어요.');
  assert.equal(A.body(OTHER, false), '새 기록이 도착했어요. 앱에서 확인해 주세요.');
  for (const category of A.FILTERS) assert.ok(A.body(category, false).length > 0);
  assert.equal(A.body(SECURITY, false), '문이나 움직임에 변화가 있어요. 앱에서 확인해 주세요.');
  assert.equal(A.NOTIFICATION_TITLE, '우리 집 알림');
  assert.equal(A.tag(SECURITY), 'family-security'); assert.equal(A.tag('weird'), 'family-other');
  assert.equal(A.levelLabel(URGENT), '긴급'); assert.equal(A.levelLabel(OFF), '끔'); assert.equal(A.label(REPORT), '정기 보고');
  assert.equal(A.caption(SAFETY), '누수·연기');
});

// ---- AirconUiTest ----

test('viewer, offline and pending commands cannot send', () => {
  assert.equal(U.canSend(false, true, 'sent'), false);
  assert.equal(U.canSend(true, false, 'sent'), false);
  assert.equal(U.canSend(true, true, 'queued'), false);
  assert.equal(U.canSend(true, true, 'dispatched'), false);
  assert.equal(U.canSend(true, true, 'sent'), true);
  assert.equal(U.canSend(true, true, ''), true);
});

test('sent means infrared transmission and unknown requires checking the appliance', () => {
  assert.ok(U.description('sent').includes('실제 작동은 에어컨에서 확인'));
  assert.ok(U.description('unknown').includes('다시 누르기 전에'));
  assert.ok(!U.description('unknown').includes('실행하지 않았'));
});

test('changing mode preserves the unsent cooling draft', () => {
  const draft = new U.Draft(); draft.temperature = 19; draft.fan = 3;
  draft.mode = 2; assert.equal(draft.action(), 'mode_dry');
  draft.mode = 0; assert.equal(draft.action(), 'cool_19_high');
  assert.equal(U.actionLabel(draft.action()), '냉방 19°C · 강풍');
});

test('unsupported cooling values cannot become commands', () => {
  for (const [t, f] of [[16, 0], [31, 0], [24, -1], [24, 4], [24.5, 0]]) assert.throws(() => U.coolingAction(t, f), RangeError);
  assert.equal(U.coolingAction(17, 0), 'cool_17_auto');
  assert.equal(U.coolingAction(30, 3), 'cool_30_high');
});

test('toggle commands explain that they change the current appliance state', () => {
  assert.ok(U.confirmation('swing_toggle').includes('누를 때마다'));
  assert.ok(U.confirmation('led_toggle').includes('현재 상태를 읽지 못해요'));
  assert.equal(U.actionLabel('airflow_fix'), '풍향 고정');
  assert.equal(U.actionLabel('mode_dry'), '제습 운전');
});

test('economy explains it keeps the cooling temperature and only works while cooling', () => {
  const text = U.confirmation('economy');
  assert.ok(text.startsWith('절전 신호를 보내요.'));
  assert.ok(text.includes('냉방 온도는 그대로')); assert.ok(text.includes('바람만 자동'));
  assert.ok(text.includes('냉방 중에만')); assert.ok(text.includes('실패로 표시'));
  assert.ok(!U.confirmation('turbo').includes('냉방 중에만'));
  assert.ok(U.description('failed', 'economy').includes('냉방 중에만'));
  assert.equal(U.description('failed', 'turbo'), U.description('failed'));
  assert.equal(U.description('sent', 'economy'), U.description('sent'));
});

test('one-line status uses short actions and state words', () => {
  assert.equal(U.shortLabel('cool_24_high'), '냉방 24°'); assert.equal(U.shortLabel('cool_on'), '냉방 24°');
  assert.equal(U.shortLabel('power_off'), '끄기'); assert.equal(U.shortLabel('mode_dry'), '제습'); assert.equal(U.shortLabel('economy'), '절전');
  assert.equal(U.stateLabel('queued'), '전달 중'); assert.equal(U.stateLabel('dispatched'), '전달 중');
  assert.equal(U.stateLabel('sent'), '전달됨'); assert.equal(U.stateLabel('unknown'), '결과 모름'); assert.equal(U.stateLabel(''), '');
  assert.equal(U.problem('failed'), true); assert.equal(U.problem('unknown'), true); assert.equal(U.problem('expired'), true);
  assert.equal(U.problem('sent'), false); assert.equal(U.problem('queued'), false);
});

test('an unsent draft survives a reload and rejects tampered values', () => {
  const draft = new U.Draft(); draft.temperature = 19; draft.mode = 0; draft.fan = 3;
  const saved = [0, 0, 0, ...draft.save()];
  assert.equal(U.Draft.restore(saved, 3).action(), 'cool_19_high');
  const invalid = U.Draft.restore([40, 9, -1], 0);
  assert.equal(invalid.temperature, 24); assert.equal(invalid.mode, 0); assert.equal(invalid.fan, 0);
  assert.equal(U.Draft.restore(null, 0).action(), 'cool_24_auto');
  assert.equal(U.Draft.restore([19, 0], 0).action(), 'cool_24_auto');
  assert.equal(U.Draft.restore(['19', 0, 0], 0).temperature, 24, 'Strings are not numbers');
});

test('extras keep the Android order and send known actions', () => {
  assert.deepEqual(U.EXTRAS.map(([label]) => label), ['풍향 고정', '스윙 바꾸기', '절전', '터보', '표시등 바꾸기']);
  assert.deepEqual(U.EXTRAS.map(([, action]) => action), ['airflow_fix', 'swing_toggle', 'economy', 'turbo', 'led_toggle']);
});

// ---- CommandPollTest ----

test('reopening the control screen does not start a second check for the same command', () => {
  const poll = new U.CommandPoll();
  assert.equal(poll.start('x', 3), true); assert.equal(poll.start('x', 3), false); assert.equal(poll.active('x', 3), true);
});
test('a newer command or screen generation supersedes the old check', () => {
  const poll = new U.CommandPoll();
  poll.start('x', 3);
  assert.equal(poll.start('y', 3), true); assert.equal(poll.active('x', 3), false);
  assert.equal(poll.start('y', 4), true); assert.equal(poll.active('y', 3), false); assert.equal(poll.active('y', 4), true);
});
test('finishing an old command keeps the newer check', () => {
  const poll = new U.CommandPoll();
  poll.start('x', 1); poll.start('y', 1);
  poll.finish('x'); assert.equal(poll.active('y', 1), true);
  poll.finish('y'); assert.equal(poll.active('y', 1), false); assert.equal(poll.start('y', 1), true);
});
test('background cancel reports whether a check must resume', () => {
  const poll = new U.CommandPoll();
  assert.equal(poll.cancel(), false);
  poll.start('x', 1);
  assert.equal(poll.cancel(), true); assert.equal(poll.active('x', 1), false); assert.equal(poll.cancel(), false);
  assert.equal(poll.start('', 1), false); assert.equal(poll.start(null, 1), false);
});
test('revoked, signed-out or missing commands stop instead of retrying', () => {
  for (const status of [401, 403, 404]) assert.equal(U.CommandPoll.retryable(status), false);
  for (const status of [0, 500, 503]) assert.equal(U.CommandPoll.retryable(status), true);
  assert.equal(U.CommandPoll.MAX_ATTEMPTS, 30);
});
test('an older reply cannot replace a newer latest command', () => {
  assert.equal(U.CommandPoll.current('x', 'x'), true); assert.equal(U.CommandPoll.current(null, 'x'), true);
  assert.equal(U.CommandPoll.current('', 'x'), true); assert.equal(U.CommandPoll.current('y', 'x'), false);
});

// ---- FanLevelsTest ----

test('bars fill up to the selected level and auto fills none', () => {
  for (let bar = 1; bar <= U.FAN_BARS; bar++) assert.equal(U.fanFilled(bar, 0), false);
  assert.equal(U.fanFilled(1, 1), true); assert.equal(U.fanFilled(2, 1), false);
  assert.equal(U.fanFilled(1, 2), true); assert.equal(U.fanFilled(2, 2), true); assert.equal(U.fanFilled(3, 2), false);
  for (let bar = 1; bar <= U.FAN_BARS; bar++) assert.equal(U.fanFilled(bar, 3), true);
  assert.equal(U.FAN_BARS, U.FANS.length - 1, 'Bars match the 약/중/강 fan values');
});
test('bars grow taller', () => {
  assert.ok(U.fanHeightQuarters(1) < U.fanHeightQuarters(2)); assert.ok(U.fanHeightQuarters(2) < U.fanHeightQuarters(3));
  assert.equal(U.fanHeightQuarters(3), 4);
});
test('dial caption shows mode and fan only while cooling', () => {
  assert.equal(U.dialCaption(0, 0), '냉방 · 바람 자동'); assert.equal(U.dialCaption(0, 3), '냉방 · 바람 강');
  assert.equal(U.dialCaption(2, 3), '온도·바람은 냉방에서 선택해요'); assert.equal(U.FAN_SHORT.length, U.FANS.length);
});

// ---- TemperatureDialTest ----

const close = (actual, expected, message) => assert.ok(Math.abs(actual - expected) < 0.001, `${message || ''} ${actual} != ${expected}`);
test('sweep grows linearly from an empty arc at 17 to the full arc at 30', () => {
  close(U.sweepFor(17), 0); close(U.sweepFor(30), 270); close(U.sweepFor(24), 7 * 270 / 13);
  close(U.sweepFor(10), 0, 'Out-of-range drafts are drawn at the nearest end'); close(U.sweepFor(35), 270);
});
test('arc ends and top map to the expected temperatures', () => {
  assert.equal(U.temperatureForAngle(135), 17); assert.equal(U.temperatureForAngle(45), 30); assert.equal(U.temperatureForAngle(405), 30);
  assert.equal(U.temperatureForAngle(270), 24, 'Straight up is the middle of the range');
  assert.equal(U.temperatureForAngle(140), 17); assert.equal(U.temperatureForAngle(135 + 270 / 13), 18);
});
test('every temperature survives a round trip through its angle', () => {
  for (let t = 17; t <= 30; t++) assert.equal(U.temperatureForAngle(U.DIAL_START + U.sweepFor(t)), t);
});
test('angles snap to whole degrees', () => {
  const step = 270 / 13;
  assert.equal(U.temperatureForAngle(135 + 3 * step + step * 0.4), 20);
  assert.equal(U.temperatureForAngle(135 + 3 * step + step * 0.6), 21);
});
test('the bottom opening snaps to the nearer end', () => {
  assert.equal(U.inGap(90), true); assert.equal(U.inGap(135), false); assert.equal(U.inGap(45), false);
  assert.equal(U.temperatureForAngle(80), 30, 'Just right of the bottom belongs to 30');
  assert.equal(U.temperatureForAngle(100), 17, 'Just left of the bottom belongs to 17');
});
test('dragging through the opening never jumps across the range', () => {
  assert.equal(U.temperatureForDrag(100, 30), 30); assert.equal(U.temperatureForDrag(80, 17), 17);
  assert.equal(U.temperatureForDrag(U.DIAL_START + U.sweepFor(26), 18), 26);
});
test('touch angles follow screen degrees', () => {
  close(U.angleOf(1, 0), 0); close(U.angleOf(0, 1), 90); close(U.angleOf(-1, 0), 180); close(U.angleOf(0, -1), 270);
  assert.equal(U.temperatureForAngle(U.angleOf(-1, 1)), 17); assert.equal(U.temperatureForAngle(U.angleOf(1, 1)), 30);
});
test('clamp keeps the supported cooling range', () => {
  assert.equal(U.clampTemperature(16), 17); assert.equal(U.clampTemperature(31), 30); assert.equal(U.clampTemperature(22), 22);
});
test('arc paths for the SVG dial', () => {
  assert.equal(U.arcPath(100, 100, 50, 135, 0), '');
  const full = U.arcPath(100, 100, 50, 135, 270);
  assert.match(full, /^M 64\.64 135\.36 A 50 50 0 1 1 135\.36 135\.36$/);
  assert.match(U.arcPath(100, 100, 50, 135, 90), / 0 0 1 /, 'A sweep under 180° uses the small arc');
  const [x, y] = U.pointOnCircle(0, 0, 10, 270); close(x, 0); close(y, -10);
});
