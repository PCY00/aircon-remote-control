idf_component_register(SRCS "main.c" "ir_tx.c"
                       INCLUDE_DIRS "."
                       REQUIRES driver esp_driver_rmt esp_driver_gpio nvs_flash
                                espressif__esp-zigbee-lib)
