"""Number platform for Tesira Level blocks."""

import logging
import math

from numpy import double

from homeassistant.components.number import NumberEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TesiraConfigEntry, get_name_from_instance_id
from .const import CONF_LEVELS
from .tesira import CommandFailedException, Tesira

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TesiraConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Tesira number entities from a config entry."""
    tesira = entry.runtime_data
    options = entry.options
    serial = await tesira.serial_number()

    entities: list[NumberEntity] = []

    for instance_id in options.get(CONF_LEVELS, []):
        try:
            entities.append(await TesiraLevel.new(tesira, instance_id, serial))
        except CommandFailedException as e:
            _LOGGER.error("Error initializing level %s: %s", instance_id, str(e))
            continue

    async_add_entities(entities)


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
