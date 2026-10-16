// The 알림 tab's record list: day headers (오늘 / 어제 / M월 d일) and rows where consecutive records of the
// same device and kind within a day collapse into one ("현관문 열림·닫힘 6번"). Mirrors Timeline.java.
// `zone` is an IANA time zone for tests; undefined means the phone's own zone.

import { DeviceText } from './device.js';
import { AUTOMATION, DEVICE, ENVIRONMENT, FAMILY, REPORT, SAFETY, SECURITY } from './alerts.js';

const formatters = new Map();
function formatter(zone) {
  const key = zone || '';
  if (!formatters.has(key)) {
    formatters.set(key, new Intl.DateTimeFormat('en-US', {
      timeZone: zone, year: 'numeric', month: 'numeric', day: 'numeric', hour: 'numeric', minute: 'numeric', hourCycle: 'h23',
    }));
  }
  return formatters.get(key);
}
/** {year, month, day, hour, minute} of epoch seconds in a zone. */
export function parts(seconds, zone) {
  const result = {};
  for (const part of formatter(zone).formatToParts(new Date(Math.trunc(seconds * 1000)))) {
    if (['year', 'month', 'day', 'hour', 'minute'].includes(part.type)) result[part.type] = Number(part.value);
  }
  if (result.hour === 24) result.hour = 0;
  return result;
}
function dayNumber(p) { return Math.floor(Date.UTC(p.year, p.month - 1, p.day) / 86400000); }
export function sameDay(a, b, zone) { return dayNumber(parts(a, zone)) === dayNumber(parts(b, zone)); }

export class Row {
  /** Newest first; a single record when nothing collapsed. */
  constructor(events) { this.events = Object.freeze([...events]); }
  newest() { return this.events[0]; }
  oldest() { return this.events[this.events.length - 1]; }
  count() { return this.events.length; }
  /** Stable within a load, for remembering which rows are expanded. */
  key() { return this.newest().id + ':' + this.newest().kind + ':' + this.count(); }
}

export function dayLabel(seconds, now, zone) {
  if (seconds <= 0) return '시각 정보 없음';
  const date = parts(seconds, zone), today = parts(now, zone);
  const difference = dayNumber(today) - dayNumber(date);
  if (difference === 0) return '오늘';
  if (difference === 1) return '어제';
  if (date.year !== today.year) return date.year + '년 ' + date.month + '월 ' + date.day + '일';
  return date.month + '월 ' + date.day + '일';
}
export function clock(seconds, zone) {
  if (seconds <= 0) return '';
  const p = parts(seconds, zone);
  return String(p.hour).padStart(2, '0') + ':' + String(p.minute).padStart(2, '0');
}
/** Door open/close records are one family; warning triggered/resolved are another. */
export function family(event) {
  if (event.door()) return 'door';
  if (event.kind.startsWith('automation.warning_')) return 'automation.warning';
  return event.kind;
}
export function sameRun(a, b) {
  return (a.deviceId || '') === (b.deviceId || '') && family(a) === family(b);
}
export function build(events, names, zone, now) {
  const days = [];
  let currentDay = null, day = null, run = null;
  for (const event of events) {
    const date = dayNumber(parts(event.receivedAt, zone));
    if (day === null || date !== currentDay) {
      if (run !== null) day.rows.push(new Row(run));
      run = null; currentDay = date;
      day = { label: dayLabel(event.receivedAt, now, zone), rows: [] };
      days.push(day);
    }
    if (run !== null && sameRun(run[0], event)) run.push(event);
    else { if (run !== null) day.rows.push(new Row(run)); run = [event]; }
  }
  if (run !== null) day.rows.push(new Row(run));
  return days;
}
/** A record belongs to a device by payload.device_id; older records without it match by kind. */
export function belongsTo(event, device) {
  if (event.deviceId !== null) return event.deviceId === device.id;
  switch (device.type) {
    case 'door_sensor': return event.door();
    case 'climate_sensor': return event.climate();
    case 'motion_sensor': return event.kind === 'sensor.motion_detected';
    case 'leak_sensor': return event.kind === 'sensor.leak_detected';
    case 'smoke_sensor': return event.kind === 'sensor.smoke_detected';
    default: return false;
  }
}
export function nameOf(event, names) {
  if (event.deviceId === null || !names) return null;
  const name = names instanceof Map ? names.get(event.deviceId) : names[event.deviceId];
  return name === undefined ? null : name;
}
export function title(event, name) {
  const kind = event.kind;
  if (kind === 'hub.connection_test') return '기기 연결 시험';
  if (event.door()) return (name === null ? '문' : name) + ' ' + (event.doorState() === 'open' ? '열림' : '닫힘');
  if (event.climate()) {
    const values = DeviceText.climate(event.number('temperature_c'), event.number('humidity_percent'));
    const base = name === null ? '온습도 측정' : name;
    return values === null ? base : base + ' · ' + values;
  }
  if (kind === 'sensor.motion_detected') return name === null ? '움직임 감지' : name + ' 움직임 감지';
  if (kind === 'sensor.leak_detected') return name === null ? '누수 감지' : name + ' 누수 감지';
  if (kind === 'sensor.smoke_detected') return name === null ? '연기 감지' : name + ' 연기 감지';
  if (kind === 'sensor.climate_threshold') return name === null ? '온습도 기준 알림' : name + ' 온습도 기준 알림';
  if (kind === 'automation.warning_triggered') return '자동화 경고 발생';
  if (kind === 'automation.warning_resolved') return '자동화 경고 해제';
  if (kind.startsWith('automation.')) return '자동화 실행';
  if (kind.startsWith('device.')) return name === null ? '기기 알림' : name + ' 기기 알림';
  if (kind.startsWith('family.')) return '가족 활동';
  if (kind.startsWith('safety.')) return name === null ? '안전 알림' : name + ' 안전 알림';
  if (kind.startsWith('environment.')) return name === null ? '환경 알림' : name + ' 환경 알림';
  return '집의 새 기록';
}
/** "현관문 열림·닫힘 6번", "거실 온습도 측정 12번", or the single record's title. */
export function rowTitle(row, names) {
  const first = row.newest(), name = nameOf(first, names);
  if (row.count() === 1) return title(first, name);
  if (first.door()) {
    let open = false, closed = false;
    for (const event of row.events) { if (event.doorState() === 'open') open = true; else closed = true; }
    const states = open && closed ? '열림·닫힘' : open ? '열림' : '닫힘';
    return (name === null ? '문' : name) + ' ' + states + ' ' + row.count() + '번';
  }
  if (first.climate()) return (name === null ? '온습도' : name) + ' 측정 ' + row.count() + '번';
  if (family(first) === 'automation.warning') {
    let triggered = false, resolved = false;
    for (const event of row.events) { if (event.kind.endsWith('triggered')) triggered = true; else resolved = true; }
    return '자동화 경고 ' + (triggered && resolved ? '발생·해제' : triggered ? '발생' : '해제') + ' ' + row.count() + '번';
  }
  return title(first, name) + ' ' + row.count() + '번';
}
/** "14:05" for one record, "13:10–14:05" for a collapsed row. */
export function rowTime(row, zone) {
  const newest = clock(row.newest().receivedAt, zone);
  if (row.count() === 1) return newest;
  return clock(row.oldest().receivedAt, zone) + '–' + newest;
}
export function icon(alertCategory) {
  switch (alertCategory) {
    case SAFETY: return 'droplet';
    case SECURITY: return 'door';
    case DEVICE: return 'hub';
    case ENVIRONMENT: return 'thermometer';
    case REPORT: return 'thermometer';
    case AUTOMATION: return 'warning';
    case FAMILY: return 'family';
    default: return 'hub';
  }
}
