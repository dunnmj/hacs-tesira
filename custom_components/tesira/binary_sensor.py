"""Binary sensor platform for Tesira state blocks."""

import logging

import voluptuous as vol

from homeassistant.components.binary_sensor import (
    PLATFORM_SCHEMA as BINARY_SENSOR_PLATFORM_SCHEMA,
    BinarySensorEntity,
)
from homeassistant.const import CONF_IP_ADDRESS, CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

from . import get_name_from_instance_id, get_tesira
from .tesira import CommandFailedException, Tesira

_LOGGER = logging.getLogger(__name__)
DOMAIN = "tesira_ttp"
CONF_LOGIC_METERS = "logic_meters"

PLATFORM_SCHEMA = BINARY_SENSOR_PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_IP_ADDRESS): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_NAME): cv.string,
        vol.Optional(CONF_LOGIC_METERS): vol.All(
            cv.ensure_list,
            [cv.string],
        ),
    }
)


async def async_setup_platform(
    hass: HomeAssistant, config: ConfigType, async_add_entities, discovery_info=None
):
    """Set up the Tesira binary sensor platform."""
    config = discovery_info
    _LOGGER.debug("Binary sensor: %s", config)
    if config.get(CONF_LOGIC_METERS, []) == []:
        return

    t = await get_tesira(
        hass, config[CONF_IP_ADDRESS], config[CONF_USERNAME], config[CONF_PASSWORD]
    )
    serial = await t.serial_number()

    for instance_id in config[CONF_LOGIC_METERS]:
        try:
            async_add_entities(
                [await TesiraStateBinarySensor.new(t, instance_id, serial)]
            )
        except CommandFailedException as e:
            _LOGGER.error(
                "Error initializing binary sensor %s: %s", instance_id, str(e)
            )
            continue


class TesiraStateBinarySensor(BinarySensorEntity):
    """Representation of a Tesira state block as a binary sensor."""

    _attr_should_poll = False

    def __init__(self, tesira: Tesira, instance_id: str, serial_number: int) -> None:
        self._tesira = tesira
        self._instance_id = instance_id
        self._serial = serial_number
        self._attr_unique_id = f"{serial_number}_{instance_id.replace(' ', '_')}_state"
        self._attr_name = get_name_from_instance_id(instance_id)

    @classmethod
    async def new(cls, tesira: Tesira, instance_id: str, serial_number: int):
        """Create and initialize a TesiraStateBinarySensor entity."""
        self = cls(tesira, instance_id, serial_number)
        await tesira.subscribe(instance_id, "state 1", self._state_callback)
        return self

    def try_write_state(self):
        """Write state if entity is added to hass."""
        if self.hass:
            self.async_write_ha_state()

    def _state_callback(self, value):
        """Handle state update from device."""
        self._attr_is_on = value.strip() == "true"
        self.try_write_state()
