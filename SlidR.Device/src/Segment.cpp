#include "Segment.h"
#include <Arduino.h>
#include <FS.h>
#include <LittleFS.h>
#include <string>

Segment::Segment(uint8_t index, const SegmentConfig &cfg, Communication &comm, uint8_t dc, uint8_t mosi, uint8_t sck)
    : _image_path(Segment::get_image_path(index)), _index(index), _config(cfg), _communication(comm), _last_pot_value(0), _last_vol_percent(0) {
    _display_mutex = xSemaphoreCreateMutex();
    _tft = std::make_unique<ST7735>(cfg.tft_cs_pin, dc, mosi, sck, -1);
}

std::unique_ptr<Segment> Segment::create_and_init(uint8_t index, const SegmentConfig &cfg, Communication &comm, uint8_t dc, uint8_t mosi, uint8_t sck) {
    auto seg = std::make_unique<Segment>(
        index,
        cfg,
        comm,
        dc,
        mosi,
        sck
    );
    seg->begin();
    seg->load_and_display_image();
    return seg;
}

void Segment::begin() {
    _tft->setSPISpeed(100000);
    _tft->initR(INITR_144GREENTAB);
    _tft->setRotation(0);
    _tft->setColRowStart(2, 1);
    _tft->fillScreen(ST7735_YELLOW);
    _tft->invertDisplay(true);
}

bool Segment::load_and_display_image() {
    if (xSemaphoreTake(_display_mutex, pdMS_TO_TICKS(500)) != pdTRUE) {
        _communication.send_log("Failed to acquire display mutex");
        return false;
    }

    File img_file = LittleFS.open(_image_path.c_str(), "r");
    if (!img_file) {
        _communication.send_log(("Failed to open image: '" + _image_path + "'").c_str());
        xSemaphoreGive(_display_mutex);
        return false;
    }

    uint16_t img_width;
    uint16_t img_height;
    img_file.read((uint8_t*)&img_width, sizeof(img_width));
    img_file.read((uint8_t*)&img_height, sizeof(img_height));

    _communication.send_log(("Loading image: '" + _image_path + "' (" + std::to_string(img_width) + "x" + std::to_string(img_height) + ")\n").c_str());

    _tft->fillScreen(ST7735_CYAN);

    constexpr size_t CHUNK_SIZE = 256;
    uint16_t pixel_buffer[CHUNK_SIZE];
    size_t total_pixels = img_width * img_height;
    size_t pixels_read = 0;

    _tft->startWrite();
    _tft->setAddrWindow(0, 0, img_width, img_height);
    while (pixels_read < total_pixels) {
        size_t pixels_to_read = std::min(CHUNK_SIZE, total_pixels - pixels_read);
        size_t bytes_to_read = pixels_to_read * sizeof(uint16_t);
        size_t read_bytes = img_file.read((uint8_t*)pixel_buffer, bytes_to_read);
        if (read_bytes != bytes_to_read) {
            _communication.send_log(("Read error: expected " + std::to_string(bytes_to_read) + ", got " + std::to_string(read_bytes)).c_str());
            _tft->endWrite();
            img_file.close();
            xSemaphoreGive(_display_mutex);
            return false;
        }

        _tft->writePixels(pixel_buffer, read_bytes / 2, true, true);
        pixels_read += pixels_to_read;
    }
    _tft->endWrite();
    img_file.close();

    _communication.send_log(("Image '" + _image_path + "' loaded successfully").c_str());

    xSemaphoreGive(_display_mutex);    
    return true;
}

uint8_t Segment::read_volume() {
    uint16_t raw_value = analogRead(_config.pot_pin);

    uint16_t range = _config.pot_max_value - _config.pot_min_value;
    if (range == 0) {
        return 0;
    }

    int32_t mapped = (((int32_t)raw_value - _config.pot_min_value) * 100) / range;
    mapped = constrain(mapped, 0, 100);

    return static_cast<uint8_t>(mapped);
}

bool Segment::has_volume_changed(uint8_t &out_vol) {
    out_vol = read_volume();
    if (abs(out_vol - _last_vol_percent) >= 2) {
        _last_vol_percent = out_vol;
        return true;
    }
    return false;
}

void Segment::sleep() {
    if (xSemaphoreTake(_display_mutex, pdMS_TO_TICKS(500)) == pdTRUE) {
        _tft->fillScreen(ST7735_BLACK);
        // TODO: _tft->enableSleep() ?
        xSemaphoreGive(_display_mutex);
    }
}
