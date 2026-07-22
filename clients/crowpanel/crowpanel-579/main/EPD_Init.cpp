#include "EPD_Init.h"

#include <cstdlib>

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

namespace {
constexpr char TAG[] = "ssd1683";
constexpr TickType_t BUSY_TIMEOUT = pdMS_TO_TICKS(30000);
}

void EPD_READBUSY(void)
{
    const TickType_t start = xTaskGetTickCount();
    while (1) {
        if (EPD_ReadBUSY == 0) {
            break;
        }

        if (xTaskGetTickCount() - start >= BUSY_TIMEOUT) {
            ESP_LOGE(TAG, "BUSY remained high for 30 seconds");
            std::abort();
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
}

void EPD_HW_RESET(void)
{
    vTaskDelay(pdMS_TO_TICKS(10));
    EPD_RES_Clr();
    vTaskDelay(pdMS_TO_TICKS(10));
    EPD_RES_Set();
    vTaskDelay(pdMS_TO_TICKS(10));
    EPD_READBUSY();
}

void EPD_Update(void)
{
    EPD_WR_REG(0x22);
    EPD_WR_DATA8(0xF7);
    EPD_WR_REG(0x20);
    EPD_READBUSY();
}

void EPD_PartUpdate(void)
{
    EPD_WR_REG(0x22);
    EPD_WR_DATA8(0xDC);
    EPD_WR_REG(0x20);
    EPD_READBUSY();
}

void EPD_FastUpdate(void)
{
    EPD_WR_REG(0x22);
    EPD_WR_DATA8(0xC7);
    EPD_WR_REG(0x20);
    EPD_READBUSY();
}

void EPD_DeepSleep(void)
{
    EPD_WR_REG(0x10);
    EPD_WR_DATA8(0x01);
    vTaskDelay(pdMS_TO_TICKS(5));
}

void EPD_FastMode1Init(void)
{
    EPD_HW_RESET();
    EPD_READBUSY();
    EPD_WR_REG(0x12);
    EPD_READBUSY();

    EPD_WR_REG(0x18);
    EPD_WR_DATA8(0x80);

    EPD_WR_REG(0x22);
    EPD_WR_DATA8(0xB1);
    EPD_WR_REG(0x20);
    EPD_READBUSY();

    EPD_WR_REG(0x1A);
    EPD_WR_DATA8(0x64);
    EPD_WR_DATA8(0x00);

    EPD_WR_REG(0x22);
    EPD_WR_DATA8(0x91);
    EPD_WR_REG(0x20);
    EPD_READBUSY();

    EPD_WR_REG(0x3C);
    EPD_WR_DATA8(0x03);
    EPD_READBUSY();
}

void EPD_SetRAMMP(void)
{
    EPD_WR_REG(0x11);
    EPD_WR_DATA8(0x05);
    EPD_WR_REG(0x44);
    EPD_WR_DATA8(0x00);
    EPD_WR_DATA8(0x31);
    EPD_WR_REG(0x45);
    EPD_WR_DATA8(0x0F);
    EPD_WR_DATA8(0x01);
    EPD_WR_DATA8(0x00);
    EPD_WR_DATA8(0x00);
}

void EPD_SetRAMMA(void)
{
    EPD_WR_REG(0x4E);
    EPD_WR_DATA8(0x00);
    EPD_WR_REG(0x4F);
    EPD_WR_DATA8(0x0F);
    EPD_WR_DATA8(0x01);
}

void EPD_SetRAMSP(void)
{
    EPD_WR_REG(0x91);
    EPD_WR_DATA8(0x04);
    EPD_WR_REG(0xC4);
    EPD_WR_DATA8(0x31);
    EPD_WR_DATA8(0x00);
    EPD_WR_REG(0xC5);
    EPD_WR_DATA8(0x0F);
    EPD_WR_DATA8(0x01);
    EPD_WR_DATA8(0x00);
    EPD_WR_DATA8(0x00);
}

void EPD_SetRAMSA(void)
{
    EPD_WR_REG(0xCE);
    EPD_WR_DATA8(0x31);
    EPD_WR_REG(0xCF);
    EPD_WR_DATA8(0x0F);
    EPD_WR_DATA8(0x01);
}

void EPD_Display_Clear(void)
{
    EPD_SetRAMMP();
    EPD_SetRAMMA();
    EPD_WR_REG(0x24);
    for (uint16_t i = 0; i < Gate_BITS; i++) {
        for (uint16_t j = 0; j < Source_BYTES; j++) {
            EPD_WR_DATA8(0xFF);
        }
    }

    EPD_SetRAMMA();
    EPD_WR_REG(0x26);
    for (uint16_t i = 0; i < Gate_BITS; i++) {
        for (uint16_t j = 0; j < Source_BYTES; j++) {
            EPD_WR_DATA8(0x00);
        }
    }

    EPD_SetRAMSP();
    EPD_SetRAMSA();
    EPD_WR_REG(0xA4);
    for (uint16_t i = 0; i < Gate_BITS; i++) {
        for (uint16_t j = 0; j < Source_BYTES; j++) {
            EPD_WR_DATA8(0xFF);
        }
    }

    EPD_SetRAMSA();
    EPD_WR_REG(0xA6);
    for (uint16_t i = 0; i < Gate_BITS; i++) {
        for (uint16_t j = 0; j < Source_BYTES; j++) {
            EPD_WR_DATA8(0x00);
        }
    }
}

void EPD_Display(const uint8_t *ImageBW)
{
    uint32_t i;
    uint8_t tempOriginal;
    uint32_t tempcol = 0;
    uint32_t templine = 0;

    EPD_SetRAMMP();
    EPD_SetRAMMA();
    EPD_WR_REG(0x24);
    for (i = 0; i < ALLSCREEN_BYTES; i++) {
        tempOriginal = *(ImageBW + templine * Source_BYTES * 2 + tempcol);
        templine++;
        if (templine >= Gate_BITS) {
            tempcol++;
            templine = 0;
        }
        EPD_WR_DATA8(tempOriginal);
    }

    EPD_SetRAMSP();
    EPD_SetRAMSA();
    EPD_WR_REG(0xA4);
    for (i = 0; i < ALLSCREEN_BYTES; i++) {
        tempOriginal = *(ImageBW + templine * Source_BYTES * 2 + tempcol);
        templine++;
        if (templine >= Gate_BITS) {
            tempcol++;
            templine = 0;
        }
        EPD_WR_DATA8(tempOriginal);
    }
}
