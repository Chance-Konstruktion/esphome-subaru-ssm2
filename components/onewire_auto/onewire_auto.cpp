#include "onewire_auto.h"

#include "esphome/core/log.h"

namespace esphome {
namespace onewire_auto {

static const char *const TAG = "onewire_auto";

void OneWireAutoComponent::setup() {
  ESP_LOGI(TAG, "1-Wire Auto-Discovery setup");
  if (this->scan_on_boot_) {
    this->set_timeout(5000, [this]() { this->perform_scan(); });
  }
}

void OneWireAutoComponent::update() {
  if (!this->scan_in_progress_) {
    this->perform_scan();
  }
}

void OneWireAutoComponent::loop() {
  // no-op
}

void OneWireAutoComponent::dump_config() {
  ESP_LOGCONFIG(TAG, "1-Wire Auto-Discovery (prototype):");
  ESP_LOGCONFIG(TAG, "  Discovery Prefix: %s", this->prefix_.c_str());
  ESP_LOGCONFIG(TAG, "  Strong Pullup (requested): %s", this->strong_pullup_ ? "YES" : "NO");
  ESP_LOGCONFIG(TAG, "  Scan on Boot: %s", this->scan_on_boot_ ? "YES" : "NO");
  ESP_LOGCONFIG(TAG, "  Cached discovered devices: %u", this->discovered_devices_.size());
}

void OneWireAutoComponent::perform_scan() {
  if (this->scan_in_progress_)
    return;

  this->scan_in_progress_ = true;

  if (this->bus_ == nullptr) {
    ESP_LOGW(TAG, "No 1-Wire bus configured, skipping scan");
    this->scan_in_progress_ = false;
    return;
  }

  // NOTE: Konzeptnachweis. Die dynamische Erstellung echter Dallas-Sensor-Komponenten
  // zur Laufzeit ist in ESPHome komplex und wird in Phase 3 vollständig umgesetzt.
  ESP_LOGI(TAG, "Prototype scan triggered. Dynamic Dallas entity creation is not enabled yet.");

  this->scan_in_progress_ = false;
}

}  // namespace onewire_auto
}  // namespace esphome
