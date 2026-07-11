#include <inttypes.h>
#include <stdio.h>

#include "esp_chip_info.h"
#include "esp_flash.h"
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "supermini_smoke";

void app_main(void)
{
    esp_chip_info_t chip_info;
    uint32_t flash_size = 0;

    esp_chip_info(&chip_info);
    ESP_ERROR_CHECK(esp_flash_get_size(NULL, &flash_size));
    ESP_LOGI(TAG, "ESP32-C3 revision %d, flash %" PRIu32 " bytes", chip_info.revision, flash_size);

    uint32_t heartbeat = 0;
    while (true) {
        ESP_LOGI(TAG, "heartbeat=%" PRIu32, heartbeat++);
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
