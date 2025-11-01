#ifndef CONTROLLER_H
#define CONTROLLER_H

#pragma once

#include "Config.h"
#include "ConfigLoader.h"
#include "Communication.h"
#include "Segment.h"

#include <cinttypes>
#include <vector>
#include <memory>

class Controller {
public:
    Controller();
    ~Controller() = default;

    void begin();

private:
    void create_tasks();
    void init_hardware();
    void handle_command(Communication::packet_t packet);
    void apply_config_changes(const DeviceConfig& new_config);
    void on_file_received(const std::string& path);
    void wake_up();
    void sleep();

    static void comm_task(void* param);
    static void segment_task(void* param);
    static void watchdog_task(void* param);

    ConfigLoader _config_loader;
    std::shared_ptr<DeviceConfig> _device_config;
    std::vector<std::unique_ptr<Segment>> _segments;
    Communication _communication;
    bool _is_awake;
    TaskHandle_t _segment_task_handle;
    TaskHandle_t _comm_task_handle;
    TaskHandle_t _watchdog_task_handle;

    static constexpr uint32_t PING_TIMEOUT_MS = 10000;
    static constexpr uint8_t SLIDER_POLL_INTERVAL_MS = 50;
};

#endif