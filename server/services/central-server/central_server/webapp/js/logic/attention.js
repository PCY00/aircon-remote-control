// "지금 확인할 것": things that need a look now, computed from the device list, the records and the
// aircon control status. Battery and 응답 없음 exist only here. Mirrors Attention.java.

import { DeviceText } from './device.js';
import { AUTOMATION, DEVICE, SECURITY } from './alerts.js';
import { actionLabel } from './aircon.js';
import { belongsTo } from './timeline.js';

export const DANGER = 'danger', WARNING = 'warning', NEUTRAL = 'neutral';
/** A failed or unconfirmed aircon command stays here this long. */
export const COMMAND_SECONDS = 600;

function item(key, tone, title, detail, deviceId, category) {
  return Object.freeze({ key, tone, title, detail, deviceId, category });
}

export function compute(inventory, events, control, now) {
  const danger = [], warning = [], neutral = [];
  const devices = inventory ? inventory.devices : [];
  events = events || [];
  for (const device of devices) {
    if (device.type !== 'door_sensor' || device.contact() !== 'open') continue;
    const since = openedAt(device, events);
    const detail = since === null ? '' : now - since < 60 ? '방금 열렸어요' : DeviceText.duration(now - since) + '째';
    danger.push(item('door:' + device.id, DANGER, DeviceText.subject(device.name) + ' 열려 있어요', detail, device.id, SECURITY));
  }
  if (control && control.latest) {
    const command = control.latest;
    if ((command.state === 'failed' || command.state === 'unknown') && command.time() > 0 && now - command.time() <= COMMAND_SECONDS) {
      const device = inventory ? inventory.find(command.deviceId) : null;
      let name = device ? device.name : control.deviceName(command.deviceId);
      if (name === null) name = '에어컨';
      danger.push(item('command:' + command.id, DANGER, name + ' 명령이 전달되지 않았어요',
        actionLabel(command.action) + ' · ' + DeviceText.ago(now - command.time()), command.deviceId, DEVICE));
    }
  }
  const warningEvent = events.find((event) => event.kind.startsWith('automation.warning_'));
  if (warningEvent && warningEvent.kind === 'automation.warning_triggered')
    danger.push(item('automation:' + warningEvent.id, DANGER, '자동화 경고가 켜져 있어요',
      warningEvent.receivedAt > 0 ? DeviceText.ago(now - warningEvent.receivedAt) : '', null, AUTOMATION));
  for (const device of devices) if (device.batteryLow()) {
    const percent = device.batteryPercent();
    warning.push(item('battery:' + device.id, WARNING, device.name, percent === null ? '배터리 부족' : '배터리 ' + percent + '%', device.id, DEVICE));
  }
  const hub = !!inventory && inventory.hubProblem(now);
  if (hub) neutral.push(item('hub', NEUTRAL, 'Pi와 연결이 끊겼어요',
    inventory.updatedAt === null ? '' : '마지막 연결 ' + DeviceText.ago(now - inventory.updatedAt), null, DEVICE));
  // With the hub down every battery sensor goes quiet together; the hub item already says why.
  if (!hub) for (const device of devices) if (device.stale(now))
    neutral.push(item('stale:' + device.id, NEUTRAL, device.name, DeviceText.NO_RESPONSE + ' · ' + DeviceText.duration(now - device.reportedAt), device.id, DEVICE));
  return [...danger, ...warning, ...neutral];
}
/** When the door opened: its latest door record if that says open, else the device's report time. */
export function openedAt(device, events) {
  for (const event of events) {
    if (!event.door() || !belongsTo(event, device)) continue;
    if (event.doorState() === 'open' && event.receivedAt > 0) return event.receivedAt;
    break;
  }
  return device.reportedAt;
}
/** The latest door record time of a door, for "닫힘 · 3분 전"; null when there is none. */
export function changedAt(device, events) {
  if (device.type !== 'door_sensor') return null;
  for (const event of events || []) if (event.door() && belongsTo(event, device) && event.receivedAt > 0) return event.receivedAt;
  return null;
}
export function filter(items, category) {
  if (!category || category === 'all') return items;
  return items.filter((entry) => entry.category === category);
}
/** Icon for a 지금 확인할 것 row. */
export function iconOf(entry) {
  if (entry.key.startsWith('door:')) return 'door';
  if (entry.key.startsWith('command:')) return 'aircon';
  if (entry.key.startsWith('automation:')) return 'warning';
  if (entry.key.startsWith('battery:')) return 'battery';
  return 'wifi_off';
}
