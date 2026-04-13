#pragma once

#include <map>
#include <string>

#include "esphome/components/one_wire/one_wire.h"
#include "esphome/core/component.h"

namespace esphome {
namespace onewire_auto {

class OneWireAutoComponent : public PollingComponent {
 public:
  void setup() override;
  void update() override;
  void loop() override;
  void dump_config() override;

  void set_one_wire_bus(one_wire::OneWireBus *bus) { this->bus_ = bus; }
  void set_discovery_prefix(const std::string &prefix) { this->prefix_ = prefix; }
  void set_strong_pullup(bool strong_pullup) { this->strong_pullup_ = strong_pullup; }
  void set_scan_on_boot(bool scan_on_boot) { this->scan_on_boot_ = scan_on_boot; }

  void perform_scan();

 protected:
  one_wire::OneWireBus *bus_{nullptr};
  std::string prefix_{"1wire"};
  bool strong_pullup_{false};
  bool scan_on_boot_{true};
  bool scan_in_progress_{false};
  std::map<uint64_t, std::string> discovered_devices_;
};

}  // namespace onewire_auto
}  // namespace esphome
