#pragma once

#include <map>
#include <vector>

#include "esphome/components/sensor/sensor.h"
#include "esphome/components/uart/uart.h"
#include "esphome/core/component.h"

namespace esphome {
namespace lin_bus {

struct LINMapping {
  uint8_t lin_id;
  sensor::Sensor *sensor;
  float scale;
  float offset;
  uint8_t data_length;
  bool is_signed;
};

class LINBusComponent : public Component, public uart::UARTDevice {
 public:
  LINBusComponent(uart::UARTComponent *parent) : uart::UARTDevice(parent) {}

  void setup() override;
  void loop() override;
  void dump_config() override;

  void add_mapping(uint8_t lin_id, sensor::Sensor *sensor, float scale, float offset,
                   uint8_t data_length, bool is_signed);
  void set_frame_timeout(uint32_t timeout_ms) { this->frame_timeout_ms_ = timeout_ms; }

  float get_setup_priority() const override { return setup_priority::LATE; }

 protected:
  enum State {
    WAIT_FOR_BREAK,
    WAIT_FOR_SYNC,
    READ_ID,
    READ_DATA,
    READ_CHECKSUM,
  };

  void process_byte_(uint8_t byte);
  void decode_frame_();

  std::map<uint8_t, LINMapping> mappings_;

  State state_{WAIT_FOR_BREAK};
  uint8_t current_id_{0};
  uint8_t current_data_length_{0};
  std::vector<uint8_t> current_data_;
  uint32_t last_byte_time_{0};
  uint32_t frame_timeout_ms_{20};
};

}  // namespace lin_bus
}  // namespace esphome
