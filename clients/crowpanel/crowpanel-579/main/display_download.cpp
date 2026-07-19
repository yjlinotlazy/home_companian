#include "display_download.h"

#include "esp_check.h"
#include "esp_http_client.h"
#include "esp_log.h"

#include <cstdlib>
#include <cstring>
#include <strings.h>

namespace {
constexpr char TAG[] = "display_download";
constexpr int HTTP_TIMEOUT_MS = 15000;
constexpr uint64_t MAX_NEXT_CHECK_SECONDS = 24 * 60 * 60;

struct DownloadContext {
    uint64_t next_check_seconds;
};

esp_err_t HttpEventHandler(esp_http_client_event_t *event)
{
    if (event->event_id != HTTP_EVENT_ON_HEADER ||
        event->header_key == nullptr || event->header_value == nullptr ||
        strcasecmp(event->header_key, "X-Next-Check-Seconds") != 0) {
        return ESP_OK;
    }

    char *end = nullptr;
    const unsigned long long parsed = std::strtoull(event->header_value, &end, 10);
    if (end != event->header_value && *end == '\0' && parsed > 0 &&
        parsed <= MAX_NEXT_CHECK_SECONDS) {
        static_cast<DownloadContext *>(event->user_data)->next_check_seconds = parsed;
    } else {
        ESP_LOGW(TAG, "Ignoring invalid X-Next-Check-Seconds header");
    }
    return ESP_OK;
}

extern const uint8_t root_ca_pem_start[]
    asm("_binary_rootCA_pem_start");

class HttpClient {
public:
    explicit HttpClient(esp_http_client_handle_t handle) : handle_(handle) {}
    ~HttpClient()
    {
        if (handle_ != nullptr) {
            esp_http_client_close(handle_);
            esp_http_client_cleanup(handle_);
        }
    }

    HttpClient(const HttpClient &) = delete;
    HttpClient &operator=(const HttpClient &) = delete;

    esp_http_client_handle_t get() const { return handle_; }

private:
    esp_http_client_handle_t handle_;
};
}

esp_err_t DownloadDisplay(uint8_t *buffer, size_t buffer_size,
                          uint64_t *next_check_seconds)
{
    if (buffer == nullptr || buffer_size == 0 || next_check_seconds == nullptr) {
        return ESP_ERR_INVALID_ARG;
    }
    if (CONFIG_CROWPANEL_SERVER_URL[0] == '\0') {
        ESP_LOGE(TAG,
                 "Framebuffer server URL is empty; configure it with idf.py menuconfig");
        return ESP_ERR_INVALID_STATE;
    }

    DownloadContext context = {*next_check_seconds};

    esp_http_client_config_t config = {};
    config.url = CONFIG_CROWPANEL_SERVER_URL;
    config.cert_pem = reinterpret_cast<const char *>(root_ca_pem_start);
    config.timeout_ms = HTTP_TIMEOUT_MS;
    config.disable_auto_redirect = true;
    config.event_handler = HttpEventHandler;
    config.user_data = &context;

    HttpClient client(esp_http_client_init(&config));
    if (client.get() == nullptr) {
        return ESP_ERR_NO_MEM;
    }

    ESP_LOGI(TAG, "Downloading %s", CONFIG_CROWPANEL_SERVER_URL);
    ESP_RETURN_ON_ERROR(esp_http_client_open(client.get(), 0), TAG,
                        "Failed to open HTTP connection");

    const int64_t content_length = esp_http_client_fetch_headers(client.get());
    if (content_length < 0) {
        ESP_LOGE(TAG, "Failed to read HTTP response headers");
        return ESP_FAIL;
    }

    const int status = esp_http_client_get_status_code(client.get());
    if (status != 200) {
        ESP_LOGE(TAG, "Server returned HTTP %d", status);
        return ESP_ERR_HTTP_BASE;
    }
    if (content_length != 0 &&
        content_length != static_cast<int64_t>(buffer_size)) {
        ESP_LOGE(TAG, "Expected %u bytes, server announced %lld",
                 static_cast<unsigned>(buffer_size),
                 static_cast<long long>(content_length));
        return ESP_ERR_INVALID_SIZE;
    }

    size_t received = 0;
    while (received < buffer_size) {
        const int read = esp_http_client_read(
            client.get(), reinterpret_cast<char *>(buffer + received),
            static_cast<int>(buffer_size - received));
        if (read < 0) {
            ESP_LOGE(TAG, "HTTP body read failed after %u bytes",
                     static_cast<unsigned>(received));
            return ESP_FAIL;
        }
        if (read == 0) {
            break;
        }
        received += static_cast<size_t>(read);
    }

    if (received != buffer_size) {
        ESP_LOGE(TAG, "Expected %u bytes, received %u",
                 static_cast<unsigned>(buffer_size),
                 static_cast<unsigned>(received));
        return ESP_ERR_INVALID_SIZE;
    }

    char extra_byte;
    const int extra = esp_http_client_read(client.get(), &extra_byte, 1);
    if (extra != 0) {
        ESP_LOGE(TAG, "Response body is larger than %u bytes",
                 static_cast<unsigned>(buffer_size));
        return extra < 0 ? ESP_FAIL : ESP_ERR_INVALID_SIZE;
    }

    ESP_LOGI(TAG, "Downloaded %u framebuffer bytes",
             static_cast<unsigned>(received));
    *next_check_seconds = context.next_check_seconds;
    return ESP_OK;
}
