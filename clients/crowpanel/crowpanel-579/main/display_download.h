#ifndef CROWPANEL_DISPLAY_DOWNLOAD_H
#define CROWPANEL_DISPLAY_DOWNLOAD_H

#include <cstddef>
#include <cstdint>

#include "esp_err.h"

constexpr size_t CROWPANEL_FRAME_ID_SIZE = 65;

esp_err_t DownloadDisplay(uint8_t *buffer, size_t buffer_size,
                          uint64_t *next_check_seconds,
                          char *frame_id, size_t frame_id_size);
esp_err_t AcknowledgeDisplay(const char *frame_id);

#endif
