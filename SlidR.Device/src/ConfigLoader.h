#ifndef CONFIGLOADER_H
#define CONFIGLOADER_H

#pragma once

#include "Config.h"

#include <cinttypes>
#include <memory>
#include <vector>

class ConfigLoader {
public:
    ConfigLoader() = default;
    ~ConfigLoader() = default;

    /// @brief Load device configuration from the filesystem.
    /// @return A shared pointer to the loaded DeviceConfig, or nullptr on failure.
    std::shared_ptr<DeviceConfig> load();
    /// @brief Load the default device configuration.
    /// @return A shared pointer to the default DeviceConfig.
    std::shared_ptr<DeviceConfig> load_default();
    /// @brief Save the device configuration to the filesystem.
    /// @param config The DeviceConfig to save.
    /// @return `bool` - success
    bool save(const DeviceConfig& config);

    /// @brief Deserialize device configuration from byte array.
    /// @param data The byte array containing the serialized configuration.
    /// @return A shared pointer to the deserialized DeviceConfig, or nullptr on failure.
    std::shared_ptr<DeviceConfig> from_bytes(const std::vector<uint8_t>& data);
    /// @brief Serialize device configuration to byte array.
    /// @param config The DeviceConfig to serialize.
    /// @return A byte array containing the serialized configuration.
    std::vector<uint8_t> to_bytes(const DeviceConfig& config);

private:
    static constexpr const char* CONFIG_PATH = "/config.bin";
    static constexpr size_t CONFIG_VERSION = 1;
};

#endif