// Devices of GET /v1/homes/<home>/devices, records of .../events and the aircon control status, with
// the Korean texts for tiles, chips and room headers. Mirrors Device, DeviceCategory, DeviceText,
// AppEvent, ControlStatus and Inventory of the Android family app 0.6.2. No DOM access.

import { clean, flag, list, map, number, text } from './plain.js';
import { categoryOf } from './alerts.js';

const TOKEN = /^[a-z][a-z0-9_]{0,31}$/;
const ID = /^[A-Za-z0-9_.:-]{1,64}$/;

// ---- Categories ----

export const HVAC = 'hvac', LIGHT = 'light', SECURITY = 'security', ENVIRONMENT = 'environment',
  SAFETY = 'safety', POWER = 'power', OTHER = 'other';

export const DeviceCategory = Object.freeze({
  KEYS: Object.freeze([HVAC, LIGHT, SECURITY, ENVIRONMENT, SAFETY, POWER, OTHER]),
  of(type) {
    switch (type) {
      case 'air_conditioner': return HVAC;
      case 'light': return LIGHT;
      case 'door_sensor': case 'motion_sensor': return SECURITY;
      case 'climate_sensor': return ENVIRONMENT;
      case 'leak_sensor': case 'smoke_sensor': return SAFETY;
      case 'plug': return POWER;
      default: return OTHER;
    }
  },
  label(category) {
    switch (category) {
      case HVAC: return '냉난방';
      case LIGHT: return '조명';
      case SECURITY: return '보안';
      case ENVIRONMENT: return '환경';
      case SAFETY: return '안전';
      case POWER: return '전력';
      default: return '기타';
    }
  },
  icon(category) {
    switch (category) {
      case HVAC: return 'aircon';
      case LIGHT: return 'bulb';
      case SECURITY: return 'door';
      case ENVIRONMENT: return 'thermometer';
      case SAFETY: return 'droplet';
      case POWER: return 'plug';
      default: return 'hub';
    }
  },
  typeIcon(type) {
    switch (type) {
      case 'air_conditioner': return 'aircon';
      case 'light': return 'bulb';
      case 'door_sensor': return 'door';
      case 'motion_sensor': return 'motion';
      case 'climate_sensor': return 'thermometer';
      case 'leak_sensor': return 'droplet';
      case 'smoke_sensor': return 'warning';
      case 'plug': return 'plug';
      default: return 'hub';
    }
  },
  /** Name used when a device arrives without one. */
  typeLabel(type) {
    switch (type) {
      case 'air_conditioner': return '에어컨';
      case 'light': return '전등';
      case 'door_sensor': return '문';
      case 'motion_sensor': return '움직임 센서';
      case 'climate_sensor': return '온습도';
      case 'leak_sensor': return '누수 센서';
      case 'smoke_sensor': return '연기 센서';
      case 'plug': return '플러그';
      default: return '기기';
    }
  },
  /** Categories that have at least one device, in chip order. */
  present(devices) { return DeviceCategory.KEYS.filter((key) => devices.some((device) => device.category() === key)); },
  members(devices, category) { return devices.filter((device) => device.category() === category); },
});

// ---- Device ----

export class Device {
  static STALE_SECONDS = 6 * 3600;
  static LOW_BATTERY = 20;

  constructor(id, name, room, type, capabilities, state, reportedAt, controllable) {
    this.id = id;
    this.type = type == null ? '' : type;
    this.name = name == null || name === '' ? DeviceCategory.typeLabel(this.type) : name;
    this.room = room == null ? '' : room;
    this.capabilities = Object.freeze([...capabilities]);
    this.state = Object.freeze({ ...state });
    /** Epoch seconds of the device's last report, or null when it never reported. */
    this.reportedAt = reportedAt == null ? null : reportedAt;
    this.controllable = !!controllable;
    Object.freeze(this);
  }
  /** Returns null for an entry without a usable id; unknown types, blocks and state keys are kept. */
  static from(raw) {
    if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) return null;
    const id = text(raw.id);
    if (id === null || !ID.test(id)) return null;
    let type = text(raw.type, '');
    if (!TOKEN.test(type)) type = 'unknown';
    const capabilities = [];
    for (const item of list(raw.capabilities)) {
      const capability = text(item);
      if (capability !== null && TOKEN.test(capability) && !capabilities.includes(capability) && capabilities.length < 16)
        capabilities.push(capability);
    }
    const state = {};
    let size = 0;
    for (const [key, item] of Object.entries(map(raw.state))) {
      if (size >= 16 || !TOKEN.test(key)) continue;
      if (item === null || typeof item === 'boolean') { state[key] = item; size++; }
      else if (typeof item === 'number') { if (number(item) !== null) { state[key] = item; size++; } }
      else if (typeof item === 'string') { state[key] = clean(item, 40); size++; }
    }
    let reported = number(raw.reported_at);
    if (reported !== null && reported <= 0) reported = null;
    return new Device(id, clean(text(raw.name), 80), clean(text(raw.room), 40), type, capabilities, state, reported,
      flag(raw.controllable));
  }
  static list(raw) {
    const result = [], seen = new Set();
    for (const item of list(raw)) {
      const device = Device.from(item);
      if (device && !seen.has(device.id)) { seen.add(device.id); result.push(device); }
    }
    return result;
  }
  category() { return DeviceCategory.of(this.type); }
  aircon() { return this.type === 'air_conditioner'; }
  has(key) { return Object.prototype.hasOwnProperty.call(this.state, key); }
  number(key) { return number(this.state[key]); }
  text(key) { return text(this.state[key]); }
  /** true/false for bool or on/off/open/closed style strings, null when unknown. */
  flag(key) {
    const value = this.state[key];
    if (typeof value === 'boolean') return value;
    if (typeof value === 'string') {
      const lower = value.toLowerCase();
      if (['on', 'true', 'open', 'detected'].includes(lower)) return true;
      if (['off', 'false', 'closed', 'clear'].includes(lower)) return false;
    }
    if (typeof value === 'number') return value !== 0;
    return null;
  }
  /** Inferred power for aircons/lights/plugs: a known mode without a power key also means on. */
  power() {
    const power = this.flag('power');
    if (power !== null) return power;
    return this.text('mode') !== null ? true : null;
  }
  on() { return this.power() === true; }
  /** "open", "closed" or null. */
  contact() {
    const value = this.state.contact;
    if (value === 'open' || value === true) return 'open';
    if (value === 'closed' || value === false) return 'closed';
    return null;
  }
  hasBattery() { return this.capabilities.includes('battery') || this.has('battery_percent') || this.has('battery_low'); }
  batteryPercent() {
    const percent = this.number('battery_percent');
    return percent === null ? null : Math.round(Math.max(0, Math.min(100, percent)));
  }
  batteryLow() {
    if (this.state.battery_low === true) return true;
    const percent = this.batteryPercent();
    return percent !== null && percent <= Device.LOW_BATTERY;
  }
  /** Only battery sensors go quiet when they stop reporting; mains devices are judged by the hub status. */
  stale(now) { return this.hasBattery() && this.reportedAt !== null && now - this.reportedAt > Device.STALE_SECONDS; }
  /** "거실 에어컨" in 거실 shows as "에어컨"; a word that merely begins with the room ("현관문" in 현관) stays whole. */
  shortName() {
    if (this.room === '' || !this.name.startsWith(this.room + ' ')) return this.name;
    const rest = this.name.slice(this.room.length).trim();
    return rest === '' ? this.name : rest;
  }
}

// ---- Texts ----

const NO_ROOM = '공간 미지정', NO_RESPONSE = '응답 없음', UNKNOWN = '상태 모름';

function roundTenth(value) { return Math.round(value * 10) / 10; }

export const DeviceText = Object.freeze({
  NO_ROOM, NO_RESPONSE, UNKNOWN,
  /** 24 → "24", 25.14 → "25.1". */
  number(value) {
    const rounded = roundTenth(value);
    if (Math.abs(rounded - Math.round(rounded)) < 1e-9) return String(Math.round(rounded));
    return rounded.toFixed(1);
  },
  /** Seconds → "N분", "N시간", "N일" (at least one minute). */
  duration(seconds) {
    const minutes = Math.max(1, Math.floor(Math.max(0, seconds) / 60));
    if (minutes < 60) return minutes + '분';
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return hours + '시간';
    return Math.floor(hours / 24) + '일';
  },
  /** Elapsed seconds → "방금", "3분 전", "2시간 전", "4일 전". */
  ago(seconds) { return seconds < 60 ? '방금' : DeviceText.duration(seconds) + ' 전'; },
  /** Subject particle: "현관문" → "현관문이", "문 센서" → "문 센서가". */
  subject(word) {
    if (!word) return '';
    const last = word.charCodeAt(word.length - 1);
    let batchim;
    if (last >= 0xAC00 && last <= 0xD7A3) batchim = (last - 0xAC00) % 28 !== 0;
    else if (last >= 48 && last <= 57) batchim = '013678'.includes(String.fromCharCode(last));
    else if (last < 128 && /[A-Za-z]/.test(String.fromCharCode(last))) batchim = 'lmnLMN'.includes(String.fromCharCode(last));
    else batchim = false;
    return word + (batchim ? '이' : '가');
  },
  climate(temperature, humidity) {
    if (temperature !== null && humidity !== null) return DeviceText.number(temperature) + '° · ' + DeviceText.number(humidity) + '%';
    if (temperature !== null) return DeviceText.number(temperature) + '°';
    if (humidity !== null) return DeviceText.number(humidity) + '%';
    return null;
  },
  roomLabel(room) { return room == null || room === '' ? NO_ROOM : room; },
  modeLabel(mode) {
    switch (mode) {
      case 'cool': return '냉방';
      case 'heat': return '난방';
      case 'auto': return '자동';
      case 'dry': return '제습';
      case 'fan': case 'fan_only': return '송풍';
      default: return '켜짐';
    }
  },
  /** A state value as text: on/off for booleans, trimmed numbers, strings as they are. */
  value(value) {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'boolean') return value ? '켜짐' : '꺼짐';
    const n = number(value);
    if (n !== null) return DeviceText.number(n);
    return String(value);
  },
  aircon(device) {
    const power = device.power();
    if (power === false) return '꺼짐';
    if (power === null) return UNKNOWN;
    const mode = device.text('mode'), setpoint = device.number('setpoint_c');
    const label = DeviceText.modeLabel(mode);
    if (setpoint !== null && (mode === 'cool' || mode === 'heat')) return label + ' ' + DeviceText.number(setpoint) + '°';
    return label;
  },
  /** One line under a tile. `changedAt` is the latest door record of this device when known. */
  summary(device, now, changedAt) {
    switch (device.type) {
      case 'air_conditioner': return DeviceText.aircon(device);
      case 'door_sensor': {
        const contact = device.contact();
        if (contact === null) return UNKNOWN;
        const value = contact === 'open' ? '열림' : '닫힘';
        const since = changedAt != null ? changedAt : device.reportedAt;
        return since === null ? value : value + ' · ' + DeviceText.ago(now - since);
      }
      case 'climate_sensor': {
        const value = DeviceText.climate(device.number('temperature_c'), device.number('humidity_percent'));
        return value === null ? '측정값 없음' : value;
      }
      case 'light': {
        const power = device.power();
        if (power === null) return UNKNOWN;
        if (!power) return '꺼짐';
        const brightness = device.number('brightness_percent');
        return brightness === null ? '켜짐' : '켜짐 · ' + DeviceText.number(brightness) + '%';
      }
      case 'plug': {
        const power = device.power();
        if (power === null) return UNKNOWN;
        if (!power) return '꺼짐';
        const watts = device.number('power_w');
        return watts === null ? '켜짐' : '켜짐 · ' + DeviceText.number(watts) + 'W';
      }
      case 'motion_sensor': {
        const motion = device.flag('motion');
        return motion === null ? UNKNOWN : motion ? '움직임 감지' : '움직임 없음';
      }
      case 'leak_sensor': {
        const leak = device.flag('leak');
        return leak === null ? UNKNOWN : leak ? '누수 감지' : '이상 없음';
      }
      case 'smoke_sensor': {
        const smoke = device.flag('smoke');
        return smoke === null ? UNKNOWN : smoke ? '연기 감지' : '이상 없음';
      }
      default: {
        const values = Object.values(device.state);
        return values.length ? DeviceText.value(values[0]) : UNKNOWN;
      }
    }
  },
  /** The tile line, with 응답 없음 replacing a value that may be hours old. */
  tile(device, now, changedAt) { return device.stale(now) ? NO_RESPONSE : DeviceText.summary(device, now, changedAt); },
  /** "26.2° · 52%" of the first climate sensor in a room that has values, else null. */
  roomClimate(devices) {
    for (const device of devices) if (device.type === 'climate_sensor') {
      const value = DeviceText.climate(device.number('temperature_c'), device.number('humidity_percent'));
      if (value !== null) return value;
    }
    return null;
  },
  /** Rooms in order of first appearance (a Map of room → devices); the empty room is 공간 미지정. */
  rooms(devices) {
    const rooms = new Map();
    for (const device of devices) {
      if (!rooms.has(device.room)) rooms.set(device.room, []);
      rooms.get(device.room).push(device);
    }
    return rooms;
  },
  /** Chip summary per category: "냉방 24°"/"꺼짐", "문 닫힘"/"문 1개 열림", average "25.6° · 50%", "2개 켜짐". */
  category(category, devices) {
    const members = DeviceCategory.members(devices, category);
    switch (category) {
      case HVAC: {
        const on = []; let off = false;
        for (const device of members) { const power = device.power(); if (power === true) on.push(device); else if (power === false) off = true; }
        if (on.length === 1) return DeviceText.aircon(on[0]);
        if (on.length > 1) return on.length + '대 켜짐';
        return off ? '꺼짐' : UNKNOWN;
      }
      case SECURITY: {
        let doors = 0, open = 0, known = 0, motion = null;
        for (const device of members) {
          if (device.type === 'door_sensor') {
            doors++; const contact = device.contact();
            if (contact !== null) known++;
            if (contact === 'open') open++;
          } else if (device.type === 'motion_sensor') {
            const value = device.flag('motion');
            if (value !== null) motion = motion === true || value;
          }
        }
        if (open > 0) return '문 ' + open + '개 열림';
        if (doors > 0) return known > 0 ? '문 닫힘' : UNKNOWN;
        if (motion !== null) return motion ? '움직임 감지' : '움직임 없음';
        return members.length + '개';
      }
      case ENVIRONMENT: {
        let temperature = 0, humidity = 0, temperatures = 0, humidities = 0;
        for (const device of members) {
          const t = device.number('temperature_c'), h = device.number('humidity_percent');
          if (t !== null) { temperature += t; temperatures++; }
          if (h !== null) { humidity += h; humidities++; }
        }
        const value = DeviceText.climate(temperatures === 0 ? null : temperature / temperatures, humidities === 0 ? null : humidity / humidities);
        return value === null ? '측정값 없음' : value;
      }
      case LIGHT: case POWER: {
        const on = members.filter((device) => device.on()).length;
        return on > 0 ? on + '개 켜짐' : '모두 꺼짐';
      }
      case SAFETY: {
        if (members.some((device) => device.flag('leak') === true)) return '누수 감지';
        if (members.some((device) => device.flag('smoke') === true)) return '연기 감지';
        return '이상 없음';
      }
      default: return members.length + '개';
    }
  },
});

// ---- Records ----

export class AppEvent {
  constructor(id, kind, receivedAt, payload) {
    this.id = id;
    this.kind = kind == null ? '' : kind;
    /** Epoch seconds the server received it; 0 when missing. */
    this.receivedAt = receivedAt;
    this.payload = Object.freeze({ ...payload });
    const device = text(payload.device_id);
    /** payload.device_id (0.7 Pi agent); null on older records. */
    this.deviceId = device === null || device === '' ? null : device;
    Object.freeze(this);
  }
  static from(raw) {
    if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) return null;
    const kind = text(raw.kind);
    if (kind === null || kind === '') return null;
    const id = number(raw.id), received = number(raw.received_at);
    return new AppEvent(id === null ? 0 : Math.trunc(id), kind, received === null || received < 0 ? 0 : received, map(raw.payload));
  }
  /** Newest first, whatever order the server used. */
  static list(raw) {
    const result = [];
    for (const item of list(raw)) { const event = AppEvent.from(item); if (event) result.push(event); }
    result.sort((a, b) => (a.receivedAt !== b.receivedAt ? b.receivedAt - a.receivedAt : b.id - a.id));
    return result;
  }
  text(key) { return text(this.payload[key]); }
  number(key) { return number(this.payload[key]); }
  alertCategory() { return categoryOf(this.kind); }
  door() { return this.kind === 'sensor.door_changed' || this.kind === 'sensor.open' || this.kind === 'sensor.closed'; }
  /** "open"/"closed" for door records (the kind decides for sensor.open/closed). */
  doorState() {
    if (this.kind === 'sensor.open') return 'open';
    if (this.kind === 'sensor.closed') return 'closed';
    const state = this.text('state');
    return state === 'open' ? 'open' : state === 'closed' ? 'closed' : null;
  }
  climate() { return this.kind === 'sensor.climate_report'; }
}

// ---- Aircon control status ----

export class ControlStatus {
  constructor(online, canControl, devices, latest) {
    this.online = online; this.canControl = canControl;
    /** Controllable aircons as {id, name}. */
    this.devices = devices;
    this.latest = latest;
  }
  static from(raw) {
    const value = map(raw);
    const devices = [];
    for (const item of list(value.devices)) {
      const device = map(item), id = text(device.id);
      if (id !== null && id !== '') devices.push({ id, name: clean(text(device.name, ''), 80) });
    }
    let latest = null;
    const command = map(value.latest_command);
    if (Object.keys(command).length) {
      const created = number(command.created_at), updated = number(command.updated_at);
      latest = {
        id: text(command.id, ''), deviceId: text(command.device_id, ''), action: text(command.action, ''),
        state: text(command.state, ''), createdAt: created === null ? 0 : created, updatedAt: updated === null ? 0 : updated,
        /** When the command last changed state, for "N분 전". */
        time() { return Math.max(this.createdAt, this.updatedAt); },
      };
    }
    return new ControlStatus(flag(value.online), flag(value.can_control), devices, latest);
  }
  deviceName(id) {
    const device = this.devices.find((item) => item.id === id);
    return device && device.name !== '' ? device.name : null;
  }
  has(id) { return this.devices.some((item) => item.id === id); }
  /** The latest command, only when it was for this device. */
  latestFor(id) { return this.latest !== null && this.latest.deviceId === id ? this.latest : null; }
}

// ---- Inventory ----

export const AIRCON_CAPABILITIES = Object.freeze(['power', 'setpoint', 'mode', 'fan', 'actions']);

export class Inventory {
  /** A list the Pi has not refreshed for this long means the hub is not reporting. */
  static HUB_STALE_SECONDS = 600;
  static FALLBACK_DOOR = 'legacy-door';
  static FALLBACK_CLIMATE = 'legacy-climate';

  constructor(devices, updatedAt, hubOnline, fallback, hubSeen) {
    this.devices = Object.freeze([...devices]);
    /** When the Pi last sent the list (epoch seconds), null when it never did. */
    this.updatedAt = updatedAt == null ? null : updatedAt;
    /** Pi connection as the server sees it; null when unknown. */
    this.hubOnline = typeof hubOnline === 'boolean' ? hubOnline : null;
    this.fallback = !!fallback;
    this.hubSeen = !!hubSeen;
  }
  static from(raw) {
    const value = map(raw);
    return new Inventory(Device.list(value.devices), number(value.updated_at),
      typeof value.hub_online === 'boolean' ? value.hub_online : null, false, true);
  }
  /** A 0.7 server whose Pi never sent a list answers devices [] and updated_at null. */
  neverReported() { return this.updatedAt === null && this.devices.length === 0; }
  /** The list the screens use: the server's when it has one, otherwise the fallback. */
  static effective(server, control, events) {
    if (server && !server.neverReported()) return server;
    return Inventory.fallback(control, events);
  }
  /** Older server or silent Pi: the control list's aircons plus the latest door and climate records. */
  static fallback(control, events) {
    const devices = [];
    if (control) for (const aircon of control.devices) {
      const latest = control.latestFor(aircon.id);
      const state = latest && latest.state === 'sent' ? Inventory.inferred(latest.action) : null;
      devices.push(new Device(aircon.id, aircon.name, '', 'air_conditioner', AIRCON_CAPABILITIES, state || {}, null, true));
    }
    let door = null, climate = null;
    for (const event of events || []) {
      if (door === null && event.door() && event.doorState() !== null) door = event;
      if (climate === null && event.climate()) climate = event;
    }
    if (door) {
      devices.push(new Device(door.deviceId === null ? Inventory.FALLBACK_DOOR : door.deviceId, '', '', 'door_sensor',
        ['contact'], { contact: door.doorState() }, door.receivedAt > 0 ? door.receivedAt : null, false));
    }
    if (climate) {
      const state = {}, capabilities = [];
      const temperature = climate.number('temperature_c'), humidity = climate.number('humidity_percent');
      if (temperature !== null) { state.temperature_c = temperature; capabilities.push('temperature'); }
      if (humidity !== null) { state.humidity_percent = humidity; capabilities.push('humidity'); }
      devices.push(new Device(climate.deviceId === null ? Inventory.FALLBACK_CLIMATE : climate.deviceId, '', '', 'climate_sensor',
        capabilities, state, climate.receivedAt > 0 ? climate.receivedAt : null, false));
    }
    const seen = !!control && (control.devices.length > 0 || (events || []).length > 0);
    return new Inventory(devices, null, control ? control.online : null, true, seen);
  }
  /** What a successfully sent command tells about the aircon, marked inferred like the Pi's own guess. */
  static inferred(action) {
    if (typeof action !== 'string') return null;
    let state;
    if (action === 'power_off') state = { power: false };
    else if (action === 'cool_on') state = { power: true, mode: 'cool', setpoint_c: 24, fan: 'auto' };
    else if (action.startsWith('cool_')) {
      const pieces = action.split('_');
      if (pieces.length !== 3 || !/^-?\d+$/.test(pieces[1])) return null;
      state = { power: true, mode: 'cool', setpoint_c: Number(pieces[1]), fan: pieces[2] };
    } else if (action === 'mode_auto') state = { power: true, mode: 'auto' };
    else if (action === 'mode_dry') state = { power: true, mode: 'dry' };
    else if (action === 'mode_fan_only') state = { power: true, mode: 'fan_only' };
    else return null;
    state.inferred = true;
    return state;
  }
  /** Pi offline, or its list not refreshed for 10 minutes. A fallback list only knows the control status. */
  hubProblem(now) {
    if (this.fallback) return this.hubSeen && this.hubOnline === false;
    return this.hubOnline === false || (this.updatedAt !== null && now - this.updatedAt > Inventory.HUB_STALE_SECONDS);
  }
  find(id) { return id == null ? null : this.devices.find((device) => device.id === id) || null; }
  /** Device id → name, for record titles. */
  names() {
    const names = new Map();
    for (const device of this.devices) names.set(device.id, device.name);
    return names;
  }
}
