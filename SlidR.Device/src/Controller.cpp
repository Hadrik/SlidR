#include "Controller.h"
#include <FreeRTOS.h>
#include <FS.h>
#include <LittleFS.h>
#include <algorithm>
#include <string>

Controller::Controller()
    : _last_ping_time(0),
      _is_awake(true),
      _backlight_level(255),
      _spi_mutex(nullptr)
{
    _spi_mutex = xSemaphoreCreateMutex();
}

void Controller::begin() {
    _communication.begin();

    if (!LittleFS.begin(true)) {
        _communication.send_log("FS mount fail");
    } else {
        _communication.send_log("FS mount ok");
    }

    auto cfg = _config_loader.load();
    if (cfg) {
        _device_config = cfg;
    } else {
        _communication.send_log("Failed to load config, using defaults");
        _device_config = _config_loader.load_default();
        _config_loader.save(*_device_config);
    }
    _backlight_level = 255; // TODO: Move to config
    init_hardware();

    _communication.on_packet = [this](Communication::packet_t packet) {
        handle_command(packet);
    };

    create_tasks();
}

void Controller::create_tasks() {
    if (!_comm_task_handle) {
        xTaskCreate(comm_task, "Comm Task", 4096, this, 2, &_comm_task_handle);
    }
    if (!_segment_task_handle) {
        xTaskCreate(segment_task, "Segment Task", 4096, this, 1, &_segment_task_handle);
    }
    if (!_watchdog_task_handle && _device_config->do_sleep) {
        xTaskCreate(watchdog_task, "Watchdog Task", 2048, this, 1, &_watchdog_task_handle);
    }
}

void Controller::init_hardware() {
    // TODO: Temporarily using software SPI
    // SPI.end();
    // SPI.begin(_device_config.spiClkPin, -1, _device_config.spiDataPin, -1);

    pinMode(_device_config->tft_backlight_pin, OUTPUT);
    analogWrite(_device_config->tft_backlight_pin, 255); // TODO: Ensure backlight is off during setup

    for (auto& segment : _device_config->segments) {
        pinMode(segment.pot_pin, INPUT);
        pinMode(segment.tft_cs_pin, OUTPUT);
        digitalWrite(segment.tft_cs_pin, HIGH);
    }

    _segments.clear();
    for (ssize_t i = _device_config->segments.size() - 1; i >= 0; i--) {
        _segments.push_back(Segment::create_and_init(i, _device_config->segments[i], _communication, _device_config->tft_dc_pin, _device_config->spi_data_pin, _device_config->spi_clk_pin));
    }
}

void Controller::handle_command(Communication::packet_t packet) {
    _last_ping_time = millis();
    if (!_is_awake) {
        wake_up();
    }

    switch (packet.command) {
        case Command::PING:
            _communication.send_packet(Command::PONG);
            break;
        
        case Command::SET_CONFIG: {
            auto in_cfg = _config_loader.from_bytes(packet.data);
            if (!in_cfg) {
                _communication.send_err(ErrorCode::INVALID_CONFIG);
                return;
            }

            apply_config_changes(*in_cfg);
            _device_config = in_cfg;
            _config_loader.save(*_device_config);

            _communication.send_packet(Command::ACK);
            break;
        }

        case Command::GET_CONFIG: {
            auto cfg_data = _config_loader.to_bytes(*_device_config);
            _communication.send_packet(Command::CONFIG_DATA, cfg_data.data(), cfg_data.size());
            break;
        }

        case Command::DEFAULT_CONFIG: {
            auto default_cfg = _config_loader.load_default();
            apply_config_changes(*default_cfg);
            _device_config = default_cfg;
            _config_loader.save(*_device_config);

            _communication.send_packet(Command::ACK);
            break;
        }

        case Command::UPLOAD_IMAGE_START: {
            // TODO!!: Move all file transfer commands to Communication class
            uint8_t segment_index = packet.data[0];
            uint32_t totalBytes;
            memcpy(&totalBytes, packet.data.data() + 1, 4);
            std::string image_path = Segment::get_image_path(segment_index);
            _communication.send_log(("Receiving image [" + std::to_string(segment_index) + "] '" + image_path + "' (" + std::to_string(totalBytes) + ")B\n").c_str());

            if (_communication.start_file_upload(image_path, totalBytes)) {
                _communication.send_packet(Command::ACK);
            } else {
                _communication.send_err(ErrorCode::FILE_ERROR);
            }
            break;
        }

        case Command::UPLOAD_IMAGE_DATA: {
            if (_communication.receive_file_data(packet.data)) {
                _communication.send_packet(Command::ACK);
            } else {
                _communication.send_err(ErrorCode::FILE_ERROR);
            }
            break;
        }

        case Command::UPLOAD_IMAGE_END: {
            _communication.finish_file_transfer();
            _communication.send_packet(Command::ACK);

            // TODO: Only reload the affected segment
            for (size_t i = 0; i < _segments.size(); i++) {
                _segments[i]->load_and_display_image();
            }
            break;
        }

        case Command::DOWNLOAD_IMAGE_START: {
            uint8_t segment_index = packet.data[0];

            _communication.send_packet(Command::ACK);
            _communication.start_file_download(Segment::get_image_path(segment_index));
            break;
        }

        case Command::SET_BACKLIGHT: {
            _backlight_level = packet.data[0];
            analogWrite(_device_config->tft_backlight_pin, _backlight_level);
            break;
        }

        case Command::GET_STATUS: {
            std::vector<uint8_t> status_data;
            status_data.push_back(_is_awake ? 1 : 0);
            status_data.push_back(_backlight_level);
            status_data.push_back(_segments.size());
            _communication.send_packet(Command::STATUS_DATA, status_data);
            break;
        }
        
        default:
            _communication.send_err(ErrorCode::INVALID_COMMAND);
            break;
    }
}

void Controller::apply_config_changes(const DeviceConfig &new_config) {
    if (new_config.tft_backlight_pin != _device_config->tft_backlight_pin) {
        pinMode(new_config.tft_backlight_pin, OUTPUT);
        analogWrite(new_config.tft_backlight_pin, _backlight_level);
    }

    if (new_config.do_sleep != _device_config->do_sleep) {
        if (new_config.do_sleep && !_watchdog_task_handle) {
            xTaskCreate(watchdog_task, "Watchdog Task", 2048, this, 1, &_watchdog_task_handle);
        } else if (!new_config.do_sleep && _watchdog_task_handle) {
            vTaskDelete(_watchdog_task_handle);
            _watchdog_task_handle = nullptr;
        }
    }

    if (new_config.baudrate != _device_config->baudrate) {
        _communication.change_baudrate(new_config.baudrate);
    }

    if (new_config.segments.size() > _device_config->segments.size()) {
        for (size_t i = _device_config->segments.size(); i < new_config.segments.size(); i++) {
            _segments.push_back(Segment::create_and_init(i, new_config.segments[i], _communication, new_config.tft_dc_pin, new_config.spi_data_pin, new_config.spi_clk_pin));
        }
    } else if (new_config.segments.size() < _device_config->segments.size()) {
        _segments.resize(new_config.segments.size());
    }

    // For SPI changes all segments need to be reinitialized
    if (new_config.spi_clk_pin != _device_config->spi_clk_pin ||
        new_config.spi_data_pin != _device_config->spi_data_pin ||
        new_config.tft_dc_pin != _device_config->tft_dc_pin ||
        new_config.spi_speed_hz != _device_config->spi_speed_hz) {
        _segments.clear();
        for (ssize_t i = new_config.segments.size() - 1; i >= 0; i--) {
            _segments.push_back(Segment::create_and_init(i, new_config.segments[i], _communication, new_config.tft_dc_pin, new_config.spi_data_pin, new_config.spi_clk_pin));
        }
        return;
    }

    for (size_t i = 0; i < new_config.segments.size(); i++) {
        auto& old_seg = _device_config->segments[i];
        auto& new_seg = new_config.segments[i];
        // Newly created segments are already configured
        if (i >= _device_config->segments.size()) break;

        if (new_seg.tft_cs_pin != old_seg.tft_cs_pin) {
            _segments[i] = Segment::create_and_init(i, new_seg, _communication, new_config.tft_dc_pin, new_config.spi_data_pin, new_config.spi_clk_pin);
            continue;
        }

        if (new_seg.pot_pin != old_seg.pot_pin) {
            _segments[i]->config().pot_pin = new_seg.pot_pin;
        }
        if (new_seg.pot_min_value != old_seg.pot_min_value) {
            _segments[i]->config().pot_min_value = new_seg.pot_min_value;
        }
        if (new_seg.pot_max_value != old_seg.pot_max_value) {
            _segments[i]->config().pot_max_value = new_seg.pot_max_value;
        }
    }
}

void Controller::wake_up() {
    _is_awake = true;
    analogWrite(_device_config->tft_backlight_pin, _backlight_level);
    for (auto& segment : _segments) {
        segment->load_and_display_image();
    }
}

void Controller::sleep() {
    _is_awake = false;
    analogWrite(_device_config->tft_backlight_pin, 0);
    for (auto& segment : _segments) {
        segment->sleep();
    }
}

void Controller::comm_task(void *param) {
    auto* controller = static_cast<Controller*>(param);
    while (true) {
        controller->_communication.update();
        vTaskDelay(10 / portTICK_PERIOD_MS);
    }
}

void Controller::segment_task(void *param) {
    auto* controller = static_cast<Controller*>(param);
    while (true) {
        if (controller->_is_awake) {
            for (uint8_t i = 0; i < controller->_segments.size(); i++) {
                uint8_t vol;
                if (controller->_segments[i]->has_volume_changed(vol)) {
                    uint8_t payload[2] = { i, vol };
                    controller->_communication.send_packet(Command::SLIDER_VALUE, payload, sizeof(payload));
                }
            }
        }
        vTaskDelay(pdMS_TO_TICKS(Controller::SLIDER_POLL_INTERVAL_MS));
    }
}

void Controller::watchdog_task(void *param) {
    auto* controller = static_cast<Controller*>(param);
    while (true) {
        if (controller->_is_awake &&
            (millis() - controller->_last_ping_time) > Controller::PING_TIMEOUT_MS) {
            controller->sleep();
        }
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
