#ifndef CONFIG_H
#define CONFIG_H

#pragma once

#include <cinttypes>
#include <vector>
#include <string>

struct SegmentConfig {
    uint8_t tft_cs_pin;
    uint8_t pot_pin;
    uint16_t pot_min_value;
    uint16_t pot_max_value;
};

struct DeviceConfig {
    int8_t spi_clk_pin;
    int8_t spi_data_pin;
    uint8_t tft_dc_pin;
    uint8_t tft_backlight_pin;
    uint8_t tft_backlight_value;
    uint32_t spi_speed_hz;
    uint32_t baudrate;
    bool wait_for_serial;
    bool do_sleep;
    std::vector<SegmentConfig> segments;
};

#endif // CONFIG_H