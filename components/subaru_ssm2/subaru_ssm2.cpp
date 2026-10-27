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

void SubaruSSM2Component::flush_sniff_buffer_() {
  if (this->sniff_buffer_.empty())
    return;

  if (millis() - this->sniff_last_rx_at_ < this->sniff_flush_ms_)
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
  const uint8_t n = cfg.data_length;

  // SSM2 "read addresses" (0xA8) returns exactly ONE byte per requested
  // 3-byte address, so an N-byte value needs N consecutive addresses in a
  // single request. Convention: the table address is the least-significant
  // (last) byte, so we ask for (addr-N+1 .. addr) ascending, which makes the
  // ECU return the bytes in big-endian (MSB first) order.
  //
  // Frame: header(0x80) dest(0x10 ECU) src(0xF0 tester) len cmd(0xA8)
  //        responseType(0x00 = single) [00 00 addr]*N checksum
  // len counts cmd + responseType + N*3 address bytes.
  //
  // NOTE: the address span/order is still an assumption and must be verified
  // against a real ECU capture (ROADMAP Phase 3/4).
  std::vector<uint8_t> request = {0x80, 0x10, 0xF0};
  request.push_back(static_cast<uint8_t>(2 + n * 3));  // data length
  request.push_back(0xA8);                             // command: read addresses
  request.push_back(0x00);                             // response type: single
  for (uint8_t i = 0; i < n; i++) {
    request.push_back(0x00);
    request.push_back(0x00);
    request.push_back(static_cast<uint8_t>(parameter - (n - 1) + i));
  }
  request.push_back(this->checksum_(request));
  ESP_LOGV(TAG, "TX request for 0x%02X (%u byte): %s", parameter, n,
           this->bytes_to_hex_(request).c_str());

  // Discard any stale bytes before issuing the new request.
  while (this->available())
    this->read();

  this->write_array(request);
  this->current_parameter_ = parameter;
  this->rx_buffer_.clear();
  this->request_sent_at_ = millis();
  this->state_ = STATE_WAIT_BEFORE_READ;
}

SubaruSSM2Component::ParseResult SubaruSSM2Component::try_parse_response_() {
  auto it = KNOWN_PARAMETERS.find(this->current_parameter_);
  if (it == KNOWN_PARAMETERS.end())
    return PARSE_BAD;
  const SSM2Parameter &cfg = it->second;

  // Locate the ECU response header (0x80 0xF0 0x10). Scanning forward over the
  // leading bytes transparently skips the request echo we receive back on the
  // half-duplex K-line: that echo starts 0x80 0x10 0xF0 and so never matches.
  size_t hdr = 0;
  bool found = false;
  for (; hdr + 4 <= this->rx_buffer_.size(); hdr++) {
    if (this->rx_buffer_[hdr] == 0x80 && this->rx_buffer_[hdr + 1] == 0xF0 &&
        this->rx_buffer_[hdr + 2] == 0x10) {
      found = true;
      break;
    }
  }
  if (!found)
    return PARSE_INCOMPLETE;  // ECU header not seen yet

  const uint8_t payload_len = this->rx_buffer_[hdr + 3];   // status + data bytes
  const size_t total_needed = hdr + 4 + payload_len + 1;   // + checksum
  if (this->rx_buffer_.size() < total_needed)
    return PARSE_INCOMPLETE;  // frame still arriving

  std::vector<uint8_t> frame(this->rx_buffer_.begin() + hdr,
                             this->rx_buffer_.begin() + hdr + 4 + payload_len);
  const uint8_t expected_csum = this->rx_buffer_[hdr + 4 + payload_len];
  if (this->checksum_(frame) != expected_csum) {
    ESP_LOGW(TAG, "Checksum mismatch for 0x%02X (calc 0x%02X != got 0x%02X) frame: %s",
             this->current_parameter_, this->checksum_(frame), expected_csum,
             this->bytes_to_hex_(frame).c_str());
    return PARSE_BAD;
  }

  // Payload byte 0 is the status (0xE8 = response to A8). Data starts at +1.
  if (payload_len < 1 + cfg.data_length) {
    ESP_LOGW(TAG, "Payload too short for 0x%02X (len %u, need %u)", this->current_parameter_,
             (unsigned) payload_len, (unsigned) (1 + cfg.data_length));
    return PARSE_BAD;
  }
  const uint8_t status = this->rx_buffer_[hdr + 4];
  if (status != 0xE8) {
    ESP_LOGW(TAG, "Unexpected response status 0x%02X for 0x%02X; raw frame: %s", status,
             this->current_parameter_, this->bytes_to_hex_(frame).c_str());
    return PARSE_BAD;
  }

  int32_t raw = 0;
  for (uint8_t i = 0; i < cfg.data_length; i++)
    raw = (raw << 8) | this->rx_buffer_[hdr + 5 + i];  // data starts after status

  // Sign-extend if needed. Guarded to <4 bytes so the 1u<<bits shift below
  // can never hit 32-bit undefined behaviour.
  if (cfg.is_signed && cfg.data_length > 0 && cfg.data_length < 4) {
    const uint8_t bits = cfg.data_length * 8;
    const uint32_t sign_bit = static_cast<uint32_t>(1) << (bits - 1);
    if (static_cast<uint32_t>(raw) & sign_bit)
      raw -= static_cast<int32_t>(static_cast<uint32_t>(1) << bits);
  }

  const float value = static_cast<float>(raw) * cfg.scale + cfg.offset;
  auto sensor_it = this->parameter_sensors_.find(this->current_parameter_);
  if (sensor_it != this->parameter_sensors_.end())
    sensor_it->second->publish_state(value);
  ESP_LOGD(TAG, "%s (0x%02X) -> %.3f %s", cfg.name != nullptr ? cfg.name : "?",
           this->current_parameter_, value, cfg.unit != nullptr ? cfg.unit : "");
  return PARSE_OK;
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

    case STATE_READING: {
      // Try to parse a complete frame out of whatever has arrived. Driven by
      // the frame's own length field instead of a fixed byte count, so a
      // leading request echo or trailing bytes no longer desync the reader.
      const ParseResult res = this->try_parse_response_();
      if (res != PARSE_INCOMPLETE) {
        this->state_ = STATE_IDLE;  // decoded, or hard error – move to next
      } else if (millis() - this->request_sent_at_ > this->response_timeout_ms_) {
        ESP_LOGW(TAG, "Timeout reading parameter 0x%02X (got %u bytes)", this->current_parameter_,
                 (unsigned) this->rx_buffer_.size());
        this->state_ = STATE_IDLE;
      }
      break;
    }
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
