import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TesiraConfigEntry, get_name_from_instance_id
from .const import CONF_LOGIC_STATES, CONF_MUTES
from .tesira import CommandFailedException, Tesira

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TesiraConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Tesira switch entities from a config entry."""
    tesira = entry.runtime_data
    options = entry.options
    serial = await tesira.serial_number()

    entities: list[SwitchEntity] = []

    for instance_id in options.get(CONF_MUTES, []):
        try:
            input_map = await tesira.inputs(instance_id, "numChannels", "label")
            for input_name, input_number in input_map.items():
                entities.append(
                    await TesiraMute.new(
                        tesira, instance_id, serial, input_number, input_name
                    )
                )
        except CommandFailedException as e:
            _LOGGER.error("Error initializing mute control %s: %s", instance_id, str(e))
            continue

    for instance_id in options.get(CONF_LOGIC_STATES, []):
        try:
            entities.append(await TesiraLogicState.new(tesira, instance_id, serial))
        except CommandFailedException as e:
            _LOGGER.error("Error initializing logic state %s: %s", instance_id, str(e))
            continue

    async_add_entities(entities)


class TesiraMute(SwitchEntity):
    def __init__(
        self, tesira: Tesira, instance_id, serial_number, input_number, input_name
    ) -> None:
        self._tesira = tesira
        self._serial = serial_number
        self._instance_id = instance_id
        self._input_number = input_number
        self._attr_name = get_name_from_instance_id(instance_id) + " - " + input_name
        self._attr_unique_id = (
            f"{serial_number}_{instance_id.replace(' ', '_')}_{input_number}"
        )

    @classmethod
    async def new(
        cls, tesira: Tesira, instance_id, serial_number, input_number, input_name
    ):
        self = cls(tesira, instance_id, serial_number, input_number, input_name)
        await tesira.subscribe(instance_id, f"mute {input_number}", self._mute_callback)
        return self

    def try_write_state(self):
        if self.hass:
            self.async_write_ha_state()

    def _mute_callback(self, value):
        self._attr_is_on = value != "true"
        self.try_write_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn input on."""
        await self._tesira.set_mute(self._instance_id, self._input_number, False)

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn input off."""
        await self._tesira.set_mute(self._instance_id, self._input_number, True)


class TesiraLogicState(SwitchEntity):
    """Representation of a Tesira logic state block as a switch."""

    _attr_should_poll = False

    def __init__(self, tesira: Tesira, instance_id: str, serial_number: int) -> None:
        self._tesira = tesira
        self._instance_id = instance_id
        self._serial = serial_number
        self._attr_unique_id = f"{serial_number}_{instance_id.replace(' ', '_')}_state"
        self._attr_name = get_name_from_instance_id(instance_id)

    @classmethod
    async def new(cls, tesira: Tesira, instance_id: str, serial_number: int):
        """Create and initialize a TesiraLogicState entity."""
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

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Set logic state to true."""
        await self._tesira.set_state(self._instance_id, True)

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Set logic state to false."""
        await self._tesira.set_state(self._instance_id, False)
