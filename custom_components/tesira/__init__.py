"""The Tesira control component."""

from __future__ import annotations

import logging
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .tesira import Tesira

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.MEDIA_PLAYER,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.BINARY_SENSOR,
]

type TesiraConfigEntry = ConfigEntry[Tesira]


BLOCK_TYPE_SUFFIXES = [
    "SourceSelector",
    "LogicMeter",
    "LogicState",
    "Router",
    "Level",
    "MuteControl",
    "Mute",
]


def get_name_from_instance_id(instance_id: str) -> str:
    """Extract a friendly name from a Tesira instance ID."""
    if "-" in instance_id:
        return instance_id.rsplit("-", 1)[0].strip()

    # Strip known block type suffixes
    name = instance_id
    for suffix in BLOCK_TYPE_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[: -len(suffix)]
            break

    # Split camelCase into separate words, keeping consecutive capitals together
    # and separating digit/letter boundaries
    return re.sub(
        r"(?<=[a-z])(?=[A-Z])"
        r"|(?<=[A-Z])(?=[A-Z][a-z])"
        r"|(?<=[a-zA-Z])(?=[0-9])"
        r"|(?<=[0-9])(?=[a-zA-Z])",
        " ",
        name,
    )


async def async_setup_entry(hass: HomeAssistant, entry: TesiraConfigEntry) -> bool:
    """Set up Tesira from a config entry."""
    host = entry.data[CONF_HOST]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    try:
        tesira = await Tesira.new(host, username, password)
    except (TimeoutError, OSError) as err:
        raise ConfigEntryNotReady(f"Unable to connect to Tesira at {host}") from err

    entry.runtime_data = tesira

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    return True


async def async_update_listener(hass: HomeAssistant, entry: TesiraConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: TesiraConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        tesira: Tesira = entry.runtime_data
        await tesira.invalidate_connection()

    return unload_ok
