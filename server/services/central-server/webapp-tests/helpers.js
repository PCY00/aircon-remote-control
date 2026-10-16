// TestMaps.java of the Android app: plain values like a parsed server reply.
import { AppEvent, Device, Inventory } from '../central_server/webapp/js/logic/device.js';

export const DOOR = '0123456789abcdef0123456789abcdef', CLIMATE = 'fedcba9876543210fedcba9876543210',
  AIRCON = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
export const NOW = 1_800_000_000;

export function device(id, name, room, type, capabilities, state, reportedAt) {
  return { id, name, room, type, capabilities, state, reported_at: reportedAt, controllable: type === 'air_conditioner' };
}
export function door(contact, battery, reportedAt) {
  const state = { contact };
  if (battery !== null && battery !== undefined) state.battery_percent = battery;
  return Device.from(device(DOOR, '현관문', '현관', 'door_sensor', ['contact', 'battery'], state, reportedAt));
}
export function climate(temperature, humidity, reportedAt) {
  return Device.from(device(CLIMATE, '거실 온습도', '거실', 'climate_sensor', ['temperature', 'humidity', 'battery'],
    { temperature_c: temperature, humidity_percent: humidity, battery_percent: 80 }, reportedAt));
}
export function aircon(state) {
  return Device.from(device(AIRCON, '거실 에어컨', '거실', 'air_conditioner', ['power', 'setpoint', 'mode', 'fan', 'actions'], state, null));
}
export function event(id, kind, receivedAt, payload) {
  return AppEvent.from({ id, kind, received_at: receivedAt, payload });
}
export function inventory(updatedAt, online, ...devices) {
  return new Inventory(devices, updatedAt, online, false, true);
}
