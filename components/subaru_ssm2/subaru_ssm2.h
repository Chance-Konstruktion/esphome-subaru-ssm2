#pragma once

#include <map>
#include <string>
#include <vector>

#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/uart/uart.h"
#include "esphome/core/component.h"
#include "ssm2_parameters.h"

namespace esphome {
namespace subaru_ssm2 {

class SubaruSSM2Component : public PollingComponent, public uart::UARTDevice {
 public:
  SubaruSSM2Component(uart::UARTComponent *parent) : uart::UARTDevice(parent) {}

  void setup() override;
  void loop() override;
  void update() override;
  void dump_config() override;

  void set_request_delay(uint32_t request_delay_ms) { this->request_delay_ms_ = request_delay_ms; }
  void set_response_timeout(uint32_t timeout_ms) { this->response_timeout_ms_ = timeout_ms; }
  void set_sniff_mode(bool sniff_mode) { this->sniff_mode_ = sniff_mode; }
  void set_motor_running_sensor(binary_sensor::BinarySensor *sensor) { this->motor_running_sensor_ = sensor; }
  void add_parameter_sensor(uint8_t parameter, sensor::Sensor *sensor);

 protected:
  enum State {
    STATE_IDLE,
    STATE_WAIT_BEFORE_READ,
    STATE_READING,
  };

  uint8_t checksum_(const std::vector<uint8_t> &frame) const;
  bool should_poll_() const;
  void send_request_(uint8_t parameter);
  void process_response_();
  void flush_sniff_buffer_(bool force = false);
  std::string bytes_to_hex_(const std::vector<uint8_t> &bytes) const;

  std::map<uint8_t, sensor::Sensor *> parameter_sensors_;
  binary_sensor::BinarySensor *motor_running_sensor_{nullptr};
  bool sniff_mode_{false};
  uint32_t sniff_flush_ms_{60};
  uint32_t request_delay_ms_{50};
  uint32_t response_timeout_ms_{200};

  // Non-blocking state machine state.
  State state_{STATE_IDLE};
  std::vector<uint8_t> rx_buffer_;
  std::vector<uint8_t> pending_params_;
  size_t pending_index_{0};
  uint8_t current_parameter_{0};
  size_t expected_response_len_{0};
  uint32_t request_sent_at_{0};
  uint32_t sniff_last_rx_at_{0};
  std::vector<uint8_t> sniff_buffer_;
};

}  // namespace subaru_ssm2
}  // namespace esphome
