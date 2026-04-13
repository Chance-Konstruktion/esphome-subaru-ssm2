#pragma once

#include <cstdint>
#include <map>
#include <string>

namespace esphome {
namespace subaru_ssm2 {

struct SSM2Parameter {
  uint8_t address;
  const char *name;
  const char *unit;
  const char *device_class;
  const char *state_class;
  float scale;
  float offset;
  uint8_t data_length;
  bool is_signed;
};

static const std::map<uint8_t, SSM2Parameter> KNOWN_PARAMETERS = {
    {0x08, {0x08, "Kühlmitteltemperatur", "°C", "temperature", "measurement", 1.0f, -40.0f, 1, false}},
    {0x0A, {0x0A, "Öltemperatur", "°C", "temperature", "measurement", 1.0f, -40.0f, 1, false}},
    {0x0F, {0x0F, "Motordrehzahl", "rpm", nullptr, "measurement", 0.25f, 0.0f, 2, false}},
    {0x11, {0x11, "Saugrohrdruck absolut", "bar", "pressure", "measurement", 0.001f, 0.0f, 2, false}},
    {0x13, {0x13, "Zündzeitpunkt", "°", nullptr, "measurement", 0.5f, -64.0f, 1, true}},
    {0x15, {0x15, "Batteriespannung ECU", "V", "voltage", "measurement", 0.1f, 0.0f, 1, false}},
    {0x16, {0x16, "Luftdurchsatz", "g/s", nullptr, "measurement", 0.01f, 0.0f, 2, false}},
    {0x17, {0x17, "Drosselklappenstellung", "%", nullptr, "measurement", 0.392f, 0.0f, 1, false}},
    {0x18, {0x18, "Gaspedalstellung", "%", nullptr, "measurement", 0.392f, 0.0f, 1, false}},
    {0x1E, {0x1E, "Ansauglufttemperatur", "°C", "temperature", "measurement", 1.0f, -40.0f, 1, false}},
    {0x24, {0x24, "Ladedruck relativ", "bar", "pressure", "measurement", 0.001f, -1.0f, 2, true}},
    {0x25, {0x25, "Boost Target", "bar", "pressure", "measurement", 0.001f, 0.0f, 2, false}},
    {0x26, {0x26, "Wastegate Duty Cycle", "%", nullptr, "measurement", 0.392f, 0.0f, 1, false}},
    {0x2A, {0x2A, "Tankfüllstand", "%", nullptr, "measurement", 0.392f, 0.0f, 1, false}},
    {0x2B, {0x2B, "Momentanverbrauch", "L/100km", nullptr, "measurement", 0.05f, 0.0f, 1, false}},
    {0x2C, {0x2C, "Durchschnittsverbrauch", "L/100km", nullptr, "measurement", 0.05f, 0.0f, 1, false}},
    {0x3C, {0x3C, "Knock Correction", "°", nullptr, "measurement", 0.5f, -16.0f, 1, true}},
    {0x3D, {0x3D, "IAM", nullptr, nullptr, "measurement", 0.0625f, 0.0f, 1, false}},
};

}  // namespace subaru_ssm2
}  // namespace esphome
