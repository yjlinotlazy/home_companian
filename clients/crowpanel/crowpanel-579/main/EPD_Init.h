#ifndef CROWPANEL_EPD_INIT_H
#define CROWPANEL_EPD_INIT_H

#include "spi.h"

#define EPD_W 800
#define EPD_H 272

#define WHITE 0xFF
#define BLACK 0x00

#define Source_BYTES (400 / 8)
#define Gate_BITS 272
#define ALLSCREEN_BYTES (Source_BYTES * Gate_BITS)

void EPD_READBUSY(void);
void EPD_HW_RESET(void);
void EPD_Update(void);
void EPD_PartUpdate(void);
void EPD_FastUpdate(void);
void EPD_DeepSleep(void);
void EPD_FastMode1Init(void);
void EPD_SetRAMMP(void);
void EPD_SetRAMMA(void);
void EPD_SetRAMSP(void);
void EPD_SetRAMSA(void);
void EPD_Display_Clear(void);
void EPD_Display(const uint8_t *ImageBW);

#endif
