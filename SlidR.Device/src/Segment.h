#ifndef SEGMENT_H
#define SEGMENT_H

#pragma once

#include "Config.h"
#include "Communication.h"
#include "ST7735.h"

#include <FreeRTOS.h>
#include <cinttypes>
#include <memory>
#include <string>

class Segment {
public:
    Segment(uint8_t index, const SegmentConfig& cfg, Communication& comm, uint8_t dc, uint8_t mosi, uint8_t sck);
    ~Segment() = default;
    static std::unique_ptr<Segment> create_and_init(uint8_t index, const SegmentConfig& cfg, Communication& comm, uint8_t dc, uint8_t mosi, uint8_t sck);

    void begin();
    bool load_and_display_image();

    uint8_t read_volume();
    bool has_volume_changed(uint8_t& out_vol);
    
    void sleep();

    SegmentConfig& config() { return _config; }
    static std::string get_image_path(uint8_t index) {
        return "/images/img-" + std::to_string(index) + ".bin";
    }

private:
    const std::string _image_path;
    uint8_t _index;
    SegmentConfig _config;
    Communication& _communication;
    std::unique_ptr<ST7735> _tft;
    uint16_t _last_pot_value;
    uint8_t _last_vol_percent;
    SemaphoreHandle_t _display_mutex;
};

#endif