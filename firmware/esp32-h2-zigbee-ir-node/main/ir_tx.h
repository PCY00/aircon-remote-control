#pragma once

#include "esp_err.h"
#include "ir_protocol.h"

esp_err_t aircon_ir_init(void);
esp_err_t aircon_ir_send(const aircon_request_t *request);
