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

    std::function<void(packet_t packet)> on_packet;
    std::function<void(const std::string& path)> on_file_received;

    Communication();
    ~Communication() = default;

    /// @brief Start serial communication
    void begin();
    /// @brief Receive and process incoming packets
    void update();
    /// @brief Change the serial baudrate
    void change_baudrate(uint32_t baudrate);

    /// @brief Send a packet with given command and data
    void send_packet(Command command, const uint8_t* data = nullptr, uint16_t size = 0);
    void send_packet(Command command, const std::vector<uint8_t>& data) {
        send_packet(command, data.data(), data.size());
    }
    void send_err(ErrorCode code);
    void send_log(const char* message);
    void send_log(const std::string& message) {
        send_log(message.c_str());
    }

    bool transfer_in_progress() const {
        return _transfer_watchdog_task_handle != nullptr;
    }

    uint32_t last_packet_time() const {
        return _last_in_packet_time;
    }

private:
    /// @brief Creates all parent directories for a given path
    /// @param full_path File path
    /// @return `bool` success
    static bool ensure_parent_dirs(const std::string& full_path);

    /// @brief Calculates the checksum of a data buffer
    /// @param data Pointer to the data buffer
    /// @param size Size of the data buffer
    /// @return Checksum value
    uint8_t calculate_checksum(const uint8_t* data, size_t size);
    
    /// @brief Call for all incoming packets
    /// @param packet 
    /// @return `true` if the packet was handled and should not be processed further
    bool handle_file_transfer(const packet_t& packet);
    
    /// @brief Start receiving a file. Handles errors.
    /// @param path Path where the file will be stored
    /// @param total_size Total size of the file
    /// @return `true` if the upload was started successfully
    bool start_file_upload(const std::string& path, uint32_t total_size);

    /// @brief Receive a chunk of file data. Handles errors.
    /// @param data The data chunk to receive
    /// @return `true` if the data was received successfully
    bool receive_file_data(const std::vector<uint8_t>& data);

    /// @brief Start sending a file
    /// @param path Path of the file to send
    void start_file_download(const std::string& path);

    /// @brief Stop watchdog and replace target file
    void finish_file_transfer();
    
    /// @brief Task responsible for sending the currently open file.
    /// Tries to take `_transfer_waiting_for_ack` semaphore after each chunk.
    void send_image_task();

    /// @brief Delete temp file and clear upload path
    void cancel_transfer();

    /// @brief Starts the transfer watchdog task
    void start_transfer_watchdog();

    /// @brief Deletes the transfer watchdog task
    void stop_transfer_watchdog();

    /// @brief Takes `_transfer_watchdog_reset` semaphore every `PACKET_TIMEOUT_MS` milliseconds.
    /// Cancels the transfer if no data is received in time.
    void transfer_watchdog_task();
    TaskHandle_t _transfer_watchdog_task_handle = nullptr;
    SemaphoreHandle_t _transfer_watchdog_reset;
    SemaphoreHandle_t _transfer_waiting_for_ack;

    static constexpr size_t MAX_PACKET_SIZE = 4096;
    static constexpr size_t TRANSFER_SEND_MAX_CHUNK_SIZE = 512;
    static constexpr uint32_t PACKET_TIMEOUT_MS = 1000;
    static constexpr const char* UPLOAD_TEMP_PATH = "/upload_temp";
    std::string _upload_path;
    uint8_t _rx_buffer[MAX_PACKET_SIZE];
    size_t _rx_index = 0;
    bool _in_packet = false;
    uint32_t _last_in_data_time = 0;
    uint32_t _last_in_packet_time = 0;
    uint16_t _expected_size = 0;
    
    File _file;
    uint32_t _upload_bytes_received = 0;
    uint32_t _upload_total_size = 0;
};

#endif