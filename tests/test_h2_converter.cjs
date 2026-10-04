const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = readFileSync(
  path.join(__dirname, '../deploy/zigbee/zigbee2mqtt/external_converters/aircon-h2-ir.mjs'),
  'utf8'
).replace(/^import .*;$/gm, '').replace('export default {', 'globalThis.converter = {');
const context = vm.createContext({
  Zcl: { DataType: { UINT8: 0 } },
  deviceAddCustomCluster: (_name, config) => config
});
vm.runInContext(source, context);
const converter = context.converter;

function endpoint() {
  const calls = [];
  const meta = {
    device: {
      getEndpoint: (number) => {
        assert.equal(number, 10);
        return { command: async (...args) => { calls.push(args); } };
      }
    }
  };
  return { calls, meta };
}

test('POWER_OFF remains on the legacy six-byte command', async () => {
  const { calls, meta } = endpoint();
  await converter.toZigbee[0].convertSet(null, 'ir_request',
    { command: 'POWER_OFF', request_id: 0x123456 }, meta);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][1], 'send');
  assert.equal(calls[0][2].version, 1);
  assert.equal(calls[0][2].command, 1);
  assert.equal(calls[0][2].request0, 0x56);
  assert.equal(calls[0][2].request1, 0x34);
  assert.equal(calls[0][2].request2, 0x12);
  assert.equal(Object.keys(calls[0][2]).length, 6);
});

test('cooling and captured fixed commands use version two', async () => {
  const { calls, meta } = endpoint();
  await converter.toZigbee[0].convertSet(null, 'ir_request',
    { command: 'COOL_STATE', request_id: 5, temperature_c: 24, fan: 'high' }, meta);
  assert.equal(calls[0][1], 'sendV2');
  assert.equal(calls[0][2].version, 2);
  assert.equal(calls[0][2].command, 2);
  assert.equal(calls[0][2].temperature, 24);
  assert.equal(calls[0][2].fan, 3);
  await converter.toZigbee[0].convertSet(null, 'ir_request',
    { command: 'SWING_TOGGLE', request_id: 6 }, meta);
  assert.equal(calls[1][1], 'sendV2');
  assert.equal(calls[1][2].command, 10);
  assert.equal(calls[1][2].temperature, 0);
  assert.equal(calls[1][2].fan, 0);
});

test('invalid settings are rejected before Zigbee transmission', async () => {
  const { calls, meta } = endpoint();
  for (const value of [
    { command: 'POWER_ON', request_id: 1 },
    { command: 'COOL_STATE', request_id: 1, temperature_c: 16, fan: 'high' },
    { command: 'COOL_STATE', request_id: 1, temperature_c: 24, fan: 'invalid' },
    { command: 'POWER_OFF', request_id: 0 },
    { command: 'POWER_OFF', request_id: 1, temperature_c: 24 },
  ]) {
    await assert.rejects(converter.toZigbee[0].convertSet(null, 'ir_request', value, meta));
  }
  assert.equal(calls.length, 0);
});

test('result decoding keeps command and request identity', () => {
  const decoded = converter.fromZigbee[0].convert(null, {
    endpoint: { ID: 10 },
    data: {
      version: 2, profile: 1, command: 2,
      request0: 0x56, request1: 0x34, request2: 0x12, status: 1
    }
  });
  assert.equal(decoded.ir_result.command, 'COOL_STATE');
  assert.equal(decoded.ir_result.request_id, 0x123456);
  assert.equal(decoded.ir_result.status, 'sent');
  const mismatched = converter.fromZigbee[0].convert(null, {
    endpoint: { ID: 10 },
    data: {
      version: 1, profile: 1, command: 2,
      request0: 1, request1: 0, request2: 0, status: 1
    }
  });
  assert.equal(Object.keys(mismatched).length, 0);
});
