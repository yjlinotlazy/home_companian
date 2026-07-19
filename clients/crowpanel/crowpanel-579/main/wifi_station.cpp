#include "wifi_station.h"

#include <cstring>

#include "esp_check.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "nvs_flash.h"

namespace {
constexpr char TAG[] = "wifi";
constexpr EventBits_t CONNECTED_BIT = BIT0;
constexpr EventBits_t FAILED_BIT = BIT1;

EventGroupHandle_t connection_events;
int retry_count;

void HandleWifiEvent(void *, esp_event_base_t event_base, int32_t event_id,
                     void *event_data)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        ESP_ERROR_CHECK(esp_wifi_connect());
    } else if (event_base == WIFI_EVENT &&
               event_id == WIFI_EVENT_STA_DISCONNECTED) {
        if (retry_count < CONFIG_CROWPANEL_WIFI_MAXIMUM_RETRY) {
            retry_count++;
            ESP_LOGW(TAG, "Connection lost; retrying (%d/%d)", retry_count,
                     CONFIG_CROWPANEL_WIFI_MAXIMUM_RETRY);
            ESP_ERROR_CHECK(esp_wifi_connect());
        } else {
            xEventGroupSetBits(connection_events, FAILED_BIT);
        }
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        const auto *event = static_cast<const ip_event_got_ip_t *>(event_data);
        retry_count = 0;
        ESP_LOGI(TAG, "Connected to %s, IP: " IPSTR, CONFIG_CROWPANEL_WIFI_SSID,
                 IP2STR(&event->ip_info.ip));
        xEventGroupSetBits(connection_events, CONNECTED_BIT);
    }
}
}

esp_err_t WifiConnect(void)
{
    if (CONFIG_CROWPANEL_WIFI_SSID[0] == '\0') {
        ESP_LOGE(TAG, "Wi-Fi SSID is empty; configure it with idf.py menuconfig");
        return ESP_ERR_INVALID_ARG;
    }

    esp_err_t result = nvs_flash_init();
    if (result == ESP_ERR_NVS_NO_FREE_PAGES ||
        result == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        result = nvs_flash_init();
    }
    ESP_RETURN_ON_ERROR(result, TAG, "Failed to initialize NVS");
    ESP_RETURN_ON_ERROR(esp_netif_init(), TAG, "Failed to initialize TCP/IP");
    ESP_RETURN_ON_ERROR(esp_event_loop_create_default(), TAG,
                        "Failed to create event loop");

    connection_events = xEventGroupCreate();
    if (connection_events == nullptr) {
        return ESP_ERR_NO_MEM;
    }
    if (esp_netif_create_default_wifi_sta() == nullptr) {
        return ESP_ERR_NO_MEM;
    }

    wifi_init_config_t init_config = WIFI_INIT_CONFIG_DEFAULT();
    ESP_RETURN_ON_ERROR(esp_wifi_init(&init_config), TAG,
                        "Failed to initialize Wi-Fi");
    ESP_RETURN_ON_ERROR(
        esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID,
                                   &HandleWifiEvent, nullptr),
        TAG, "Failed to register Wi-Fi event handler");
    ESP_RETURN_ON_ERROR(
        esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP,
                                   &HandleWifiEvent, nullptr),
        TAG, "Failed to register IP event handler");

    wifi_config_t wifi_config = {};
    const size_t ssid_length = std::strlen(CONFIG_CROWPANEL_WIFI_SSID);
    const size_t password_length = std::strlen(CONFIG_CROWPANEL_WIFI_PASSWORD);
    if (ssid_length > sizeof(wifi_config.sta.ssid) ||
        password_length > sizeof(wifi_config.sta.password)) {
        ESP_LOGE(TAG, "Wi-Fi SSID or password is too long");
        return ESP_ERR_INVALID_ARG;
    }
    std::memcpy(wifi_config.sta.ssid, CONFIG_CROWPANEL_WIFI_SSID, ssid_length);
    std::memcpy(wifi_config.sta.password, CONFIG_CROWPANEL_WIFI_PASSWORD,
                password_length);
    wifi_config.sta.threshold.authmode = password_length == 0
                                             ? WIFI_AUTH_OPEN
                                             : WIFI_AUTH_WPA2_PSK;

    ESP_RETURN_ON_ERROR(esp_wifi_set_mode(WIFI_MODE_STA), TAG,
                        "Failed to select station mode");
    ESP_RETURN_ON_ERROR(esp_wifi_set_config(WIFI_IF_STA, &wifi_config), TAG,
                        "Failed to configure station");
    ESP_RETURN_ON_ERROR(esp_wifi_start(), TAG, "Failed to start Wi-Fi");

    const EventBits_t result_bits = xEventGroupWaitBits(
        connection_events, CONNECTED_BIT | FAILED_BIT, pdFALSE, pdFALSE,
        portMAX_DELAY);
    if ((result_bits & CONNECTED_BIT) != 0) {
        return ESP_OK;
    }

    ESP_LOGE(TAG, "Failed to connect to %s after %d retries",
             CONFIG_CROWPANEL_WIFI_SSID,
             CONFIG_CROWPANEL_WIFI_MAXIMUM_RETRY);
    return ESP_FAIL;
}
