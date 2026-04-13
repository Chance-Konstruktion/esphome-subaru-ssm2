#include "subaru_ssm2.h"

#include <cstdio>

#include "esphome/core/log.h"

namespace esphome {
namespace subaru_ssm2 {

static const char *const TAG = "subaru_ssm2";

void SubaruSSM2Component::setup() {
  // Drain any boot-time noise on the UART.
  while (this->available())
    this->read();
  this->sniff_buffer_.clear();
}

void SubaruSSM2Component::dump_config() {
  ESP_LOGCONFIG(TAG, "Subaru SSM2:");
  ESP_LOGCONFIG(TAG, "  Mode:             %s", this->sniff_mode_ ? "sniff" : "normal");
  ESP_LOGCONFIG(TAG, "  Request delay:    %u ms", this->request_delay_ms_);
  ESP_LOGCONFIG(TAG, "  Response timeout: %u ms", this->response_timeout_ms_);
  LOG_UPDATE_INTERVAL(this);
  if (this->motor_running_sensor_ != nullptr) {
    LOG_BINARY_SENSOR("  ", "Motor running sensor", this->motor_running_sensor_);
  }
  ESP_LOGCONFIG(TAG, "  Configured parameters: %u", (unsigned) this->parameter_sensors_.size());
}

void SubaruSSM2Component::add_parameter_sensor(uint8_t parameter, sensor::Sensor *sensor) {
  this->parameter_sensors_[parameter] = sensor;
}

uint8_t SubaruSSM2Component::checksum_(const std::vector<uint8_t> &frame) const {
  // SSM2 checksum is the simple 8-bit sum of all bytes (modulo 256), NOT
  // the bitwise inverse. The previous implementation inverted the sum,
  // which would never match a real ECU response.
  uint16_t sum = 0;
  for (uint8_t b : frame)
    sum += b;
  return static_cast<uint8_t>(sum & 0xFF);
}

std::string SubaruSSM2Component::bytes_to_hex_(const std::vector<uint8_t> &bytes) const {
  if (bytes.empty())
    return "";

  std::string out;
  out.reserve(bytes.size() * 3);
  char buf[5];
  for (size_t i = 0; i < bytes.size(); i++) {
    std::snprintf(buf, sizeof(buf), "%02X", bytes[i]);
    out.append(buf);
    if (i + 1 < bytes.size())
      out.push_back(' ');
  }
  return out;
}

void SubaruSSM2Component::flush_sniff_buffer_(bool force) {
  if (this->sniff_buffer_.empty())
    return;

  if (!force && (millis() - this->sniff_last_rx_at_ < this->sniff_flush_ms_))
    return;

  ESP_LOGD(TAG, "Sniff RX (%u bytes): %s", (unsigned) this->sniff_buffer_.size(),
           this->bytes_to_hex_(this->sniff_buffer_).c_str());
  this->sniff_buffer_.clear();
}

bool SubaruSSM2Component::should_poll_() const {
  if (this->motor_running_sensor_ == nullptr)
    return true;
  return this->motor_running_sensor_->state;
}

void SubaruSSM2Component::send_request_(uint8_t parameter) {
  auto it = KNOWN_PARAMETERS.find(parameter);
  if (it == KNOWN_PARAMETERS.end()) {
    ESP_LOGW(TAG, "Unknown parameter 0x%02X – skipping", parameter);
    this->state_ = STATE_IDLE;
    return;
  }
  const SSM2Parameter &cfg = it->second;

  // SSM2 single-address read request: header(0x80), dest(0x10 ECU),
  // src(0xF0 tester), data length, command(0xA8), pad(0x00),
  // address bytes (3-byte address; we only use the low byte here),
  // checksum.
  std::vector<uint8_t> request = {
      0x80, 0x10, 0xF0, 0x05, 0xA8, 0x00, 0x00, 0x00, parameter,
  };
  request.push_back(this->checksum_(request));
  ESP_LOGV(TAG, "TX request for 0x%02X: %s", parameter, this->bytes_to_hex_(request).c_str());

  // Discard any stale bytes before issuing the new request.
  while (this->available())
    this->read();

  this->write_array(request);
  this->current_parameter_ = parameter;
  // Header(5) + echo of payload bytes is implementation-dependent on K-Line
  // sniffers. We accept any length >= header(5) + 1 status + data_length + 1 checksum.
  this->expected_response_len_ = static_cast<size_t>(7 + cfg.data_length);
  this->rx_buffer_.clear();
  this->rx_buffer_.reserve(this->expected_response_len_);
  this->request_sent_at_ = millis();
  this->state_ = STATE_WAIT_BEFORE_READ;

  ESP_LOGV(TAG, "Sent SSM2 request for 0x%02X (expecting %u bytes)", parameter,
           (unsigned) this->expected_response_len_);
}

void SubaruSSM2Component::process_response_() {
  auto it = KNOWN_PARAMETERS.find(this->current_parameter_);
  if (it == KNOWN_PARAMETERS.end()) {
    this->state_ = STATE_IDLE;
    return;
  }
  const SSM2Parameter &cfg = it->second;

  // Find ECU response header: 0x80 0xF0 0x10 (ECU -> tester).
  size_t hdr = 0;
  bool found = false;
  for (; hdr + 5 <= this->rx_buffer_.size(); hdr++) {
    if (this->rx_buffer_[hdr] == 0x80 && this->rx_buffer_[hdr + 1] == 0xF0 &&
        this->rx_buffer_[hdr + 2] == 0x10) {
      found = true;
      break;
    }
  }
  if (!found) {
    ESP_LOGW(TAG, "No ECU header found for 0x%02X", this->current_parameter_);
    this->state_ = STATE_IDLE;
    return;
  }

  const uint8_t payload_len = this->rx_buffer_[hdr + 3];
  const size_t total_needed = hdr + 4 + payload_len + 1;  // header + len + payload + checksum
  if (this->rx_buffer_.size() < total_needed) {
    ESP_LOGW(TAG, "Truncated response for 0x%02X (got %u, need %u)", this->current_parameter_,
             (unsigned) this->rx_buffer_.size(), (unsigned) total_needed);
    this->state_ = STATE_IDLE;
    return;
  }

  std::vector<uint8_t> frame(this->rx_buffer_.begin() + hdr,
                             this->rx_buffer_.begin() + hdr + 4 + payload_len);
  const uint8_t expected_csum = this->rx_buffer_[hdr + 4 + payload_len];
  if (this->checksum_(frame) != expected_csum) {
    ESP_LOGW(TAG, "Checksum mismatch for 0x%02X (calc 0x%02X != got 0x%02X) frame: %s",
             this->current_parameter_, this->checksum_(frame), expected_csum, this->bytes_to_hex_(frame).c_str());
    this->state_ = STATE_IDLE;
    return;
  }

  // Payload byte 0 is the status (0xE8 = response to A8). Data starts at +1.
  if (payload_len < 1 + cfg.data_length) {
    ESP_LOGW(TAG, "Payload too short for 0x%02X", this->current_parameter_);
    this->state_ = STATE_IDLE;
    return;
  }
  const uint8_t status = this->rx_buffer_[hdr + 4];
  if (status != 0xE8) {
    ESP_LOGW(TAG, "Unexpected response status 0x%02X for 0x%02X; raw frame: %s", status,
             this->current_parameter_, this->bytes_to_hex_(frame).c_str());
    this->state_ = STATE_IDLE;
    return;
  }

  int32_t raw = 0;
  for (uint8_t i = 0; i < cfg.data_length; i++) {
    raw = (raw << 8) | this->rx_buffer_[hdr + 4 + 1 + i];
  }
  if (cfg.is_signed) {
    const uint8_t bits = cfg.data_length * 8;
    const int32_t sign_bit = static_cast<int32_t>(1UL << (bits - 1));
    if (raw & sign_bit)
      raw -= static_cast<int32_t>(1UL << bits);
  }

  float value = static_cast<float>(raw) * cfg.scale + cfg.offset;
  auto sensor_it = this->parameter_sensors_.find(this->current_parameter_);
  if (sensor_it != this->parameter_sensors_.end()) {
    sensor_it->second->publish_state(value);
  }
  ESP_LOGD(TAG, "Parameter 0x%02X -> %.3f %s", this->current_parameter_, value,
           cfg.unit != nullptr ? cfg.unit : "");
  this->state_ = STATE_IDLE;
}

void SubaruSSM2Component::loop() {
  if (this->sniff_mode_) {
    while (this->available()) {
      this->sniff_buffer_.push_back(this->read());
      this->sniff_last_rx_at_ = millis();
    }
    this->flush_sniff_buffer_();
    return;
  }

  // Read whatever bytes have arrived; never block.
  while (this->available()) {
    this->rx_buffer_.push_back(this->read());
  }

  switch (this->state_) {
    case STATE_IDLE:
      // Pop the next pending parameter from the queue produced by update().
      if (this->pending_index_ < this->pending_params_.size()) {
        this->send_request_(this->pending_params_[this->pending_index_++]);
      }
      break;

    case STATE_WAIT_BEFORE_READ:
      if (millis() - this->request_sent_at_ >= this->request_delay_ms_) {
        this->state_ = STATE_READING;
      }
      break;

    case STATE_READING:
      if (this->rx_buffer_.size() >= this->expected_response_len_) {
        this->process_response_();
      } else if (millis() - this->request_sent_at_ > this->response_timeout_ms_) {
        ESP_LOGW(TAG, "Timeout reading parameter 0x%02X (got %u bytes)", this->current_parameter_,
                 (unsigned) this->rx_buffer_.size());
        this->state_ = STATE_IDLE;
      }
      break;
  }
}

void SubaruSSM2Component::update() {
  if (this->sniff_mode_) {
    ESP_LOGV(TAG, "Sniff mode active: no requests sent");
    return;
  }

  if (!this->should_poll_()) {
    ESP_LOGD(TAG, "Skipping SSM2 polling while engine is not running");
    return;
  }

  if (this->state_ != STATE_IDLE || this->pending_index_ < this->pending_params_.size()) {
    ESP_LOGW(TAG, "Previous SSM2 polling cycle still running, skipping this update");
    return;
  }

  this->pending_params_.clear();
  this->pending_params_.reserve(this->parameter_sensors_.size());
  for (auto const &entry : this->parameter_sensors_)
    this->pending_params_.push_back(entry.first);
  this->pending_index_ = 0;
}

}  // namespace subaru_ssm2
}  // namespace esphome
