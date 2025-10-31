#include "Communication.h"
#include "Segment.h"
#include <Arduino.h>

Communication::Communication() {
    _transfer_watchdog_reset = xSemaphoreCreateBinary();
    _transfer_waiting_for_ack = xSemaphoreCreateBinary();
}

void Communication::begin() {
  Serial.begin(115200);
  Serial.setTimeout(1000);
  while (!Serial) { // TODO: Make this a config option
    delay(10);
  }
}

void Communication::update() {
    if (_in_packet && (millis() - _last_in_data_time > PACKET_TIMEOUT_MS)) {
        send_log("Packet timeout");
        _in_packet = false;
        _rx_index = 0;
    }

    while (Serial.available()) {
        uint8_t byte = Serial.read();

        if (!_in_packet && byte == START_BYTE) {
            _rx_index = 0;
            _in_packet = true;
            _last_in_data_time = millis();
            continue;
        }

        if (_in_packet) {
            _last_in_data_time = millis();
            _rx_buffer[_rx_index++] = byte;

            if (_rx_index == 3) {
                _expected_size = _rx_buffer[1] | (_rx_buffer[2] << 8);
                if (_expected_size > MAX_PACKET_SIZE - 4) {
                    send_log(("Packet size overflow: " + String(_expected_size) + "\n").c_str());
                    send_err(ErrorCode::BUFFER_OVERFLOW);
                    _in_packet = false;
                    continue;
                }
            }

            if (_rx_index >= 3 && _rx_index == _expected_size + 4) {
                uint8_t recv_checksum = _rx_buffer[_rx_index - 1];
                uint8_t calc_checksum = calculate_checksum(_rx_buffer, _rx_index - 1);

                if (recv_checksum == calc_checksum) {
                    _last_in_packet_time = millis();
                    Command cmd = static_cast<Command>(_rx_buffer[0]);
                    std::vector<uint8_t> data(_rx_buffer + 3, _rx_buffer + 3 + _expected_size);
                    packet_t packet{cmd, data};

                    if (!handle_file_transfer(packet)) {
                        on_packet(packet);
                    }

                } else {
                    send_log(("Checksum mismatch (RX: 0x" + String(recv_checksum, HEX) + ", CALC: 0x" + String(calc_checksum, HEX) + ")\n").c_str());
                    send_err(ErrorCode::CHECKSUM_ERROR);
                }

                _in_packet = false;
                _rx_index = 0;
            }
        }
    }
}

void Communication::change_baudrate(uint32_t baudrate) { // TODO: implement
}

void Communication::send_packet(Command command, const uint8_t *data, uint16_t size) {
    Serial.write(START_BYTE);
    Serial.write(static_cast<uint8_t>(command));
    Serial.write(size & 0xFF);
    Serial.write((size >> 8) & 0xFF);

    uint8_t checksum = static_cast<uint8_t>(command);
    checksum ^= size & 0xFF;
    checksum ^= (size >> 8) & 0xFF;

    for (uint16_t i = 0; i < size; i++) {
        Serial.write(data[i]);
        checksum ^= data[i];
    }
    
    Serial.write(checksum);
}

void Communication::send_err(ErrorCode code) {
    send_packet(Command::ERROR_CMD, reinterpret_cast<const uint8_t*>(&code), sizeof(code));
}

void Communication::send_log(const char* message) {
    send_packet(Command::LOG_MESSAGE, reinterpret_cast<const uint8_t*>(message), strlen(message));
}

bool Communication::handle_file_transfer(const packet_t &packet) {
    switch (packet.command) {
        case Command::UPLOAD_IMAGE_START: {
            if (packet.data.size() != 5) {
                send_err(ErrorCode::INVALID_DATA);
                break;
            }

            uint8_t segment_index = packet.data.at(0);
            uint32_t total_bytes;
            memcpy(&total_bytes, packet.data.data() + 1, 4);
            std::string image_path = Segment::get_image_path(segment_index);

            if (start_file_upload(image_path, total_bytes)) {
                send_packet(Command::ACK);
            }

            break;
        }

        case Command::UPLOAD_IMAGE_DATA: {
            if (!transfer_in_progress()) {
                send_log("Received UPLOAD_IMAGE_DATA without active transfer\n");
                send_err(ErrorCode::INVALID_COMMAND);
                break;
            }

            if (receive_file_data(packet.data)) {
                send_packet(Command::ACK);
            }

            break;
        }
        
        case Command::UPLOAD_IMAGE_END: {
            if (!transfer_in_progress()) {
                send_log("Received UPLOAD_IMAGE_END without active transfer\n");
                send_err(ErrorCode::INVALID_COMMAND);
                break;
            }

            if (_upload_bytes_received != _upload_total_size) {
                send_log("Upload size mismatch: received " + std::to_string(_upload_bytes_received) + " of " + std::to_string(_upload_total_size) + "\n");
                cancel_transfer();
                send_err(ErrorCode::INVALID_COMMAND);
                break;
            }
            finish_file_transfer();
            send_packet(Command::ACK);
            
            if (on_file_received) {
                on_file_received(_upload_path);
            }
            
            break;
        }

        case Command::DOWNLOAD_IMAGE_START: {
            if (packet.data.size() != 1) {
                send_err(ErrorCode::INVALID_DATA);
                break;
            }
            uint8_t segment_index = packet.data.at(0);
            std::string image_path = Segment::get_image_path(segment_index);
            start_file_download(image_path);
            break;
        }

        case Command::ACK: {
            if (!transfer_in_progress()) {
                return false;
            }
            xSemaphoreGive(_transfer_waiting_for_ack);
            return true;
        }

        default:
            return false;
    }

    return true;
}

bool Communication::start_file_upload(const std::string &path, uint32_t total_size) {
    if (transfer_in_progress()) {
        send_err(ErrorCode::TRANSFER_IN_PROGRESS);
        return false;
    }

    _file = LittleFS.open(UPLOAD_TEMP_PATH, "w");
    if (!_file) {
        send_err(ErrorCode::FILE_ERROR);
        return false;
    }

    _upload_path = path;
    start_transfer_watchdog();

    _upload_total_size = total_size;
    _upload_bytes_received = 0;
    return true;
}

bool Communication::receive_file_data(const std::vector<uint8_t>& data) {
    if (!_file) {
        finish_file_transfer();
        send_log("Received UPLOAD_IMAGE_DATA without active transfer\n");
        send_err(ErrorCode::FILE_ERROR);
        return false;
    }

    xSemaphoreGive(_transfer_watchdog_reset);
    size_t written = _file.write(data.data(), data.size());
    
    if (written != data.size()) {
        send_log("Failed to write all data to file - written: " + std::to_string(written) + ", expected: " + std::to_string(data.size()) + "\n");
        stop_transfer_watchdog();
        cancel_transfer();
        send_err(ErrorCode::FILE_ERROR);
        return false;
    }

    _upload_bytes_received += written;
    return true;
}

void Communication::start_file_download(const std::string& path) {
    _file = LittleFS.open(path.c_str(), "r");
    if (!_file) {
        send_log("Failed to open file for download\n");
        send_err(ErrorCode::FILE_ERROR);
        return;
    }
    
    xSemaphoreTake(_transfer_waiting_for_ack, 0);
    xSemaphoreGive(_transfer_watchdog_reset);
    xTaskCreate(
        [](void* param) {
            static_cast<Communication*>(param)->send_image_task();
            vTaskDelete(nullptr);
        },
        "Send Image Task",
        8192,
        this,
        1,
        nullptr
    );
}

void Communication::finish_file_transfer() {
    stop_transfer_watchdog();

    if (_file) {
        _file.close();
        if (LittleFS.exists(_upload_path.c_str())) {
            if (!LittleFS.remove(_upload_path.c_str())) {
                send_log(("Failed to remove existing file: '" + _upload_path + "'\n").c_str());
                send_err(ErrorCode::FILE_ERROR);
                return;
            }
        }
        if (!Communication::ensure_parent_dirs(_upload_path) ||
            !LittleFS.rename(UPLOAD_TEMP_PATH, _upload_path.c_str())) {
            send_log(("Failed to rename uploaded file to: '" + _upload_path + "'\n").c_str());
            send_err(ErrorCode::FILE_ERROR);
            return;
        }
    }
}

bool Communication::ensure_parent_dirs(const std::string& full_path) {
    auto slash = full_path.find_last_of('/');
    if (slash == std::string::npos || slash == 0) {
        return true;
    }
    std::string path;
    size_t pos = 1;
    while ((pos = full_path.find('/', pos)) != std::string::npos && pos < slash) {
        path = full_path.substr(0, pos);
        if (!LittleFS.exists(path.c_str()) && !LittleFS.mkdir(path.c_str())) {
            return false;
        }
        ++pos;
    }
    path = full_path.substr(0, slash);
    return LittleFS.exists(path.c_str()) || LittleFS.mkdir(path.c_str());
}

uint8_t Communication::calculate_checksum(const uint8_t *data, size_t size) {
    uint8_t checksum = 0;
    for (size_t i = 0; i < size; ++i) {
        checksum ^= data[i];
    }
    return checksum;
}

void Communication::send_image_task() {
    if (!_file) {
        send_log("No file opened for sending image\n");
        send_err(ErrorCode::FILE_ERROR);
        return;
    }

    uint8_t buffer[TRANSFER_SEND_MAX_CHUNK_SIZE];

    while (_file.available()) {
        size_t to_read = std::min(TRANSFER_SEND_MAX_CHUNK_SIZE, static_cast<size_t>(_file.size() - _file.position()));
        if (to_read == 0) {
            break;
        }

        size_t read_bytes = _file.read(buffer, to_read);
        if (read_bytes != to_read) {
            send_log("Failed to read expected number of bytes from file\n");
            send_err(ErrorCode::FILE_ERROR);
            _file.close();
            return;
        } else {
            send_packet(Command::DOWNLOAD_IMAGE_DATA, buffer, read_bytes);
            if (xSemaphoreTake(_transfer_waiting_for_ack, pdMS_TO_TICKS(PACKET_TIMEOUT_MS)) == pdTRUE) {
                xSemaphoreGive(_transfer_watchdog_reset);
            }
        }
    }

    _file.close();
    send_packet(Command::DOWNLOAD_IMAGE_END);
}

void Communication::cancel_transfer() {
    if (_file) {
        _file.close();
        LittleFS.remove(UPLOAD_TEMP_PATH);
    }
    _upload_path.clear();
}

void Communication::start_transfer_watchdog() {
    xSemaphoreGive(_transfer_watchdog_reset);
    xTaskCreate(
        [](void* param) {
            static_cast<Communication*>(param)->transfer_watchdog_task();
            vTaskDelete(nullptr);
        },
        "Transfer Watchdog Task",
        1024,
        this,
        1,
        &_transfer_watchdog_task_handle
    );
}

void Communication::stop_transfer_watchdog() {
    if (_transfer_watchdog_task_handle) {
        vTaskDelete(_transfer_watchdog_task_handle);
        _transfer_watchdog_task_handle = nullptr;
    }
}

void Communication::transfer_watchdog_task() {
    while (true) {
        if (xSemaphoreTake(_transfer_watchdog_reset, pdMS_TO_TICKS(PACKET_TIMEOUT_MS)) != pdTRUE) {
            send_err(ErrorCode::TRANSFER_TIMEOUT);
            cancel_transfer();
            break;
        }
    }
}
