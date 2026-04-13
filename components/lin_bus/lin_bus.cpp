#include "lin_bus.h"

#include "lin_frames.h"
#include "esphome/core/log.h"

namespace esphome {
namespace lin_bus {

static const char *const TAG = "lin_bus";

void LINBusComponent::setup() {
  this->current_data_.reserve(8);
  this->last_byte_time_ = millis();
}

void LINBusComponent::dump_config() {
  ESP_LOGCONFIG(TAG, "LIN Bus:");
  ESP_LOGCONFIG(TAG, "  Frame timeout:      %u ms", this->frame_timeout_ms_);
  ESP_LOGCONFIG(TAG, "  Number of mappings: %u", (unsigned) this->mappings_.size());
}

void LINBusComponent::add_mapping(uint8_t lin_id, sensor::Sensor *sensor, float scale, float offset,
                                  uint8_t data_length, bool is_signed) {
  LINMapping m = {lin_id, sensor, scale, offset, data_length, is_signed};
  this->mappings_[lin_id] = m;
}

void LINBusComponent::loop() {
  bool got_byte = false;
  while (this->available()) {
    uint8_t byte = this->read();
    this->process_byte_(byte);
    got_byte = true;
  }

  // Reset frame state if we are mid-frame and no bytes have arrived for a while.
  // Skip the timeout check entirely while idle (state_ == WAIT_FOR_BREAK) so we
  // don't spin on the very first loop() call when last_byte_time_ is zero.
  if (!got_byte && this->state_ != WAIT_FOR_BREAK &&
      (millis() - this->last_byte_time_) > this->frame_timeout_ms_) {
    ESP_LOGV(TAG, "LIN frame timeout, resetting state");
    this->state_ = WAIT_FOR_BREAK;
    this->current_data_.clear();
  }
}

void LINBusComponent::process_byte_(uint8_t byte) {
  this->last_byte_time_ = millis();

  switch (this->state_) {
    case WAIT_FOR_BREAK:
      // A LIN break is at least 13 dominant bits; on a UART this typically
      // surfaces as one or more 0x00 bytes (often with a framing error).
      if (byte == 0x00) {
        this->state_ = WAIT_FOR_SYNC;
      }
      break;

    case WAIT_FOR_SYNC:
      if (byte == 0x55) {
        this->state_ = READ_ID;
      } else if (byte != 0x00) {
        // Unexpected, restart frame search.
        this->state_ = WAIT_FOR_BREAK;
      }
      break;

    case READ_ID: {
      this->current_id_ = byte & 0x3F;
      auto known = KNOWN_LIN_FRAMES.find(this->current_id_);
      auto user = this->mappings_.find(this->current_id_);
      if (user != this->mappings_.end()) {
        this->current_data_length_ = user->second.data_length;
      } else if (known != KNOWN_LIN_FRAMES.end()) {
        this->current_data_length_ = known->second.default_length;
      } else {
        // Unknown ID – skip to next frame.
        this->state_ = WAIT_FOR_BREAK;
        break;
      }
      this->current_data_.clear();
      this->state_ = READ_DATA;
      break;
    }

    case READ_DATA:
      this->current_data_.push_back(byte);
      if (this->current_data_.size() >= this->current_data_length_) {
        this->state_ = READ_CHECKSUM;
      }
      break;

    case READ_CHECKSUM:
      // We currently don't validate the LIN checksum (classic vs enhanced
      // depends on the protocol version). Decode the frame as-is.
      this->decode_frame_();
      this->state_ = WAIT_FOR_BREAK;
      break;
  }
}

void LINBusComponent::decode_frame_() {
  auto it = this->mappings_.find(this->current_id_);
  if (it == this->mappings_.end()) {
    ESP_LOGV(TAG, "Unmapped LIN ID 0x%02X", this->current_id_);
    return;
  }

  const LINMapping &m = it->second;
  if (this->current_data_.size() < m.data_length) {
    ESP_LOGW(TAG, "LIN ID 0x%02X: short frame (%u bytes, expected %u)", this->current_id_,
             (unsigned) this->current_data_.size(), m.data_length);
    return;
  }

  // LIN data is little-endian on the wire.
  int32_t raw = 0;
  for (int i = m.data_length - 1; i >= 0; i--) {
    raw = (raw << 8) | this->current_data_[i];
  }
  if (m.is_signed) {
    const uint8_t bits = m.data_length * 8;
    const int32_t sign_bit = static_cast<int32_t>(1UL << (bits - 1));
    if (raw & sign_bit)
      raw -= static_cast<int32_t>(1UL << bits);
  }

  float value = static_cast<float>(raw) * m.scale + m.offset;
  m.sensor->publish_state(value);

  ESP_LOGD(TAG, "LIN 0x%02X = %.3f", this->current_id_, value);
}

}  // namespace lin_bus
}  // namespace esphome
