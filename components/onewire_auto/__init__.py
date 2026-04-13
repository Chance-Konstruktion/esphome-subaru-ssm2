import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import one_wire
from esphome.const import CONF_ID

DEPENDENCIES = ["one_wire"]

onewire_auto_ns = cg.esphome_ns.namespace("onewire_auto")
OneWireAutoComponent = onewire_auto_ns.class_(
    "OneWireAutoComponent", cg.PollingComponent
)

CONF_ONE_WIRE_ID = "one_wire_id"
CONF_DISCOVERY_PREFIX = "discovery_prefix"
CONF_STRONG_PULLUP = "strong_pullup"
CONF_SCAN_ON_BOOT = "scan_on_boot"

# We piggy-back on PollingComponent's own update_interval handling instead of
# re-inventing a separate scan_interval option (the previous version manually
# called set_update_interval, which collided with COMPONENT_SCHEMA defaults).
CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(OneWireAutoComponent),
        cv.Required(CONF_ONE_WIRE_ID): cv.use_id(one_wire.OneWireBus),
        cv.Optional(CONF_DISCOVERY_PREFIX, default="1wire"): cv.string,
        cv.Optional(CONF_STRONG_PULLUP, default=False): cv.boolean,
        cv.Optional(CONF_SCAN_ON_BOOT, default=True): cv.boolean,
    }
).extend(cv.polling_component_schema("60min"))


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)

    one_wire_bus = await cg.get_variable(config[CONF_ONE_WIRE_ID])
    cg.add(var.set_one_wire_bus(one_wire_bus))
    cg.add(var.set_discovery_prefix(config[CONF_DISCOVERY_PREFIX]))
    cg.add(var.set_strong_pullup(config[CONF_STRONG_PULLUP]))
    cg.add(var.set_scan_on_boot(config[CONF_SCAN_ON_BOOT]))
