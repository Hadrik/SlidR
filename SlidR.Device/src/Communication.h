#ifndef COMMUNICATION_H
#define COMMUNICATION_H

#pragma once

#include "ProtocolConstants.h"

#include <functional>
#include <vector>
#include <string>
#include <FS.h>
#include <LittleFS.h>
#include <USBCDC.h>
#include <FreeRTOS.h>

class Communication {
public:
    using packet_t = struct {
        Command command;
        std::vector<uint8_t> data;
    };
    using packet_cb_t = std::function<void(packet_t packet)>;
    packet_cb_t on_packet;

    Communication();
    ~Communication() = default;

    void begin();
    void update();
    void change_baudrate(uint32_t baudrate);

    void send_packet(Command command, const uint8_t* data = nullptr, uint16_t size = 0);
    void send_packet(Command command, const std::vector<uint8_t>& data) {
        send_packet(command, data.data(), data.size());
    }
    void send_err(ErrorCode code);
    void send_log(const char* message);
    void send_log(const std::string& message) {
        send_log(message.c_str());
    }

    bool start_file_upload(const std::string& path, uint32_t total_size);
    bool receive_file_data(const std::vector<uint8_t>& data);
    void start_file_download(const std::string& path);
    void finish_file_transfer();

    bool transfer_in_progress() {
        return _transfer_watchdog_task_handle != nullptr;
    }

private:
    static bool ensure_parent_dirs(const std::string& full_path);
    uint8_t calculate_checksum(const uint8_t* data, size_t size);
    void send_image();
    void cancel_transfer();
    void transfer_watchdog_task(void* param);
    TaskHandle_t _transfer_watchdog_task_handle = nullptr;
    SemaphoreHandle_t _transfer_watchdog_reset;
    SemaphoreHandle_t _transfer_waiting_for_ack;

    static constexpr size_t MAX_PACKET_SIZE = 4096;
    static constexpr uint32_t PACKET_TIMEOUT_MS = 1000;
    static constexpr const char* UPLOAD_TEMP_PATH = "/upload_temp";
    std::string _upload_path;
    uint8_t _rx_buffer[MAX_PACKET_SIZE];
    size_t _rx_index = 0;
    bool _in_packet = false;
    size_t _last_in_data = 0;
    uint16_t _expected_size = 0;
    
    File _file;
    uint32_t _upload_bytes_received = 0;
    uint32_t _upload_total_size = 0;
};

#endif