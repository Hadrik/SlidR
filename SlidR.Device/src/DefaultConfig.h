#ifndef DEFAULT_CONFIG_H
#define DEFAULT_CONFIG_H

#pragma once

#include "Config.h"

DeviceConfig DEFAULT_CONFIG = {
    .spi_clk_pin = 3,
    .spi_data_pin = 5,
    .tft_dc_pin = 7,
    .tft_backlight_pin = 39,
    .spi_speed_hz = 1000000,
    .baudrate = 115200,
    .wait_for_serial = true,
    .do_sleep = false,
    .segments = {
        {
            .tft_cs_pin = 8,
            .pot_pin = 39,
            .pot_min_value = 0,
            .pot_max_value = 4095
        },
        {
            .tft_cs_pin = 6,
            .pot_pin = 37,
            .pot_min_value = 0,
            .pot_max_value = 4095
        },
        {
            .tft_cs_pin = 4,
            .pot_pin = 35,
            .pot_min_value = 0,
            .pot_max_value = 4095
        },
        {
            .tft_cs_pin = 2,
            .pot_pin = 33,
            .pot_min_value = 0,
            .pot_max_value = 4095
        },
        {
            .tft_cs_pin = 1,
            .pot_pin = 18,
            .pot_min_value = 0,
            .pot_max_value = 4095
        }
    }
};

#endif