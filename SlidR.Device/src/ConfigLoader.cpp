#include "ConfigLoader.h"
#include "DefaultConfig.h"
#include <FS.h>
#include <LittleFS.h>

#define GET(x) memcpy(&x, data.data() + offset, sizeof(x)); offset += sizeof(x)

std::shared_ptr<DeviceConfig> ConfigLoader::load() {
    File config_file = LittleFS.open(CONFIG_PATH, "r");
    if (!config_file) return nullptr;

    size_t file_size = config_file.size();
    std::vector<uint8_t> buffer(file_size);

    config_file.read(buffer.data(), file_size);
    config_file.close();

    return from_bytes(buffer);
}

std::shared_ptr<DeviceConfig> ConfigLoader::load_default() {
    return std::make_shared<DeviceConfig>(DEFAULT_CONFIG);
}

bool ConfigLoader::save(const DeviceConfig &config) {
    File config_file = LittleFS.open(CONFIG_PATH, "w");
    if (!config_file) return false;

    auto data = to_bytes(config);
    if (data.empty()) {
        config_file.close();
        return false;
    }

    config_file.write(data.data(), data.size());
    config_file.close();

    return true;
}

std::shared_ptr<DeviceConfig> ConfigLoader::from_bytes(const std::vector<uint8_t> &data) {
    if (data.size() < sizeof(CONFIG_VERSION)) return nullptr;

    size_t offset = 0;
    size_t version;
    GET(version);

    if (version != CONFIG_VERSION) return nullptr;

    auto config = std::make_shared<DeviceConfig>();

    GET(config->spi_clk_pin);
    GET(config->spi_data_pin);
    GET(config->tft_dc_pin);
    GET(config->tft_backlight_pin);
    GET(config->tft_backlight_value);
    GET(config->spi_speed_hz);
    GET(config->baudrate);
    GET(config->wait_for_serial);
    GET(config->do_sleep);

    uint8_t num_segments;
    GET(num_segments);

    config->segments.clear();
    for (uint8_t i = 0; i < num_segments; i++) {
        SegmentConfig seg;
        GET(seg.tft_cs_pin);
        GET(seg.pot_pin);
        GET(seg.pot_min_value);
        GET(seg.pot_max_value);
        config->segments.push_back(seg);
    }

    return config;
}

std::vector<uint8_t> ConfigLoader::to_bytes(const DeviceConfig &config) {
    std::vector<uint8_t> buffer;

    auto append = [&](const void* src, size_t len) {
        const uint8_t* byte_src = static_cast<const uint8_t*>(src);
        buffer.insert(buffer.end(), byte_src, byte_src + len);
    };

    append(&CONFIG_VERSION, sizeof(CONFIG_VERSION));
    append(&config.spi_clk_pin, sizeof(config.spi_clk_pin));
    append(&config.spi_data_pin, sizeof(config.spi_data_pin));
    append(&config.tft_dc_pin, sizeof(config.tft_dc_pin));
    append(&config.tft_backlight_pin, sizeof(config.tft_backlight_pin));
    append(&config.tft_backlight_value, sizeof(config.tft_backlight_value));
    append(&config.spi_speed_hz, sizeof(config.spi_speed_hz));
    append(&config.baudrate, sizeof(config.baudrate));
    append(&config.wait_for_serial, sizeof(config.wait_for_serial));
    append(&config.do_sleep, sizeof(config.do_sleep));

    uint8_t num_segments = static_cast<uint8_t>(config.segments.size());
    append(&num_segments, sizeof(num_segments));

    for (const auto& seg : config.segments) {
        append(&seg.tft_cs_pin, sizeof(seg.tft_cs_pin));
        append(&seg.pot_pin, sizeof(seg.pot_pin));
        append(&seg.pot_min_value, sizeof(seg.pot_min_value));
        append(&seg.pot_max_value, sizeof(seg.pot_max_value));
    }

    return buffer;
}

#undef GET
