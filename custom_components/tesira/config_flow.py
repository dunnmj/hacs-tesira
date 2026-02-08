"""Config flow for Tesira Control."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from .const import (
    BLOCK_TYPE_LEVEL,
    BLOCK_TYPE_LOGIC_METER,
    BLOCK_TYPE_LOGIC_STATE,
    BLOCK_TYPE_MUTE,
    BLOCK_TYPE_ROUTER,
    BLOCK_TYPE_SOURCE_SELECTOR,
    CONF_LEVEL_BLOCK,
    CONF_LEVELS,
    CONF_LEVEL_BLOCKS,
    CONF_LOGIC_METERS,
    CONF_LOGIC_STATES,
    CONF_MUTES,
    CONF_ROUTERS,
    CONF_ROUTER_ID,
    CONF_SOURCE_SELECTORS,
    DOMAIN,
    NONE_SELECTION,
)
from .tesira import Tesira

_LOGGER = logging.getLogger(__name__)


class TesiraConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tesira Control."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_blocks: dict[str, list[dict]] = {}
        self._routers: list[dict] = []
        self._level_blocks: list[str] = []
        self._router_configs: list[dict[str, Any]] = []
        self._current_router_index: int = 0
        self._current_output_index: int = 0
        self._current_router_levels: list[str] = []
        self._assigned_levels: set[str] = set()
        self._connection_data: dict[str, str] = {}
        self._serial: int = 0

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial connection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            try:
                tesira = Tesira(host, username, password)
                await tesira.connect_command_only()
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                try:
                    self._serial = await tesira.serial_number()
                    self._discovered_blocks = await tesira.discover_blocks()
                except Exception:
                    errors["base"] = "cannot_connect"
                finally:
                    await tesira.invalidate_connection()

            if not errors:
                # Check for duplicate by serial number
                await self.async_set_unique_id(str(self._serial))
                self._abort_if_unique_id_configured()

                self._connection_data = {
                    CONF_NAME: user_input[CONF_NAME],
                    CONF_HOST: host,
                    CONF_USERNAME: username,
                    CONF_PASSWORD: password,
                }

                # Categorize discovered blocks
                self._routers = [
                    b for b in self._discovered_blocks.get(BLOCK_TYPE_ROUTER, [])
                ]
                self._level_blocks = [
                    b["instance_id"]
                    for b in self._discovered_blocks.get(BLOCK_TYPE_LEVEL, [])
                ]
                self._router_configs = []
                self._current_router_index = 0
                self._assigned_levels = set()

                # If routers exist, go to router config steps
                if self._routers:
                    return await self.async_step_router()

                # Otherwise go straight to level selection
                return await self.async_step_levels()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_USERNAME): str,
                    vol.Optional(CONF_PASSWORD, default=""): str,
                }
            ),
            errors=errors,
        )

    async def _advance_to_next_router(self) -> ConfigFlowResult:
        """Save current router config and advance to next router or levels."""
        router = self._routers[self._current_router_index]
        self._router_configs.append(
            {
                CONF_ROUTER_ID: router["instance_id"],
                CONF_LEVEL_BLOCKS: list(self._current_router_levels),
            }
        )
        self._current_router_index += 1
        self._current_output_index = 0
        self._current_router_levels = []

        if self._current_router_index < len(self._routers):
            return await self.async_step_router()
        return await self.async_step_levels()

    async def async_step_router(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle router level block assignment, one output at a time."""
        if user_input is not None:
            selected = user_input.get(CONF_LEVEL_BLOCK, NONE_SELECTION)
            if selected != NONE_SELECTION:
                self._current_router_levels.append(selected)
                self._assigned_levels.add(selected)
            else:
                self._current_router_levels.append("")

            self._current_output_index += 1

            # More outputs on this router?
            router = self._routers[self._current_router_index]
            num_outputs = router.get("channel_info", {}).get("numOutputs", 0)
            if self._current_output_index < num_outputs:
                return await self.async_step_router()

            # This router is done, advance
            return await self._advance_to_next_router()

        router = self._routers[self._current_router_index]
        router_id = router["instance_id"]
        num_outputs = router.get("channel_info", {}).get("numOutputs", 0)

        if num_outputs == 0:
            # No outputs, skip this router
            return await self._advance_to_next_router()

        # Available level blocks (not yet assigned)
        available_levels = [
            lid for lid in self._level_blocks if lid not in self._assigned_levels
        ]

        if not available_levels:
            # No levels left, skip remaining outputs and this router
            remaining = num_outputs - self._current_output_index
            self._current_router_levels.extend([""] * remaining)
            return await self._advance_to_next_router()

        # Build select options: "None" + available levels
        level_options = {NONE_SELECTION: "None (skip)"}
        level_options.update({lid: lid for lid in available_levels})

        output_number = self._current_output_index + 1

        return self.async_show_form(
            step_id="router",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LEVEL_BLOCK, default=NONE_SELECTION): vol.In(
                        level_options
                    ),
                }
            ),
            description_placeholders={
                "router_name": router_id,
                "num_outputs": str(num_outputs),
                "output_number": str(output_number),
            },
        )

    async def async_step_levels(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle standalone level block selection."""
        if user_input is not None:
            selected_levels = user_input.get(CONF_LEVELS, [])
            return self._create_entry(selected_levels)

        # Available level blocks not assigned to routers
        available_levels = [
            lid for lid in self._level_blocks if lid not in self._assigned_levels
        ]

        if not available_levels:
            # No levels to select, create entry immediately
            return self._create_entry([])

        level_options = {lid: lid for lid in available_levels}

        return self.async_show_form(
            step_id="levels",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_LEVELS, default=[]): cv.multi_select(
                        level_options
                    ),
                }
            ),
        )

    def _create_entry(self, selected_levels: list[str]) -> ConfigFlowResult:
        """Create the config entry with all discovered and selected blocks."""
        # Auto-added blocks
        source_selectors = [
            b["instance_id"]
            for b in self._discovered_blocks.get(BLOCK_TYPE_SOURCE_SELECTOR, [])
        ]
        mutes = [
            b["instance_id"] for b in self._discovered_blocks.get(BLOCK_TYPE_MUTE, [])
        ]
        logic_states = [
            b["instance_id"]
            for b in self._discovered_blocks.get(BLOCK_TYPE_LOGIC_STATE, [])
        ]
        logic_meters = [
            b["instance_id"]
            for b in self._discovered_blocks.get(BLOCK_TYPE_LOGIC_METER, [])
        ]

        options = {
            CONF_SOURCE_SELECTORS: source_selectors,
            CONF_MUTES: mutes,
            CONF_LOGIC_STATES: logic_states,
            CONF_LOGIC_METERS: logic_meters,
            CONF_LEVELS: selected_levels,
            CONF_ROUTERS: self._router_configs,
        }

        return self.async_create_entry(
            title=self._connection_data[CONF_NAME],
            data=self._connection_data,
            options=options,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return TesiraOptionsFlow()


class TesiraOptionsFlow(OptionsFlow):
    """Handle options flow for Tesira Control.

    Re-discovers blocks and lets the user reconfigure routers and levels.
    """

    def __init__(self) -> None:
        """Initialize the options flow."""
        self._discovered_blocks: dict[str, list[dict]] = {}
        self._routers: list[dict] = []
        self._level_blocks: list[str] = []
        self._router_configs: list[dict[str, Any]] = []
        self._current_router_index: int = 0
        self._current_output_index: int = 0
        self._current_router_levels: list[str] = []
        self._assigned_levels: set[str] = set()

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-discover blocks and start reconfiguration."""
        entry = self.config_entry
        host = entry.data[CONF_HOST]
        username = entry.data[CONF_USERNAME]
        password = entry.data[CONF_PASSWORD]
        errors: dict[str, str] = {}

        try:
            tesira = Tesira(host, username, password)
            await tesira.connect_command_only()
            self._discovered_blocks = await tesira.discover_blocks()
            await tesira.invalidate_connection()
        except Exception:
            errors["base"] = "cannot_connect"
            return self.async_show_form(
                step_id="init", data_schema=vol.Schema({}), errors=errors
            )

        # Categorize
        self._routers = list(self._discovered_blocks.get(BLOCK_TYPE_ROUTER, []))
        self._level_blocks = [
            b["instance_id"] for b in self._discovered_blocks.get(BLOCK_TYPE_LEVEL, [])
        ]
        self._router_configs = []
        self._current_router_index = 0
        self._assigned_levels = set()

        if self._routers:
            return await self.async_step_router()

        return await self.async_step_levels()

    async def _advance_to_next_router(self) -> ConfigFlowResult:
        """Save current router config and advance to next router or levels."""
        router = self._routers[self._current_router_index]
        self._router_configs.append(
            {
                CONF_ROUTER_ID: router["instance_id"],
                CONF_LEVEL_BLOCKS: list(self._current_router_levels),
            }
        )
        self._current_router_index += 1
        self._current_output_index = 0
        self._current_router_levels = []

        if self._current_router_index < len(self._routers):
            return await self.async_step_router()
        return await self.async_step_levels()

    async def async_step_router(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle router level block assignment in options, one output at a time."""
        if user_input is not None:
            selected = user_input.get(CONF_LEVEL_BLOCK, NONE_SELECTION)
            if selected != NONE_SELECTION:
                self._current_router_levels.append(selected)
                self._assigned_levels.add(selected)
            else:
                self._current_router_levels.append("")

            self._current_output_index += 1

            # More outputs on this router?
            router = self._routers[self._current_router_index]
            num_outputs = router.get("channel_info", {}).get("numOutputs", 0)
            if self._current_output_index < num_outputs:
                return await self.async_step_router()

            # This router is done, advance
            return await self._advance_to_next_router()

        router = self._routers[self._current_router_index]
        router_id = router["instance_id"]
        num_outputs = router.get("channel_info", {}).get("numOutputs", 0)

        if num_outputs == 0:
            return await self._advance_to_next_router()

        available_levels = [
            lid for lid in self._level_blocks if lid not in self._assigned_levels
        ]

        if not available_levels:
            remaining = num_outputs - self._current_output_index
            self._current_router_levels.extend([""] * remaining)
            return await self._advance_to_next_router()

        # Determine default from current config
        default = NONE_SELECTION
        current_routers = self.config_entry.options.get(CONF_ROUTERS, [])
        for rc in current_routers:
            if rc[CONF_ROUTER_ID] == router_id:
                current_levels = rc.get(CONF_LEVEL_BLOCKS, [])
                if self._current_output_index < len(current_levels):
                    prev = current_levels[self._current_output_index]
                    if prev in available_levels:
                        default = prev
                break

        level_options = {NONE_SELECTION: "None (skip)"}
        level_options.update({lid: lid for lid in available_levels})

        output_number = self._current_output_index + 1

        return self.async_show_form(
            step_id="router",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LEVEL_BLOCK, default=default): vol.In(
                        level_options
                    ),
                }
            ),
            description_placeholders={
                "router_name": router_id,
                "num_outputs": str(num_outputs),
                "output_number": str(output_number),
            },
        )

    async def async_step_levels(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle standalone level block selection in options."""
        if user_input is not None:
            selected_levels = user_input.get(CONF_LEVELS, [])
            return self._create_options_entry(selected_levels)

        available_levels = [
            lid for lid in self._level_blocks if lid not in self._assigned_levels
        ]

        if not available_levels:
            return self._create_options_entry([])

        # Pre-select from current config
        current_levels = self.config_entry.options.get(CONF_LEVELS, [])
        defaults = [lid for lid in current_levels if lid in available_levels]

        level_options = {lid: lid for lid in available_levels}

        return self.async_show_form(
            step_id="levels",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_LEVELS, default=defaults): cv.multi_select(
                        level_options
                    ),
                }
            ),
        )

    def _create_options_entry(self, selected_levels: list[str]) -> ConfigFlowResult:
        """Create options entry with updated block selections."""
        source_selectors = [
            b["instance_id"]
            for b in self._discovered_blocks.get(BLOCK_TYPE_SOURCE_SELECTOR, [])
        ]
        mutes = [
            b["instance_id"] for b in self._discovered_blocks.get(BLOCK_TYPE_MUTE, [])
        ]
        logic_states = [
            b["instance_id"]
            for b in self._discovered_blocks.get(BLOCK_TYPE_LOGIC_STATE, [])
        ]
        logic_meters = [
            b["instance_id"]
            for b in self._discovered_blocks.get(BLOCK_TYPE_LOGIC_METER, [])
        ]

        return self.async_create_entry(
            title=self.config_entry.title,
            data={
                CONF_SOURCE_SELECTORS: source_selectors,
                CONF_MUTES: mutes,
                CONF_LOGIC_STATES: logic_states,
                CONF_LOGIC_METERS: logic_meters,
                CONF_LEVELS: selected_levels,
                CONF_ROUTERS: self._router_configs,
            },
        )
