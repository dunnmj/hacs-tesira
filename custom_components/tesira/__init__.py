"""The Tesira control component."""

import asyncio
import copy
import voluptuous as vol

from homeassistant.const import CONF_IP_ADDRESS, CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.discovery import async_load_platform

from .tesira import Tesira

DOMAIN = "tesira_ttp"
CONF_SOURCE_SELECTORS = "source_selectors"
CONF_MUTES = "mutes"
CONF_LEVELS = "levels"
CONF_LOGIC_METERS = "logic_meters"
CONF_LOGIC_STATES = "logic_states"
CONF_ROUTERS = "routers"
CONF_ROUTER_ID = "router_id"
CONF_LEVEL_BLOCKS = "level_blocks"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.All(
            cv.ensure_list,
            [
                vol.Schema(
                    {
                        vol.Required(CONF_IP_ADDRESS): cv.string,
                        vol.Required(CONF_USERNAME): cv.string,
                        vol.Required(CONF_PASSWORD): cv.string,
                        vol.Required(CONF_NAME): cv.string,
                        vol.Optional(CONF_SOURCE_SELECTORS): vol.All(
                            cv.ensure_list,
                            [cv.string],
                        ),
                        vol.Optional(CONF_MUTES): vol.All(
                            cv.ensure_list,
                            [cv.string],
                        ),
                        vol.Optional(CONF_LEVELS): vol.All(
                            cv.ensure_list,
                            [cv.string],
                        ),
                        vol.Optional(CONF_LOGIC_METERS): vol.All(
                            cv.ensure_list,
                            [cv.string],
                        ),
                        vol.Optional(CONF_LOGIC_STATES): vol.All(
                            cv.ensure_list,
                            [cv.string],
                        ),
                        vol.Optional(CONF_ROUTERS): vol.All(
                            cv.ensure_list,
                            [
                                vol.Schema(
                                    {
                                        vol.Required(CONF_ROUTER_ID): cv.string,
                                        vol.Required(CONF_LEVEL_BLOCKS): vol.All(
                                            cv.ensure_list,
                                            [cv.string],
                                        ),
                                    }
                                )
                            ],
                        ),
                    }
                )
            ],
        )
    },
    extra=vol.ALLOW_EXTRA,  # Allow extra keys to be present in the configuration.
)


COMMON_CONFIGS = [CONF_IP_ADDRESS, CONF_USERNAME, CONF_PASSWORD, CONF_NAME]


async def async_setup(hass: HomeAssistant, config):
    """Set up entities from config."""
    hass.data[DOMAIN] = hass.data.get(DOMAIN, {})
    for tesira_device in config[DOMAIN]:
        hass.async_create_task(
            async_load_platform(
                hass, "media_player", DOMAIN, copy.deepcopy(tesira_device), config
            ),
            eager_start=True,
        )
        hass.async_create_task(
            async_load_platform(
                hass,
                "switch",
                DOMAIN,
                copy.deepcopy(tesira_device),
                config,
            ),
            eager_start=True,
        )
        hass.async_create_task(
            async_load_platform(
                hass,
                "number",
                DOMAIN,
                copy.deepcopy(tesira_device),
                config,
            ),
            eager_start=True,
        )
        hass.async_create_task(
            async_load_platform(
                hass,
                "binary_sensor",
                DOMAIN,
                copy.deepcopy(tesira_device),
                config,
            ),
            eager_start=True,
        )
    return True


def get_name_from_instance_id(instance_id: str) -> str:
    """Extract a friendly name from a Tesira instance ID."""
    if "-" in instance_id:
        return instance_id.rsplit("-", 1)[0].strip()
    return instance_id


TESIRA_CREATION_LOCK = asyncio.Lock()


class AlreadyConstructedException(Exception):
    def __init__(self, future):
        self.future = future
        super().__init__("Already constructed")


async def get_tesira(hass, ip, username, password) -> Tesira:
    # try and get tesira from hass or create new one
    try:
        async with TESIRA_CREATION_LOCK:
            if ip in hass.data[DOMAIN]:
                raise AlreadyConstructedException(hass.data[DOMAIN][ip])

            hass.data[DOMAIN][ip] = asyncio.create_task(
                Tesira.new(ip, username, password)
            )
    except AlreadyConstructedException as e:
        return await e.future
    try:
        return await hass.data[DOMAIN][ip]
    except (TimeoutError, OSError) as e:
        async with TESIRA_CREATION_LOCK:
            hass.data[DOMAIN].pop(ip)
        raise PlatformNotReady(f"Unable to connect to Tesira: {e!s}") from e
