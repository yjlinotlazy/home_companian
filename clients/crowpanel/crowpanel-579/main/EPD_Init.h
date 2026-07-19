#ifndef CROWPANEL_EPD_INIT_H
#define CROWPANEL_EPD_INIT_H

#include "spi.h"

#define EPD_W 800
#define EPD_H 272

#define Source_BYTES (400 / 8)
#define Gate_BITS 272
#define ALLSCREEN_BYTES (Source_BYTES * Gate_BITS)

void EPD_FastUpdate(void);
void EPD_DeepSleep(void);
void EPD_FastMode1Init(void);
void EPD_Display(const uint8_t *ImageBW);

#endif
