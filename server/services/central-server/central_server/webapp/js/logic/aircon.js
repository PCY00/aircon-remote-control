// Aircon control texts, the unsent draft, fan bars, the 270° dial math and the result check.
// Mirrors AirconUi, FanLevels, TemperatureDial (pure part) and CommandPoll of the Android app.
// A transmitter acknowledgement never establishes the appliance's measured power state.

export const MODES = Object.freeze(['냉방', '자동', '제습', '송풍']);
export const MODE_ACTIONS = Object.freeze(['', 'mode_auto', 'mode_dry', 'mode_fan_only']);
export const MODE_ICONS = Object.freeze(['snowflake', 'auto', 'droplet', 'wind']);
export const FANS = Object.freeze(['자동', '약풍', '중풍', '강풍']);
export const FAN_VALUES = Object.freeze(['auto', 'low', 'medium', 'high']);
/** One-shot extras: each opens the same confirmation dialog. */
export const EXTRAS = Object.freeze([
  ['풍향 고정', 'airflow_fix'], ['스윙 바꾸기', 'swing_toggle'], ['절전', 'economy'], ['터보', 'turbo'], ['표시등 바꾸기', 'led_toggle'],
]);

export function coolingAction(temperature, fan) {
  if (!Number.isInteger(temperature) || temperature < 17 || temperature > 30 || !Number.isInteger(fan) || fan < 0 || fan >= FAN_VALUES.length)
    throw new RangeError('Unsupported cooling setting');
  return 'cool_' + temperature + '_' + FAN_VALUES[fan];
}

export class Draft {
  constructor() { this.temperature = 24; this.mode = 0; this.fan = 0; }
  action() { return this.mode === 0 ? coolingAction(this.temperature, this.fan) : MODE_ACTIONS[this.mode]; }
  save() { return [this.temperature, this.mode, this.fan]; }
  /** Restores an unsent draft; values outside the supported range fall back to the defaults. */
  static restore(values, offset = 0) {
    const draft = new Draft();
    if (!Array.isArray(values) || offset < 0 || values.length < offset + 3) return draft;
    const [temperature, mode, fan] = values.slice(offset, offset + 3);
    if (Number.isInteger(temperature) && temperature >= 17 && temperature <= 30) draft.temperature = temperature;
    if (Number.isInteger(mode) && mode >= 0 && mode < MODES.length) draft.mode = mode;
    if (Number.isInteger(fan) && fan >= 0 && fan < FANS.length) draft.fan = fan;
    return draft;
  }
}

export function actionLabel(action) {
  if (action === 'cool_on') return '냉방 24°C · 바람 자동';
  if (typeof action === 'string' && action.startsWith('cool_')) {
    const pieces = action.split('_');
    if (pieces.length === 3) {
      const index = FAN_VALUES.indexOf(pieces[2]);
      if (index >= 0) return '냉방 ' + pieces[1] + '°C · ' + FANS[index];
    }
  }
  switch (action) {
    case 'power_off': return '전원 끄기';
    case 'mode_auto': return '자동 운전';
    case 'mode_dry': return '제습 운전';
    case 'mode_fan_only': return '송풍 운전';
    case 'economy': return '절전';
    case 'turbo': return '터보';
    case 'led_toggle': return '표시등 바꾸기';
    case 'airflow_fix': return '풍향 고정';
    case 'swing_toggle': return '스윙 동작 바꾸기';
    default: return '에어컨 명령';
  }
}
/** Compact action for the one-line status: "냉방 24°", "끄기", "제습". */
export function shortLabel(action) {
  if (action === 'cool_on') return '냉방 24°';
  if (typeof action === 'string' && action.startsWith('cool_')) {
    const pieces = action.split('_');
    if (pieces.length === 3) return '냉방 ' + pieces[1] + '°';
  }
  switch (action) {
    case 'power_off': return '끄기';
    case 'mode_auto': return '자동';
    case 'mode_dry': return '제습';
    case 'mode_fan_only': return '송풍';
    default: return actionLabel(action);
  }
}
/** One word for the command state in the status line. */
export function stateLabel(state) {
  switch (state) {
    case 'queued': case 'dispatched': return '전달 중';
    case 'sent': return '전달됨';
    case 'failed': return '실패';
    case 'expired': return '만료';
    case 'cancelled': return '취소됨';
    case 'unknown': return '결과 모름';
    default: return '';
  }
}
/** States that did not reach the aircon (or may not have). */
export function problem(state) { return ['failed', 'unknown', 'expired', 'cancelled'].includes(state); }
export function confirmation(action) {
  let result = actionLabel(action) + ' 신호를 보내요.';
  if (action === 'swing_toggle' || action === 'led_toggle')
    result += '\n현재 상태를 읽지 못해요. 누를 때마다 동작이 바뀌므로 에어컨 반응을 확인해 주세요.';
  if (action === 'economy')
    result += '\n지금 냉방 온도는 그대로 두고 바람만 자동으로 바뀌어요. 냉방 중에만 작동하고, 다른 모드에서는 실패로 표시돼요.';
  return result;
}
export function pending(state) { return state === 'queued' || state === 'dispatched'; }
export function canSend(allowed, online, state) { return !!allowed && !!online && !pending(state); }
export function description(state, action) {
  if (state === 'failed' && action === 'economy') return '절전을 보내지 못했어요. 절전은 냉방 중에만 작동해요. 운전 모드와 Pi 연결을 확인해 주세요.';
  switch (state) {
    case 'queued': return 'Pi에 명령을 전달하고 있어요…';
    case 'dispatched': return 'IR 송신 결과를 기다리고 있어요…';
    case 'sent': return 'IR 신호를 보냈어요. 실제 작동은 에어컨에서 확인해 주세요.';
    case 'failed': return '명령을 보내지 못했어요. Pi와 IR 장치 연결을 확인해 주세요.';
    case 'expired': return '시간이 지나 실행하지 않았어요. 연결 상태를 확인해 주세요.';
    case 'cancelled': return '권한이나 기기 연결이 바뀌어 실행하지 않았어요.';
    case 'unknown': return '실행 결과를 받지 못했어요. 다시 누르기 전에 에어컨을 확인해 주세요.';
    default: return '아직 앱에서 보낸 명령이 없어요.';
  }
}
export const LOST_RESULT = '연결이 끊겨 결과를 확인하지 못했어요. 다시 누르기 전에 에어컨을 확인해 주세요.';
export const NOT_SENDABLE = '지금은 보낼 수 없어요. 연결 상태와 최근 요청을 확인해 주세요.';
export const NOT_RESENT = ' 명령은 자동으로 다시 보내지 않아요.';

// ---- Fan bars ----

export const FAN_SHORT = Object.freeze(['자동', '약', '중', '강']);
/** Bars 1–3 stand for 약풍·중풍·강풍; index 0 (자동) is the separate pill. */
export const FAN_BARS = 3;
/** A bar is filled up to the selected level; 자동 fills none. */
export function fanFilled(bar, fan) { return fan > 0 && bar >= 1 && bar <= fan; }
/** Relative bar height in quarters of the tallest bar: 약 2/4, 중 3/4, 강 4/4. */
export function fanHeightQuarters(bar) { return Math.max(1, Math.min(FAN_BARS, bar)) + 1; }
export function dialCaption(mode, fan) {
  if (mode !== 0) return '온도·바람은 냉방에서 선택해요';
  const index = fan >= 0 && fan < FAN_SHORT.length ? fan : 0;
  return MODES[0] + ' · 바람 ' + FAN_SHORT[index];
}

// ---- 270° dial (SVG degrees: 0° is 3 o'clock, angles grow clockwise, the opening is at the bottom) ----

export const DIAL_MIN = 17, DIAL_MAX = 30, DIAL_START = 135, DIAL_SWEEP = 270;
export function clampTemperature(temperature) { return Math.max(DIAL_MIN, Math.min(DIAL_MAX, temperature)); }
/** Progress sweep in degrees; 17° is an empty arc and 30° the full 270°. */
export function sweepFor(temperature) { return (clampTemperature(temperature) - DIAL_MIN) * DIAL_SWEEP / (DIAL_MAX - DIAL_MIN); }
export function normalize(degrees) { const d = degrees % 360; return d < 0 ? d + 360 : d; }
/** Touch angle around the centre (0° = right, 90° = down). */
export function angleOf(dx, dy) { return normalize(Math.atan2(dy, dx) * 180 / Math.PI); }
export function inGap(degrees) { return normalize(degrees - DIAL_START) > DIAL_SWEEP; }
/** Snaps an angle to the nearest whole degree Celsius; inside the bottom opening the nearer end wins. */
export function temperatureForAngle(degrees) {
  const along = normalize(degrees - DIAL_START);
  if (along > DIAL_SWEEP) return along - DIAL_SWEEP < (360 - DIAL_SWEEP) / 2 ? DIAL_MAX : DIAL_MIN;
  return clampTemperature(DIAL_MIN + Math.round(along / DIAL_SWEEP * (DIAL_MAX - DIAL_MIN)));
}
/** While dragging, sliding through the opening keeps the end it came from instead of jumping 17↔30. */
export function temperatureForDrag(degrees, current) {
  if (inGap(degrees)) return current * 2 >= DIAL_MIN + DIAL_MAX ? DIAL_MAX : DIAL_MIN;
  return temperatureForAngle(degrees);
}
export function pointOnCircle(cx, cy, r, degrees) {
  const radians = degrees * Math.PI / 180;
  return [cx + r * Math.cos(radians), cy + r * Math.sin(radians)];
}
/** SVG path of a clockwise arc; an empty sweep gives an empty string. */
export function arcPath(cx, cy, r, start, sweep) {
  if (!(sweep > 0)) return '';
  const s = Math.min(sweep, 359.99);
  const [x1, y1] = pointOnCircle(cx, cy, r, start), [x2, y2] = pointOnCircle(cx, cy, r, start + s);
  const f = (n) => Math.round(n * 100) / 100;
  return `M ${f(x1)} ${f(y1)} A ${f(r)} ${f(r)} 0 ${s > 180 ? 1 : 0} 1 ${f(x2)} ${f(y2)}`;
}

// ---- Result check ----

/** One result check per aircon command; a superseded or abandoned check never updates the screen. */
export class CommandPoll {
  static MAX_ATTEMPTS = 30;
  static INTERVAL_MS = 2000;
  constructor() { this.id = null; this.epoch = 0; }
  /** Returns false when this command already has a live check in the same screen generation. */
  start(command, generation) {
    if (!command || (command === this.id && this.epoch === generation)) return false;
    this.id = command; this.epoch = generation; return true;
  }
  active(command, generation) { return !!command && command === this.id && this.epoch === generation; }
  finish(command) { if (command && command === this.id) this.id = null; }
  /** Drops the live check and reports whether one was running, so it can resume from the server later. */
  cancel() { const running = this.id !== null; this.id = null; return running; }
  /** Sign-in, permission and missing-command failures do not recover by asking again. */
  static retryable(status) { return status !== 401 && status !== 403 && status !== 404; }
  /** A reply for an older command must not replace a newer latest_command. */
  static current(latest, reply) { return !latest || latest === reply; }
}
