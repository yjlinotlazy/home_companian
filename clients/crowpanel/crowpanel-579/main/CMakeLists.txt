idf_component_register(
    SRCS "main.cpp" "spi.cpp" "EPD_Init.cpp" "wifi_station.cpp"
         "display_download.cpp"
    INCLUDE_DIRS "."
    REQUIRES esp_driver_gpio esp_http_client esp_wifi nvs_flash
    EMBED_TXTFILES "rootCA.pem"
)
