"""Number platform for Tesira Level blocks."""

import logging
import math

from numpy import double
import voluptuous as vol

from homeassistant.components.number import (
    PLATFORM_SCHEMA as NUMBER_PLATFORM_SCHEMA,
    NumberEntity,
)
from homeassistant.const import CONF_IP_ADDRESS, CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

from . import get_name_from_instance_id, get_tesira
from .tesira import CommandFailedException, Tesira

_LOGGER = logging.getLogger(__name__)
DOMAIN = "tesira_ttp"
CONF_LEVELS = "levels"

PLATFORM_SCHEMA = NUMBER_PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_IP_ADDRESS): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_NAME): cv.string,
        vol.Optional(CONF_LEVELS): vol.All(
            cv.ensure_list,
            [cv.string],
        ),
    }
)


async def async_setup_platform(
    hass: HomeAssistant, config: ConfigType, async_add_entities, discovery_info=None
):
    """Set up the Tesira number platform."""
    config = discovery_info
    _LOGGER.debug("Number: %s", config)
    if config.get(CONF_LEVELS, []) == []:
        return

    t = await get_tesira(
        hass, config[CONF_IP_ADDRESS], config[CONF_USERNAME], config[CONF_PASSWORD]
    )
    serial = await t.serial_number()

    for instance_id in config[CONF_LEVELS]:
        try:
            async_add_entities([await TesiraLevel.new(t, instance_id, serial)])
        except CommandFailedException as e:
            _LOGGER.error("Error initializing level %s: %s", instance_id, str(e))
            continue


class TesiraLevel(NumberEntity):
    """Representation of a Tesira Level block as a number entity."""

    _attr_should_poll = False
    _attr_mode = "slider"
    _attr_native_min_value = 0.0
    _attr_native_max_value = 100.0
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = "%"

    @staticmethod
    def volume_to_db(volume: float) -> float:
        """Convert a 0-100 percentage to dB."""
        return max(30 * (math.log2(max(volume / 100, 0.001))), -100)

    @staticmethod
    def db_to_volume(db: float) -> float:
        """Convert dB to a 0-100 percentage."""
        if math.pow(2, (double(db) / 30)) < 0.1:
            return 0.0
        return round(math.pow(2, (double(db) / 30)) * 100)

    def __init__(self, tesira: Tesira, instance_id: str, serial_number: int) -> None:
        self._tesira = tesira
        self._serial = serial_number
        self._instance_id = instance_id
        self._attr_unique_id = f"{serial_number}_{instance_id.replace(' ', '_')}_level"
        self._attr_name = get_name_from_instance_id(instance_id)

    @classmethod
    async def new(cls, tesira: Tesira, instance_id: str, serial_number: int):
        """Create and initialize a TesiraLevel entity."""
        self = cls(tesira, instance_id, serial_number)

        # Get initial state
        try:
            current_level = await tesira.get_level(instance_id)
            self._attr_native_value = self.db_to_volume(current_level)
        except CommandFailedException as e:
            _LOGGER.error("Error getting initial level for %s: %s", instance_id, str(e))

        # Subscribe to updates
        await tesira.subscribe(instance_id, "level 1", self._level_callback)

        return self

    def try_write_state(self):
        """Write state if entity is added to hass."""
        if self.hass:
            self.async_write_ha_state()

    def _level_callback(self, value):
        """Handle level update from device."""
        self._attr_native_value = self.db_to_volume(float(value))
        self.try_write_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set the level value as a percentage."""
        await self._tesira.set_level(self._instance_id, self.volume_to_db(value))
        self._attr_native_value = value
        self.async_write_ha_state()
