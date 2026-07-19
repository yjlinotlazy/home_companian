#ifndef CROWPANEL_EPD_SPI_H
#define CROWPANEL_EPD_SPI_H

#include <stdint.h>

#include "driver/gpio.h"

#define SCK  GPIO_NUM_12
#define MOSI GPIO_NUM_11
#define RES  GPIO_NUM_47
#define DC   GPIO_NUM_46
#define CS   GPIO_NUM_45
#define BUSY GPIO_NUM_48

#define EPD_SCK_Clr()  gpio_set_level(SCK, 0)
#define EPD_SCK_Set()  gpio_set_level(SCK, 1)
#define EPD_MOSI_Clr() gpio_set_level(MOSI, 0)
#define EPD_MOSI_Set() gpio_set_level(MOSI, 1)
#define EPD_RES_Clr()  gpio_set_level(RES, 0)
#define EPD_RES_Set()  gpio_set_level(RES, 1)
#define EPD_DC_Clr()   gpio_set_level(DC, 0)
#define EPD_DC_Set()   gpio_set_level(DC, 1)
#define EPD_CS_Clr()   gpio_set_level(CS, 0)
#define EPD_CS_Set()   gpio_set_level(CS, 1)
#define EPD_ReadBUSY   gpio_get_level(BUSY)

void EPD_GPIOInit(void);
void EPD_WR_Bus(uint8_t dat);
void EPD_WR_REG(uint8_t reg);
void EPD_WR_DATA8(uint8_t dat);

#endif
