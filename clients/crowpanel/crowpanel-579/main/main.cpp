#include "EPD_Init.h"
#include "display_download.h"
#include "wifi_station.h"

#include "driver/gpio.h"
#include "esp_check.h"
#include "esp_log.h"
#include "esp_sleep.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

namespace {
constexpr gpio_num_t DISPLAY_POWER = GPIO_NUM_7;
constexpr char TAG[] = "crowpanel_epd";
constexpr uint64_t DEFAULT_NEXT_CHECK_SECONDS = 30 * 60;
uint8_t ImageBW[EPD_W * EPD_H / 8];
char FrameId[CROWPANEL_FRAME_ID_SIZE];

void SleepUntilNextCheck(uint64_t seconds)
{
    ESP_LOGI(TAG, "Sleeping for %llu seconds",
             static_cast<unsigned long long>(seconds));
    ESP_ERROR_CHECK(esp_sleep_enable_timer_wakeup(seconds * 1000000ULL));
    esp_deep_sleep_start();
}
}

extern "C" void app_main(void)
{
    gpio_config_t power_config = {};
    power_config.pin_bit_mask = 1ULL << DISPLAY_POWER;
    power_config.mode = GPIO_MODE_OUTPUT;
    power_config.pull_up_en = GPIO_PULLUP_DISABLE;
    power_config.pull_down_en = GPIO_PULLDOWN_DISABLE;
    power_config.intr_type = GPIO_INTR_DISABLE;
    ESP_ERROR_CHECK(gpio_config(&power_config));
    ESP_ERROR_CHECK(gpio_set_level(DISPLAY_POWER, 1));

    uint64_t next_check_seconds = DEFAULT_NEXT_CHECK_SECONDS;
    const esp_err_t wifi_result = WifiConnect();
    if (wifi_result != ESP_OK) {
        ESP_LOGE(TAG, "Wi-Fi connection failed: %s; keeping existing image",
                 esp_err_to_name(wifi_result));
        SleepUntilNextCheck(next_check_seconds);
        return;
    }

    const esp_err_t download_result = DownloadDisplay(
        ImageBW, sizeof(ImageBW), &next_check_seconds,
        FrameId, sizeof(FrameId));
    if (download_result != ESP_OK) {
        ESP_LOGE(TAG, "Display download failed: %s; keeping existing image",
                 esp_err_to_name(download_result));
        SleepUntilNextCheck(next_check_seconds);
        return;
    }

    EPD_GPIOInit();

    // Establish the vendor's known full-refresh baseline before the fast update.
    EPD_FastMode1Init();
    EPD_Display_Clear();
    EPD_Update();

    EPD_FastMode1Init();
    EPD_Display(ImageBW);
    EPD_FastUpdate();
    EPD_DeepSleep();

    ESP_LOGI(TAG, "Downloaded display refreshed successfully");
    const esp_err_t ack_result = AcknowledgeDisplay(FrameId);
    if (ack_result != ESP_OK) {
        ESP_LOGW(TAG, "Frame acknowledgement failed: %s",
                 esp_err_to_name(ack_result));
    }
    SleepUntilNextCheck(next_check_seconds);
}
