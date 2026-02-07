import logging
import math

import voluptuous as vol

from homeassistant.components.media_player import (
    PLATFORM_SCHEMA as MEDIA_PLAYER_PLATFORM_SCHEMA,
    MediaPlayerEntity,
    MediaPlayerState,
)
from homeassistant.components.media_player.const import MediaPlayerEntityFeature
from homeassistant.const import CONF_IP_ADDRESS, CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

from . import get_tesira
from .tesira import CommandFailedException, Tesira

DOMAIN = "tesira_ttp"
SERVICE_NAME = "send_command"

_LOGGER = logging.getLogger(__name__)


DEFAULT_PORT = 23

CONF_ZONES = "zones"
CONF_ROUTERS = "routers"
CONF_ROUTER_ID = "router_id"
CONF_LEVEL_BLOCKS = "level_blocks"

PLATFORM_SCHEMA = MEDIA_PLAYER_PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_IP_ADDRESS): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_ZONES): vol.All(
            cv.ensure_list,
            [cv.string],
        ),
        vol.Optional(CONF_ROUTERS): vol.All(
            cv.ensure_list,
            [
                vol.Schema({
                    vol.Required(CONF_ROUTER_ID): cv.string,
                    vol.Required(CONF_LEVEL_BLOCKS): vol.All(
                        cv.ensure_list,
                        [cv.string],
                    ),
                })
            ],
        ),
    }
)


async def send_command(entity, service_call):
    """Send a command to the Tesira."""
    for command in service_call.data["command_strings"]:
        await entity.async_send_command(command)


async def async_setup_platform(
    hass: HomeAssistant, config: ConfigType, async_add_entities, discovery_info=None
):
    """Set up the Tesira platform."""
    _LOGGER.debug("MediaPlayer: %s", config)
    if config == {}:
        return

    ip = config[CONF_IP_ADDRESS]
    source_selector_instance_ids = config[CONF_ZONES]
    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_NAME,
        {
            vol.Required("command_strings"): vol.All(
                cv.ensure_list,
                [cv.string],
            ),
        },
        send_command,
    )
    t = await get_tesira(hass, ip, config[CONF_USERNAME], config[CONF_PASSWORD])
    serial = await t.serial_number()
    # _LOGGER.error("Serial number is %s", str(serial))

    for instance_id in source_selector_instance_ids:
        try:
            source_map = await t.sources(instance_id)
            async_add_entities(
                [await TesiraSourceSelector.new(t, instance_id, serial, source_map)]
            )
        except CommandFailedException as e:
            _LOGGER.error(
                "Error initializing source selector %s: %s", instance_id, str(e)
            )
            continue

    # Setup router outputs
    router_configs = config.get(CONF_ROUTERS, [])

    for router_config in router_configs:
        router_id = router_config[CONF_ROUTER_ID]
        level_blocks = router_config[CONF_LEVEL_BLOCKS]

        try:
            # Get available inputs for this router
            input_map = await t.router_inputs(router_id)

            # Create entity for each output (1-indexed for Tesira protocol)
            for output_index, level_id in enumerate(level_blocks, start=1):
                # Derive output label from level instance tag (remove "Level" suffix)
                output_label = TesiraSourceSelector.name_from_instance_id(level_id)
                # Remove "Level" from the end if present
                if output_label.endswith(" Level"):
                    output_label = output_label[:-6]
                elif output_label.endswith("Level"):
                    output_label = output_label[:-5]

                # Create entity
                try:
                    async_add_entities([
                        await TesiraRouterOutput.new(
                            t, router_id, level_id, serial,
                            output_index, input_map, output_label
                        )
                    ])
                except CommandFailedException as e:
                    _LOGGER.error(
                        "Error initializing router %s output %d (level %s): %s",
                        router_id,
                        output_index,
                        level_id,
                        str(e),
                    )
                    continue
        except CommandFailedException as e:
            _LOGGER.error("Error initializing router %s: %s", router_id, str(e))
            continue

class TesiraSourceSelector(MediaPlayerEntity):
    """Representation of a Tesira Source Selector."""

    _attr_supported_features = (
        MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.VOLUME_SET
    )
    _attr_should_poll = False

    @staticmethod
    def name_from_instance_id(instance_id):
        split_id = instance_id.split("- ", 1)
        if len(split_id) >= 2:
            return split_id[1]
        split_id = instance_id.split("-", 1)
        if len(split_id) >= 2:
            return split_id[1]
        return instance_id

    def __init__(self, tesira: Tesira, instance_id, serial_number, source_map):
        self._tesira = tesira
        self._serial = serial_number
        self._instance_id = instance_id
        self._attr_unique_id = f"{serial_number}_{instance_id.replace(' ', '_')}"
        self._source_map = source_map
        self._attr_source_list = list(source_map.keys())
        self._attr_source = self._attr_source_list[0]
        self._attr_name = self.name_from_instance_id(instance_id)

    @classmethod
    async def new(cls, tesira: Tesira, instance_id, serial_number, source_map):
        self = cls(tesira, instance_id, serial_number, source_map)
        await tesira.subscribe(instance_id, "outputLevel", self._volume_callback)
        await tesira.subscribe(instance_id, "outputMute", self._mute_callback)
        await tesira.subscribe(instance_id, "sourceSelection", self._source_callback)
        return self

    def try_write_state(self):
        if self.hass:
            self.async_write_ha_state()

    def _volume_callback(self, value):
        self._attr_volume_level = self.db_to_volume(float(value))
        self.try_write_state()

    def _mute_callback(self, value):
        self._attr_is_volume_muted = value == "true"
        self.try_write_state()

    def _source_callback(self, value):
        value = int(value)  # assuming value is a source ID
        for source, source_id in self._source_map.items():
            if source_id == value:
                self._attr_source = source
                break
        else:
            _LOGGER.error("Unknown source ID: %i %s", value, self._instance_id)
            self._attr_source = "Unknown"
        self.try_write_state()

    @property
    def state(self):
        return MediaPlayerState.ON

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        source_id = self._source_map[source]
        await self._tesira.select_source(self._instance_id, source_id)
        self._attr_source = source
        self.async_write_ha_state()

    @staticmethod
    def volume_to_db(volume):
        return max(30 * (math.log2(max(volume, 0.001))), -100)

    @staticmethod
    def db_to_volume(db):
        return math.pow(2, (db / 30))

    async def async_set_volume_level(self, volume: float) -> None:
        await self._tesira.set_volume(self._instance_id, self.volume_to_db(volume))
        self._attr_volume_level = volume
        self.async_write_ha_state()

    async def async_mute_volume(self, mute: bool) -> None:
        await self._tesira.set_output_mute(self._instance_id, mute)
        self._attr_is_volume_muted = mute
        self.async_write_ha_state()

    async def async_send_command(self, command_string: str) -> None:
        await self._tesira._send_command(command_string)  # noqa: SLF001


class TesiraRouterOutput(MediaPlayerEntity):
    """Representation of a Tesira Router Output with Level control."""

    _attr_supported_features = (
        MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.VOLUME_SET
    )
    _attr_should_poll = False

    def __init__(
        self,
        tesira: Tesira,
        router_id: str,
        level_id: str,
        serial_number: int,
        output_index: int,
        input_map: dict,
        output_label: str,
    ):
        self._tesira = tesira
        self._serial = serial_number
        self._router_id = router_id
        self._level_id = level_id
        self._output_index = output_index
        self._attr_unique_id = (
            f"{serial_number}_{router_id.replace(' ', '_')}_output_{output_index}_{level_id.replace(' ', '_')}"
        )
        self._input_map = input_map
        self._attr_source_list = list(input_map.keys())
        self._attr_source = self._attr_source_list[0]
        self._attr_name = output_label

    @classmethod
    async def new(
        cls,
        tesira: Tesira,
        router_id: str,
        level_id: str,
        serial_number: int,
        output_index: int,
        input_map: dict,
        output_label: str,
    ):
        self = cls(
            tesira, router_id, level_id, serial_number, output_index, input_map, output_label
        )

        # Get initial states
        try:
            current_input = await tesira.get_router_output(router_id, output_index)
            # Map input ID to label
            for label, input_id in input_map.items():
                if input_id == current_input:
                    self._attr_source = label
                    break
            else:
                self._attr_source = "Unknown"

            current_level = await tesira.get_level(level_id)
            self._attr_volume_level = self.db_to_volume(current_level)

            current_mute = await tesira.get_mute(level_id)
            self._attr_is_volume_muted = current_mute
        except CommandFailedException as e:
            _LOGGER.error(
                "Error getting initial state for router %s output %d: %s",
                router_id,
                output_index,
                str(e),
            )

        # Subscribe to updates
        await tesira.subscribe(router_id, f"input {output_index}", self._routing_callback)
        await tesira.subscribe(level_id, "level 1", self._volume_callback)
        await tesira.subscribe(level_id, "mute 1", self._mute_callback)

        return self

    def try_write_state(self):
        if self.hass:
            self.async_write_ha_state()

    def _routing_callback(self, value):
        input_id = int(value)
        # Map input ID to label
        for label, mapped_id in self._input_map.items():
            if mapped_id == input_id:
                self._attr_source = label
                break
        else:
            _LOGGER.error(
                "Unknown input ID: %i for router %s output %d",
                input_id,
                self._router_id,
                self._output_index,
            )
            self._attr_source = "Unknown"
        self.try_write_state()

    def _volume_callback(self, value):
        self._attr_volume_level = self.db_to_volume(float(value))
        self.try_write_state()

    def _mute_callback(self, value):
        self._attr_is_volume_muted = value == "true"
        self.try_write_state()

    @property
    def state(self):
        return MediaPlayerState.ON

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        input_id = self._input_map[source]
        await self._tesira.set_router_output(self._router_id, self._output_index, input_id)
        self._attr_source = source
        self.async_write_ha_state()

    @staticmethod
    def volume_to_db(volume):
        return max(30 * (math.log2(max(volume, 0.001))), -100)

    @staticmethod
    def db_to_volume(db):
        return math.pow(2, (db / 30))

    async def async_set_volume_level(self, volume: float) -> None:
        await self._tesira.set_level(self._level_id, self.volume_to_db(volume))
        self._attr_volume_level = volume
        self.async_write_ha_state()

    async def async_mute_volume(self, mute: bool) -> None:
        await self._tesira.set_level_mute(self._level_id, mute)
        self._attr_is_volume_muted = mute
        self.async_write_ha_state()
