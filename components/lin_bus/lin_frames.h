#pragma once

#include <cstdint>
#include <map>

namespace esphome {
namespace lin_bus {

struct LINFrameInfo {
  uint8_t id;
  const char *description;
  uint8_t default_length;
  float scale;
  float offset;
  bool is_signed;
};

// Hints for common LIN frame IDs; used as fallback when the user does not
// specify an explicit data_length in their mapping.
static const std::map<uint8_t, LINFrameInfo> KNOWN_LIN_FRAMES = {
    {0x12, {0x12, "Aussentemperatur", 2, 0.1f, -40.0f, true}},
    {0x1E, {0x1E, "Helligkeit", 2, 1.0f, 0.0f, false}},
    {0x1F, {0x1F, "Regenintensitaet", 1, 1.0f, 0.0f, false}},
    {0x2A, {0x2A, "Sitzheizung Stufe", 1, 1.0f, 0.0f, false}},
    {0x33, {0x33, "Fensterposition", 1, 1.0f, 0.0f, false}},
};

}  // namespace lin_bus
}  // namespace esphome
