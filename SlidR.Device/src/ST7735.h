#ifndef ST7735_H
#define ST7735_H

#pragma once

#include <Arduino.h>
#include <Adafruit_ST7735.h>
#include <SPI.h>

class ST7735 : public Adafruit_ST7735 {
public:
    ST7735(uint8_t cs, SPIClass *spiClass, uint8_t dc, uint8_t rst) : Adafruit_ST7735(spiClass, cs, dc, rst) {}
    ~ST7735() = default;

    void setColRowStart(int8_t col, int8_t row) {
        Adafruit_ST7735::setColRowStart(col, row);
    }

    void setDcPin(uint8_t dc) {
        pinMode(dc, OUTPUT);
        digitalWrite(dc, HIGH);
        _dc = dc;
    }
private:
};

#endif