#include "spi.h"

#include "esp_check.h"

void EPD_GPIOInit(void)
{
    gpio_config_t output_config = {};
    output_config.pin_bit_mask = (1ULL << SCK) | (1ULL << MOSI) |
                                 (1ULL << RES) | (1ULL << DC) |
                                 (1ULL << CS);
    output_config.mode = GPIO_MODE_OUTPUT;
    output_config.pull_up_en = GPIO_PULLUP_DISABLE;
    output_config.pull_down_en = GPIO_PULLDOWN_DISABLE;
    output_config.intr_type = GPIO_INTR_DISABLE;
    ESP_ERROR_CHECK(gpio_config(&output_config));

    gpio_config_t input_config = {};
    input_config.pin_bit_mask = 1ULL << BUSY;
    input_config.mode = GPIO_MODE_INPUT;
    input_config.pull_up_en = GPIO_PULLUP_DISABLE;
    input_config.pull_down_en = GPIO_PULLDOWN_DISABLE;
    input_config.intr_type = GPIO_INTR_DISABLE;
    ESP_ERROR_CHECK(gpio_config(&input_config));
}

void EPD_WR_Bus(uint8_t dat)
{
    EPD_CS_Clr();
    for (uint8_t i = 0; i < 8; i++) {
        EPD_SCK_Clr();
        if (dat & 0x80) {
            EPD_MOSI_Set();
        } else {
            EPD_MOSI_Clr();
        }
        EPD_SCK_Set();
        dat <<= 1;
    }
    EPD_CS_Set();
}

void EPD_WR_REG(uint8_t reg)
{
    EPD_DC_Clr();
    EPD_WR_Bus(reg);
    EPD_DC_Set();
}

void EPD_WR_DATA8(uint8_t dat)
{
    EPD_DC_Set();
    EPD_WR_Bus(dat);
    EPD_DC_Set();
}
