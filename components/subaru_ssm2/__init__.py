import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import binary_sensor, sensor, uart
from esphome.const import (
    CONF_ID,
    CONF_PARAMETERS,
    STATE_CLASS_MEASUREMENT,
)

AUTO_LOAD = ["sensor"]
DEPENDENCIES = ["uart"]

CONF_UART_ID = "uart"
CONF_REQUEST_DELAY = "request_delay"
CONF_RESPONSE_TIMEOUT = "response_timeout"
CONF_MOTOR_RUNNING_SENSOR = "motor_running_sensor"
CONF_PARAMETER_ID = "id"

subaru_ssm2_ns = cg.esphome_ns.namespace("subaru_ssm2")
SubaruSSM2Component = subaru_ssm2_ns.class_(
    "SubaruSSM2Component", cg.PollingComponent, uart.UARTDevice
)

# Parameter schema = full sensor schema PLUS the SSM2 parameter address.
# This is critical: sensor.new_sensor() needs a validated config dict that
# already contains a generated CONF_ID, otherwise codegen crashes.
PARAMETER_SCHEMA = sensor.sensor_schema(
    accuracy_decimals=2,
    state_class=STATE_CLASS_MEASUREMENT,
).extend(
    {
        cv.Required(CONF_PARAMETER_ID): cv.hex_uint8_t,
    }
)

CONFIG_SCHEMA = (
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(SubaruSSM2Component),
            cv.Required(CONF_UART_ID): cv.use_id(uart.UARTComponent),
            cv.Optional(
                CONF_REQUEST_DELAY, default="50ms"
            ): cv.positive_time_period_milliseconds,
            cv.Optional(
                CONF_RESPONSE_TIMEOUT, default="200ms"
            ): cv.positive_time_period_milliseconds,
            cv.Optional(CONF_MOTOR_RUNNING_SENSOR): cv.use_id(
                binary_sensor.BinarySensor
            ),
            cv.Required(CONF_PARAMETERS): cv.ensure_list(PARAMETER_SCHEMA),
        }
    ).extend(cv.polling_component_schema("5s"))
)


async def to_code(config):
    parent = await cg.get_variable(config[CONF_UART_ID])
    var = cg.new_Pvariable(config[CONF_ID], parent)
    await cg.register_component(var, config)

    cg.add(var.set_request_delay(config[CONF_REQUEST_DELAY].total_milliseconds))
    cg.add(var.set_response_timeout(config[CONF_RESPONSE_TIMEOUT].total_milliseconds))

    if CONF_MOTOR_RUNNING_SENSOR in config:
        motor_running_sensor = await cg.get_variable(
            config[CONF_MOTOR_RUNNING_SENSOR]
        )
        cg.add(var.set_motor_running_sensor(motor_running_sensor))

    for parameter_config in config[CONF_PARAMETERS]:
        sens = await sensor.new_sensor(parameter_config)
        cg.add(var.add_parameter_sensor(int(parameter_config[CONF_PARAMETER_ID]), sens))
