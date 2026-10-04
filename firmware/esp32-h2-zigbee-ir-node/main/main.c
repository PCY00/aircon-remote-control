#include <stdbool.h>
#include <stdint.h>

#include "esp_check.h"
#include "esp_log.h"
#include "esp_zigbee.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "nvs_flash.h"

#include "ir_protocol.h"
#include "ir_tx.h"

#define ZIGBEE_STORAGE_PARTITION "nvs"
#define REQUEST_QUEUE_LENGTH 4U
#define REQUEST_HISTORY_LENGTH 8U

/* ZCL strings use a byte length prefix. Keep these in sync with the
 * Zigbee2MQTT converter's fingerprint. No manufacturer code is claimed.
 */
#define MANUFACTURER_NAME "\x0A" "DIY Aircon"
#define MODEL_IDENTIFIER "\x0F" "AIRCON_H2_IR_01"

typedef struct {
    ezb_zcl_cmd_hdr_t header;
    aircon_request_t request;
} ir_job_t;

static const char *TAG = "aircon_h2_zigbee";
static QueueHandle_t ir_queue;
static uint32_t request_history[REQUEST_HISTORY_LENGTH];
static unsigned request_history_used;
static unsigned request_history_next;
static uint8_t capability = 1;

static bool request_seen(uint32_t request_id)
{
    for (unsigned i = 0; i < request_history_used; ++i) {
        if (request_history[i] == request_id) {
            return true;
        }
    }
    return false;
}

static void remember_request(uint32_t request_id)
{
    request_history[request_history_next] = request_id;
    request_history_next = (request_history_next + 1U) % REQUEST_HISTORY_LENGTH;
    if (request_history_used < REQUEST_HISTORY_LENGTH) {
        ++request_history_used;
    }
}

/* Called inside the Zigbee callback, or with the Zigbee lock from the IR
 * worker. The encoded payload remains valid for the command API call.
 */
static ezb_err_t send_result(const ezb_zcl_cmd_hdr_t *header,
                             const aircon_request_t *request, aircon_result_t result)
{
    uint8_t payload[AIRCON_RESULT_SIZE];
    aircon_encode_result(payload, request, result);
    ezb_zcl_custom_cluster_cmd_t response = {
        .cmd_ctrl = {
            .dst_addr = header->src_addr,
            .dst_ep = header->src_ep,
            .src_ep = header->dst_ep,
            .cluster_id = AIRCON_CLUSTER_ID,
            .fc = {.direction = EZB_ZCL_CMD_DIRECTION_TO_CLI,
                   .dis_default_rsp = true},
        },
        .cmd_id = AIRCON_ZCL_RESULT_COMMAND,
        .data_length = sizeof(payload),
        .data = payload,
    };
    return ezb_zcl_custom_cluster_cmd_req(&response);
}

static ezb_zcl_status_t send_default_error(const ezb_zcl_cmd_hdr_t *header,
                                            ezb_zcl_status_t status)
{
    if (EZB_ZCL_CMD_FC_IS_DIS_DEFAULT_RSP(header->fc)) {
        return status;
    }
    ezb_zcl_default_rsp_cmd_t response = {
        .cmd_ctrl = {
            .dst_addr = header->src_addr,
            .dst_ep = header->src_ep,
            .src_ep = header->dst_ep,
            .cluster_id = AIRCON_CLUSTER_ID,
            .fc = {.direction = EZB_ZCL_CMD_DIRECTION_TO_CLI,
                   .dis_default_rsp = true},
        },
        .payload = {.rsp_to_cmd = header->cmd_id,
                    .tsn = header->tsn,
                    .status_code = status},
    };
    return ezb_zcl_default_rsp_cmd_req(&response) == EZB_ERR_NONE
               ? EZB_ZCL_STATUS_SUCCESS : EZB_ZCL_STATUS_FAIL;
}

static ezb_zcl_status_t aircon_command_handler(const ezb_zcl_cmd_hdr_t *header,
                                                const uint8_t *payload,
                                                uint16_t payload_length)
{
    if (header == NULL) {
        return EZB_ZCL_STATUS_FAIL;
    }
    if (header->cluster_id != AIRCON_CLUSTER_ID || header->dst_ep != AIRCON_ENDPOINT ||
        (header->cmd_id != AIRCON_ZCL_SEND_COMMAND &&
         header->cmd_id != AIRCON_ZCL_SEND_V2_COMMAND) ||
        EZB_ZCL_CMD_FC_IS_TO_CLI_DIRECTION(header->fc) ||
        EZB_ZCL_CMD_FC_IS_MANUF_SPEC(header->fc)) {
        return send_default_error(header, EZB_ZCL_STATUS_UNSUP_CMD);
    }
    aircon_request_t request;
    if (!aircon_decode_request(payload, payload_length, &request) ||
        (header->cmd_id == AIRCON_ZCL_SEND_COMMAND &&
         request.wire_version != AIRCON_WIRE_VERSION_V1) ||
        (header->cmd_id == AIRCON_ZCL_SEND_V2_COMMAND &&
         request.wire_version != AIRCON_WIRE_VERSION_V2)) {
        return send_default_error(header, EZB_ZCL_STATUS_INVALID_FIELD);
    }
    if (request_seen(request.request_id)) {
        return send_result(header, &request, AIRCON_RESULT_DUPLICATE) == EZB_ERR_NONE
                   ? EZB_ZCL_STATUS_SUCCESS : EZB_ZCL_STATUS_FAIL;
    }
    const ir_job_t job = {.header = *header, .request = request};
    if (xQueueSend(ir_queue, &job, 0) != pdTRUE) {
        return send_result(header, &request, AIRCON_RESULT_BUSY) == EZB_ERR_NONE
                   ? EZB_ZCL_STATUS_SUCCESS : EZB_ZCL_STATUS_FAIL;
    }
    remember_request(request.request_id);
    ESP_LOGI(TAG, "IR request accepted: id=%lu command=%u", (unsigned long)request.request_id,
             request.command_id);
    return send_result(header, &request, AIRCON_RESULT_ACCEPTED) == EZB_ERR_NONE
               ? EZB_ZCL_STATUS_SUCCESS : EZB_ZCL_STATUS_FAIL;
}

static uint8_t discover_commands(bool receive, uint8_t **list)
{
    static uint8_t receive_ids[] = {AIRCON_ZCL_SEND_COMMAND, AIRCON_ZCL_SEND_V2_COMMAND};
    static uint8_t send_ids[] = {AIRCON_ZCL_RESULT_COMMAND};
    *list = receive ? receive_ids : send_ids;
    return receive ? 2 : 1;
}

static void custom_cluster_init(uint8_t endpoint)
{
    (void)endpoint;
    ezb_zcl_custom_cluster_handlers_t handlers = {
        .cluster_id = AIRCON_CLUSTER_ID,
        .cluster_role = EZB_ZCL_CLUSTER_SERVER,
        .process_cmd_cb = aircon_command_handler,
        .cmd_disc_cb = discover_commands,
    };
    ezb_zcl_custom_cluster_handlers_register(&handlers);
}

static void custom_cluster_deinit(uint8_t endpoint)
{
    (void)endpoint;
}

static esp_err_t register_aircon_endpoint(void)
{
    ezb_af_device_desc_t device = ezb_af_create_device_desc();
    ezb_zcl_basic_cluster_server_config_t basic_config = {
        .zcl_version = EZB_ZCL_BASIC_ZCL_VERSION_DEFAULT_VALUE,
        .power_source = EZB_ZCL_BASIC_POWER_SOURCE_DEFAULT_VALUE,
    };
    ezb_zcl_cluster_desc_t basic = ezb_zcl_basic_create_cluster_desc(&basic_config,
                                                                       EZB_ZCL_CLUSTER_SERVER);
    ezb_zcl_basic_cluster_desc_add_attr(basic, EZB_ZCL_ATTR_BASIC_MANUFACTURER_NAME_ID,
                                        (void *)MANUFACTURER_NAME);
    ezb_zcl_basic_cluster_desc_add_attr(basic, EZB_ZCL_ATTR_BASIC_MODEL_IDENTIFIER_ID,
                                        (void *)MODEL_IDENTIFIER);
    ezb_zcl_identify_cluster_server_config_t identify_config = {
        .identify_time = EZB_ZCL_IDENTIFY_IDENTIFY_TIME_DEFAULT_VALUE,
    };
    ezb_zcl_cluster_desc_t identify = ezb_zcl_identify_create_cluster_desc(&identify_config,
                                                                             EZB_ZCL_CLUSTER_SERVER);
    ezb_zcl_custom_cluster_config_t custom_config = {
        .cluster_id = AIRCON_CLUSTER_ID,
        .init_func = custom_cluster_init,
        .deinit_func = custom_cluster_deinit,
    };
    ezb_zcl_cluster_desc_t custom = ezb_zcl_custom_create_cluster_desc(&custom_config,
                                                                         EZB_ZCL_CLUSTER_SERVER);
    ezb_zcl_custom_cluster_desc_add_attr(custom, 0x0000, EZB_ZCL_ATTR_TYPE_UINT8,
                                         EZB_ZCL_ATTR_ACCESS_READ, &capability);
    ezb_af_ep_config_t endpoint_config = {
        .ep_id = AIRCON_ENDPOINT,
        .app_profile_id = EZB_AF_HA_PROFILE_ID,
        .app_device_id = 0x0000,
        .app_device_version = 1,
    };
    ezb_af_ep_desc_t endpoint = ezb_af_create_endpoint_desc(&endpoint_config);
    ESP_RETURN_ON_ERROR(ezb_af_endpoint_add_cluster_desc(endpoint, basic), TAG, "add Basic");
    ESP_RETURN_ON_ERROR(ezb_af_endpoint_add_cluster_desc(endpoint, identify), TAG, "add Identify");
    ESP_RETURN_ON_ERROR(ezb_af_endpoint_add_cluster_desc(endpoint, custom), TAG, "add IR cluster");
    ESP_RETURN_ON_ERROR(ezb_af_device_add_endpoint_desc(device, endpoint), TAG, "add endpoint");
    return ezb_af_device_desc_register(device);
}

static bool zigbee_signal_handler(const ezb_app_signal_t *signal)
{
    const ezb_app_signal_type_t type = ezb_app_signal_get_type(signal);
    switch (type) {
    case EZB_ZDO_SIGNAL_SKIP_STARTUP:
        ezb_bdb_start_top_level_commissioning(EZB_BDB_MODE_INITIALIZATION);
        break;
    case EZB_BDB_SIGNAL_DEVICE_FIRST_START:
    case EZB_BDB_SIGNAL_DEVICE_REBOOT: {
        const ezb_bdb_comm_status_t status = *(ezb_bdb_comm_status_t *)ezb_app_signal_get_params(signal);
        if (status == EZB_BDB_STATUS_SUCCESS && ezb_bdb_is_factory_new()) {
            ESP_LOGI(TAG, "First start; requesting Zigbee network steering");
            ezb_bdb_start_top_level_commissioning(EZB_BDB_MODE_NETWORK_STEERING);
        } else if (status == EZB_BDB_STATUS_SUCCESS) {
            ESP_LOGI(TAG, "Rejoined existing Zigbee network");
        } else {
            ESP_LOGW(TAG, "Zigbee initialization failed: 0x%02x; reboot to retry", status);
        }
        break;
    }
    case EZB_BDB_SIGNAL_STEERING: {
        const ezb_bdb_comm_status_t status = *(ezb_bdb_comm_status_t *)ezb_app_signal_get_params(signal);
        if (status == EZB_BDB_STATUS_SUCCESS) {
            ESP_LOGI(TAG, "Zigbee joined; IR remains idle until a valid command arrives");
        } else {
            ESP_LOGW(TAG, "Zigbee join failed: 0x%02x; reboot to retry", status);
        }
        break;
    }
    default:
        break;
    }
    return true;
}

static void ir_worker(void *unused)
{
    (void)unused;
    ir_job_t job;
    while (xQueueReceive(ir_queue, &job, portMAX_DELAY) == pdTRUE) {
        const esp_err_t result = aircon_ir_send(&job.request);
        const aircon_result_t status = result == ESP_OK ? AIRCON_RESULT_SENT : AIRCON_RESULT_FAILED;
        ESP_LOGI(TAG, "IR request id=%lu TX %s (appliance state not measured)",
                 (unsigned long)job.request.request_id, result == ESP_OK ? "complete" : "failed");
        esp_zigbee_lock_acquire(portMAX_DELAY);
        const ezb_err_t response = send_result(&job.header, &job.request, status);
        esp_zigbee_lock_release();
        if (response != EZB_ERR_NONE) {
            ESP_LOGW(TAG, "Could not send Zigbee TX result: 0x%x", response);
        }
    }
    vTaskDelete(NULL);
}

static void zigbee_task(void *unused)
{
    (void)unused;
    esp_zigbee_config_t config = {
        .device_config = {
            .device_type = EZB_NWK_DEVICE_TYPE_END_DEVICE,
            .install_code_policy = false,
            .zed_config = {.ed_timeout = EZB_NWK_ED_TIMEOUT_64MIN, .keep_alive = 4000},
        },
        .platform_config = {
            .storage_partition_name = ZIGBEE_STORAGE_PARTITION,
            .radio_config = {.radio_mode = ESP_ZIGBEE_RADIO_MODE_NATIVE},
        },
    };
    ESP_ERROR_CHECK(esp_zigbee_init(&config));
    ESP_ERROR_CHECK(ezb_app_signal_add_handler(zigbee_signal_handler));
    ESP_ERROR_CHECK(register_aircon_endpoint());
    ESP_ERROR_CHECK(esp_zigbee_start(false));
    esp_zigbee_launch_mainloop();
    vTaskDelete(NULL);
}

void app_main(void)
{
    /* Never erase NVS automatically: it contains the Zigbee network identity. */
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(aircon_ir_init());
    ir_queue = xQueueCreate(REQUEST_QUEUE_LENGTH, sizeof(ir_job_t));
    ESP_ERROR_CHECK(ir_queue == NULL ? ESP_ERR_NO_MEM : ESP_OK);
    ESP_ERROR_CHECK(xTaskCreate(ir_worker, "ir_worker", 4096, NULL, 4, NULL) == pdPASS
                        ? ESP_OK : ESP_ERR_NO_MEM);
    ESP_ERROR_CHECK(xTaskCreate(zigbee_task, "zigbee_main", 6144, NULL, 5, NULL) == pdPASS
                        ? ESP_OK : ESP_ERR_NO_MEM);
    ESP_LOGI(TAG, "GPIO5 IR ready; waiting for Zigbee; no automatic IR on boot");
}
