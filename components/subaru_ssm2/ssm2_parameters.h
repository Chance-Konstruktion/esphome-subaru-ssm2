#pragma once

#include <cstdint>
#include <map>

namespace esphome {
namespace subaru_ssm2 {

// Decoding metadata for one SSM2 parameter. Only the fields used by the C++
// side live here:
// //   - name/unit:   used for human-readable debug logs only.
//   - scale/offset/data_length/is_signed: raw -> engineering-unit conversion.
// The sensor's presentation (name shown in HA, device_class, state_class,
// accuracy_decimals) comes entirely from the YAML, so it is NOT duplicated
// here.
//
// NOTE: addresses, scales and offsets below are still UNVERIFIED guesses and
// must be checked against RomRaider/a real ECU capture before release
// (see ROADMAP Phase 4).
struct SSM2Parameter {
  const char *name;
  const char *unit;
  float scale;
  float offset;
  uint8_t data_length;
  bool is_signed;
};

static const std::map<uint8_t, SSM2Parameter> KNOWN_PARAMETERS = {
    {0x08, {"Kühlmitteltemperatur", "°C", 1.0f, -40.0f, 1, false}},
    {0x0A, {"Öltemperatur", "°C", 1.0f, -40.0f, 1, false}},
    {0x0F, {"Motordrehzahl", "rpm", 0.25f, 0.0f, 2, false}},
    {0x11, {"Saugrohrdruck absolut", "bar", 0.001f, 0.0f, 2, false}},
    {0x13, {"Zündzeitpunkt", "°", 0.5f, -64.0f, 1, true}},
    {0x15, {"Batteriespannung ECU", "V", 0.1f, 0.0f, 1, false}},
    {0x16, {"Luftdurchsatz", "g/s", 0.01f, 0.0f, 2, false}},
    {0x17, {"Drosselklappenstellung", "%", 0.392f, 0.0f, 1, false}},
    {0x18, {"Gaspedalstellung", "%", 0.392f, 0.0f, 1, false}},
    {0x1E, {"Ansauglufttemperatur", "°C", 1.0f, -40.0f, 1, false}},
    {0x24, {"Ladedruck relativ", "bar", 0.001f, -1.0f, 2, true}},
    {0x25, {"Boost Target", "bar", 0.001f, 0.0f, 2, false}},
    {0x26, {"Wastegate Duty Cycle", "%", 0.392f, 0.0f, 1, false}},
    {0x2A, {"Tankfüllstand", "%", 0.392f, 0.0f, 1, false}},
    {0x2B, {"Momentanverbrauch", "L/100km", 0.05f, 0.0f, 1, false}},
    {0x2C, {"Durchschnittsverbrauch", "L/100km", 0.05f, 0.0f, 1, false}},
    {0x3C, {"Knock Correction", "°", 0.5f, -16.0f, 1, true}},
    {0x3D, {"IAM", nullptr, 0.0625f, 0.0f, 1, false}},
};

}  // namespace subaru_ssm2
}  // namespace esphome
