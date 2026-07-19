#ifndef CROWPANEL_DISPLAY_DOWNLOAD_H
#define CROWPANEL_DISPLAY_DOWNLOAD_H

#include <cstddef>
#include <cstdint>

#include "esp_err.h"


esp_err_t DownloadDisplay(uint8_t *buffer, size_t buffer_size,
                          uint64_t *next_check_seconds);

#endif
