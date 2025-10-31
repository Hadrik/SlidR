#ifndef ST7735_H
#define ST7735_H

#pragma once

#include <Adafruit_ST7735.h>

class ST7735 : public Adafruit_ST7735 {
public:
    ST7735(int8_t cs, int8_t dc, int8_t mosi, int8_t sclk, int8_t rst) : Adafruit_ST7735(cs, dc, mosi, sclk, rst) {}
    ~ST7735() = default;

    void setColRowStart(int8_t col, int8_t row) {
        Adafruit_ST7735::setColRowStart(col, row);
    }
private:
};

#endif