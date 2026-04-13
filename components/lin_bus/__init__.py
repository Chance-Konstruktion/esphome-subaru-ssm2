import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import sensor, uart
from esphome.const import CONF_ID, CONF_UART_ID, STATE_CLASS_MEASUREMENT

DEPENDENCIES = ["uart"]
AUTO_LOAD = ["sensor"]

lin_bus_ns = cg.esphome_ns.namespace("lin_bus")
LINBusComponent = lin_bus_ns.class_(
    "LINBusComponent", cg.Component, uart.UARTDevice
)

CONF_MAPPINGS = "mappings"
CONF_LIN_ID = "lin_id"
CONF_SCALE = "scale"
CONF_OFFSET = "offset"
CONF_DATA_LENGTH = "data_length"
CONF_SIGNED = "signed"
CONF_FRAME_TIMEOUT = "frame_timeout"


def _validate_lin_id(value):
    value = cv.hex_int(value)
    if value < 0x00 or value > 0x3F:
        raise cv.Invalid("lin_id must be between 0x00 and 0x3F")
    return value


# Each mapping is itself a full sensor (so it gets a CONF_ID, name, etc.).
MAPPING_SCHEMA = sensor.sensor_schema(
    accuracy_decimals=2,
    state_class=STATE_CLASS_MEASUREMENT,
).extend(
    {
        cv.Required(CONF_LIN_ID): _validate_lin_id,
        cv.Optional(CONF_SCALE, default=1.0): cv.float_,
        cv.Optional(CONF_OFFSET, default=0.0): cv.float_,
        cv.Optional(CONF_DATA_LENGTH, default=1): cv.one_of(1, 2, 4, int=True),
        cv.Optional(CONF_SIGNED, default=False): cv.boolean,
    }
)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(LINBusComponent),
        cv.Required(CONF_UART_ID): cv.use_id(uart.UARTComponent),
        cv.Optional(
            CONF_FRAME_TIMEOUT, default="20ms"
        ): cv.positive_time_period_milliseconds,
        cv.Required(CONF_MAPPINGS): cv.ensure_list(MAPPING_SCHEMA),
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    parent = await cg.get_variable(config[CONF_UART_ID])
    var = cg.new_Pvariable(config[CONF_ID], parent)
    await cg.register_component(var, config)

    cg.add(var.set_frame_timeout(config[CONF_FRAME_TIMEOUT].total_milliseconds))

    for mapping in config[CONF_MAPPINGS]:
        sens = await sensor.new_sensor(mapping)
        cg.add(
            var.add_mapping(
                int(mapping[CONF_LIN_ID]),
                sens,
                mapping[CONF_SCALE],
                mapping[CONF_OFFSET],
                mapping[CONF_DATA_LENGTH],
                mapping[CONF_SIGNED],
            )
        )
