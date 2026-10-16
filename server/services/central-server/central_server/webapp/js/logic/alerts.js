// Alert categories x levels (decision 0019), the quiet-hours range and the generic notification
// texts. Mirrors AlertLevels.java; the web additions are the quiet-hours request body helpers.

export const SAFETY = 'safety', SECURITY = 'security', DEVICE = 'device', ENVIRONMENT = 'environment',
  REPORT = 'report', AUTOMATION = 'automation', FAMILY = 'family', OTHER = 'other';
/** The seven categories a phone chooses a level for, in settings order. */
export const CATEGORIES = Object.freeze([SAFETY, SECURITY, DEVICE, ENVIRONMENT, REPORT, AUTOMATION, FAMILY]);
/** Filter chip order in the 알림 tab. */
export const FILTERS = Object.freeze([...CATEGORIES, OTHER]);
export const URGENT = 'urgent', ALERT = 'alert', QUIET = 'quiet', OFF = 'off';
export const LEVELS = Object.freeze([URGENT, ALERT, QUIET, OFF]);
export const INTERVALS = Object.freeze([1, 5, 15, 60]);
export const DEFAULT_INTERVAL = 5;
/** Default do-not-disturb range in minutes of the day: 23:00–07:00. */
export const QUIET_START = 23 * 60, QUIET_END = 7 * 60;
/** Every web push shows this title; names and values never travel in a push. */
export const NOTIFICATION_TITLE = '우리 집 알림';

export function label(category) {
  switch (category) {
    case SAFETY: return '안전';
    case SECURITY: return '보안';
    case DEVICE: return '기기';
    case ENVIRONMENT: return '환경';
    case REPORT: return '정기 보고';
    case AUTOMATION: return '자동화';
    case FAMILY: return '가족';
    default: return '기타';
  }
}
/** What each category covers, shown under its name in settings. */
export function caption(category) {
  switch (category) {
    case SAFETY: return '누수·연기';
    case SECURITY: return '문·움직임';
    case DEVICE: return '조작 실패·응답 없음·배터리';
    case ENVIRONMENT: return '온습도 기준';
    case REPORT: return '온습도 값';
    case AUTOMATION: return '자동화 실행·경고';
    case FAMILY: return '누가 조작함';
    default: return '연결 시험 등';
  }
}
export function levelLabel(level) {
  switch (level) {
    case URGENT: return '긴급';
    case ALERT: return '알림';
    case QUIET: return '조용히';
    default: return '끔';
  }
}
export function levelMeaning(level) {
  switch (level) {
    case URGENT: return '방해 금지 시간에도 소리로 알려요';
    case ALERT: return '소리로 알려요. 방해 금지 시간엔 조용히 보여요';
    case QUIET: return '휴대폰 알림 없이 알림 탭에만 남겨요';
    default: return '알림 탭의 ‘전체’에서도 숨겨요';
  }
}
export function defaultLevel(category) {
  switch (category) {
    case SAFETY: return URGENT;
    case SECURITY: case DEVICE: case AUTOMATION: return ALERT;
    case ENVIRONMENT: case FAMILY: return QUIET;
    case REPORT: return OFF;
    default: return ALERT;
  }
}
export function defaults() {
  const levels = {};
  for (const category of CATEGORIES) levels[category] = defaultLevel(category);
  return levels;
}
/** Safety can never be silenced; the other categories take all four levels; other is not configurable. */
export function allowed(category) {
  if (category === SAFETY) return [URGENT, ALERT];
  return CATEGORIES.includes(category) ? [...LEVELS] : [];
}
export function valid(category, level) { return allowed(category).includes(level); }
export function configurable(category) { return allowed(category).length > 0; }
export function validInterval(minutes) { return INTERVALS.includes(minutes); }
/** Saved levels with every unknown or invalid value replaced by the default: all seven, every time. */
export function normalizeLevels(saved) {
  const levels = {};
  for (const category of CATEGORIES) {
    const value = saved && typeof saved === 'object' ? saved[category] : undefined;
    levels[category] = valid(category, value) ? value : defaultLevel(category);
  }
  return levels;
}
export function normalizeInterval(minutes) { return validInterval(minutes) ? minutes : DEFAULT_INTERVAL; }

/** Event kind → alert category, exactly as the contract's table (unknown kinds are other). */
export function categoryOf(kind) {
  const k = typeof kind === 'string' ? kind : '';
  if (k.startsWith('safety.') || k === 'sensor.leak_detected' || k === 'sensor.smoke_detected') return SAFETY;
  if (k === 'sensor.door_changed' || k === 'sensor.open' || k === 'sensor.closed' || k === 'sensor.motion_detected') return SECURITY;
  if (k.startsWith('device.')) return DEVICE;
  if (k.startsWith('environment.') || k === 'sensor.climate_threshold') return ENVIRONMENT;
  if (k === 'sensor.climate_report') return REPORT;
  if (k.startsWith('automation.')) return AUTOMATION;
  if (k.startsWith('family.')) return FAMILY;
  return OTHER;
}
/** Legacy FCM category (door/climate/warning/other) → alert category. */
export function fromLegacy(legacy) {
  if (legacy === 'door') return SECURITY;
  if (legacy === 'climate') return REPORT;
  if (legacy === 'warning') return AUTOMATION;
  return OTHER;
}
/** FCM data from a 0.7+ server carries alert_category; an older server only the legacy category. */
export function incomingCategory(alertCategory, legacy) {
  if (typeof alertCategory === 'string' && alertCategory !== '') return FILTERS.includes(alertCategory) ? alertCategory : OTHER;
  return fromLegacy(legacy);
}
/** The server pushes only these two levels to the phone. */
export function delivers(level) { return level === URGENT || level === ALERT; }
/** 정기 보고 간격 matters only while reports reach the phone. */
export function reportIntervalVisible(reportLevel) { return delivers(reportLevel); }
/** 끔 hides a category from the 알림 tab's 전체 list; its own chip still shows it. */
export function showsInAll(category, level) { return !configurable(category) || level !== OFF; }

/** Minutes of the day; start == end means no quiet range. Ranges may cross midnight (23:00–07:00). */
export function inQuietHours(start, end, now) {
  if (start === end) return false;
  if (start < end) return now >= start && now < end;
  return now >= start || now < end;
}
/** Generic per-category text: a push never carries device names or values; details are read in the app. */
export function body(category, test) {
  if (test) return '시험 알림이 도착했어요.';
  switch (category) {
    case SAFETY: return '안전 알림이 왔어요. 앱에서 바로 확인해 주세요.';
    case SECURITY: return '문이나 움직임에 변화가 있어요. 앱에서 확인해 주세요.';
    case DEVICE: return '기기 상태를 확인해 주세요.';
    case ENVIRONMENT: return '온습도가 기준을 넘었어요. 앱에서 확인해 주세요.';
    case REPORT: return '새 온습도 측정값이 도착했어요.';
    case AUTOMATION: return '자동화 소식이 있어요. 앱에서 확인해 주세요.';
    case FAMILY: return '가족이 기기를 조작했어요.';
    default: return '새 기록이 도착했어요. 앱에서 확인해 주세요.';
  }
}
/** Notifications of one category replace each other, like the Android group. */
export function tag(category) { return 'family-' + (FILTERS.includes(category) ? category : OTHER); }

// ---- Quiet hours (web: enforced by the server, so the phone sends its range and UTC offset) ----

/** "07:30" → 450; anything else → null. */
export function parseClock(value) {
  const match = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(typeof value === 'string' ? value : '');
  return match ? Number(match[1]) * 60 + Number(match[2]) : null;
}
/** 450 → "07:30". */
export function formatClock(minutes) {
  const m = ((Math.trunc(minutes) % 1440) + 1440) % 1440;
  return String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0');
}
/** Minutes east of UTC for the phone's clock at `date` (Seoul: 540). */
export function utcOffsetMinutes(date) {
  const offset = -date.getTimezoneOffset();
  return Math.max(-14 * 60, Math.min(14 * 60, offset === 0 ? 0 : offset));
}
export function validQuiet(quiet) {
  return !!quiet && typeof quiet.enabled === 'boolean'
    && Number.isInteger(quiet.start) && quiet.start >= 0 && quiet.start < 1440
    && Number.isInteger(quiet.end) && quiet.end >= 0 && quiet.end < 1440;
}
export function defaultQuiet() { return { enabled: false, start: QUIET_START, end: QUIET_END }; }
/** Body of PUT /v1/installations/<id>/quiet-hours. */
export function quietHoursBody(secret, quiet, date) {
  const value = validQuiet(quiet) ? quiet : defaultQuiet();
  return {
    secret, enabled: value.enabled, start_minute: value.start, end_minute: value.end,
    utc_offset_minutes: utcOffsetMinutes(date),
  };
}
