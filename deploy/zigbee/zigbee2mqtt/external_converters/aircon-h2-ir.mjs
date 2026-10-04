import {Zcl} from 'zigbee-herdsman';
import {deviceAddCustomCluster} from 'zigbee-herdsman-converters/lib/modernExtend';

const CLUSTER = 'airconIr';
const ENDPOINT = 10;
const MAX_REQUEST_ID = 0xffffff;
const commands = new Map([
    ['POWER_OFF', 1], ['COOL_STATE', 2], ['MODE_AUTO', 3],
    ['MODE_DRY', 4], ['MODE_FAN_ONLY', 5], ['ECONOMY', 6],
    ['TURBO', 7], ['LED_TOGGLE', 8], ['AIRFLOW_FIX', 9],
    ['SWING_TOGGLE', 10],
]);
const fans = new Map([['auto', 0], ['low', 1], ['medium', 2], ['high', 3]]);
const commandNames = new Map([...commands].map(([name, id]) => [id, name]));

// This private cluster does not claim an allocated Zigbee manufacturer code.
const irCluster = deviceAddCustomCluster(CLUSTER, {
    name: CLUSTER,
    ID: 0xff00,
    attributes: {
        capability: {name: 'capability', ID: 0x0000, type: Zcl.DataType.UINT8},
    },
    commands: {
        send: {
            name: 'send',
            ID: 0x00,
            parameters: [
                {name: 'version', type: Zcl.DataType.UINT8},
                {name: 'profile', type: Zcl.DataType.UINT8},
                {name: 'command', type: Zcl.DataType.UINT8},
                {name: 'request0', type: Zcl.DataType.UINT8},
                {name: 'request1', type: Zcl.DataType.UINT8},
                {name: 'request2', type: Zcl.DataType.UINT8},
            ],
        },
        sendV2: {
            name: 'sendV2',
            ID: 0x02,
            parameters: [
                {name: 'version', type: Zcl.DataType.UINT8},
                {name: 'profile', type: Zcl.DataType.UINT8},
                {name: 'command', type: Zcl.DataType.UINT8},
                {name: 'temperature', type: Zcl.DataType.UINT8},
                {name: 'fan', type: Zcl.DataType.UINT8},
                {name: 'request0', type: Zcl.DataType.UINT8},
                {name: 'request1', type: Zcl.DataType.UINT8},
                {name: 'request2', type: Zcl.DataType.UINT8},
            ],
        },
    },
    commandsResponse: {
        result: {
            name: 'result',
            ID: 0x01,
            parameters: [
                {name: 'version', type: Zcl.DataType.UINT8},
                {name: 'profile', type: Zcl.DataType.UINT8},
                {name: 'command', type: Zcl.DataType.UINT8},
                {name: 'request0', type: Zcl.DataType.UINT8},
                {name: 'request1', type: Zcl.DataType.UINT8},
                {name: 'request2', type: Zcl.DataType.UINT8},
                {name: 'status', type: Zcl.DataType.UINT8},
            ],
        },
    },
});

const statuses = ['accepted', 'sent', 'failed', 'duplicate', 'busy'];

function parseRequest(value) {
    let request = value;
    if (typeof request === 'string') {
        try {
            request = JSON.parse(request);
        } catch {
            throw new Error('ir_request must be a JSON object');
        }
    }
    if (request === null || typeof request !== 'object' || Array.isArray(request) ||
        !commands.has(request.command) ||
        !Number.isInteger(request.request_id) ||
        request.request_id < 1 || request.request_id > MAX_REQUEST_ID) {
        throw new Error('ir_request requires a supported command and request_id:1..16777215');
    }
    if (request.command === 'COOL_STATE') {
        if (!Number.isInteger(request.temperature_c) || request.temperature_c < 17 ||
            request.temperature_c > 30 || !fans.has(request.fan)) {
            throw new Error('COOL_STATE requires temperature_c:17..30 and fan:auto|low|medium|high');
        }
    } else if (request.temperature_c !== undefined || request.fan !== undefined) {
        throw new Error('temperature_c and fan are only allowed for COOL_STATE');
    }
    return request;
}

const toZigbee = {
    key: ['ir_request'],
    convertSet: async (entity, key, value, meta) => {
        const request = parseRequest(value);
        const endpoint = meta.device.getEndpoint(ENDPOINT);
        if (!endpoint) {
            throw new Error(`IR endpoint ${ENDPOINT} is missing`);
        }
        const payload = {
            version: request.command === 'POWER_OFF' ? 1 : 2,
            profile: 1,
            command: commands.get(request.command),
            request0: request.request_id & 0xff,
            request1: (request.request_id >>> 8) & 0xff,
            request2: (request.request_id >>> 16) & 0xff,
        };
        if (request.command !== 'POWER_OFF') {
            payload.temperature = request.command === 'COOL_STATE' ? request.temperature_c : 0;
            payload.fan = request.command === 'COOL_STATE' ? fans.get(request.fan) : 0;
        }
        await endpoint.command(CLUSTER, request.command === 'POWER_OFF' ? 'send' : 'sendV2',
            payload, {disableDefaultResponse: true});
        // A successful Zigbee send is NOT proof that IR was sent or the A/C
        // changed state. Wait for the later 'sent' result frame.
    },
};

const fromZigbee = {
    cluster: CLUSTER,
    type: ['commandResult'],
    convert: (model, msg) => {
        const data = msg.data;
        const bytes = [data.version, data.profile, data.command,
            data.request0, data.request1, data.request2, data.status];
        if (msg.endpoint.ID !== ENDPOINT || bytes.some((v) => !Number.isInteger(v) || v < 0 || v > 255) ||
            ![1, 2].includes(data.version) || data.profile !== 1 ||
            !commandNames.has(data.command) ||
            (data.version === 1 && data.command !== 1)) {
            return {};
        }
        return {
            ir_result: {
                command: commandNames.get(data.command),
                request_id: data.request0 | (data.request1 << 8) | (data.request2 << 16),
                status: statuses[data.status] ?? 'unknown',
            },
        };
    },
};

export default {
    zigbeeModel: ['AIRCON_H2_IR_01'],
    model: 'AIRCON_H2_IR_01',
    vendor: 'DIY Aircon',
    description: 'ESP32-H2 Zigbee IR bridge (Carrier CS-A061GS captured commands)',
    extend: [irCluster],
    fromZigbee: [fromZigbee],
    toZigbee: [toZigbee],
};
