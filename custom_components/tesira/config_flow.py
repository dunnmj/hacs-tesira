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
        self._selected_source_selectors: list[str] = []
        self._selected_routers: list[str] = []
        self._selected_mutes: list[str] = []
        self._selected_logic_states: list[str] = []
        self._selected_logic_meters: list[str] = []

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

                return await self.async_step_source_selectors()

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

    async def async_step_source_selectors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle source selector block selection."""
        if user_input is not None:
            self._selected_source_selectors = user_input.get(CONF_SOURCE_SELECTORS, [])
            return await self.async_step_select_routers()

        available = [
            b["instance_id"]
            for b in self._discovered_blocks.get(BLOCK_TYPE_SOURCE_SELECTOR, [])
        ]

        if not available:
            return await self.async_step_select_routers()

        options = {sid: sid for sid in available}

        return self.async_show_form(
            step_id="source_selectors",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_SOURCE_SELECTORS, default=[]): cv.multi_select(
                        options
                    ),
                }
            ),
        )

    async def async_step_select_routers(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle router block selection."""
        if user_input is not None:
            self._selected_routers = user_input.get(CONF_ROUTERS, [])
            # Filter routers to only selected ones
            self._routers = [
                r for r in self._routers if r["instance_id"] in self._selected_routers
            ]
            if self._routers:
                return await self.async_step_router()
            return await self.async_step_levels()

        available = [
            b["instance_id"] for b in self._discovered_blocks.get(BLOCK_TYPE_ROUTER, [])
        ]

        if not available:
            return await self.async_step_levels()

        options = {rid: rid for rid in available}

        return self.async_show_form(
            step_id="select_routers",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_ROUTERS, default=[]): cv.multi_select(options),
                }
            ),
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
            self._selected_levels = user_input.get(CONF_LEVELS, [])
            return await self.async_step_mutes()

        # Available level blocks not assigned to routers
        available_levels = [
            lid for lid in self._level_blocks if lid not in self._assigned_levels
        ]

        if not available_levels:
            self._selected_levels = []
            return await self.async_step_mutes()

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

    async def async_step_mutes(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle mute block selection."""
        if user_input is not None:
            self._selected_mutes = user_input.get(CONF_MUTES, [])
            return await self.async_step_logic_states()

        available = [
            b["instance_id"] for b in self._discovered_blocks.get(BLOCK_TYPE_MUTE, [])
        ]

        if not available:
            return await self.async_step_logic_states()

        options = {mid: mid for mid in available}

        return self.async_show_form(
            step_id="mutes",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_MUTES, default=[]): cv.multi_select(options),
                }
            ),
        )

    async def async_step_logic_states(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle logic state block selection."""
        if user_input is not None:
            self._selected_logic_states = user_input.get(CONF_LOGIC_STATES, [])
            return await self.async_step_logic_meters()

        available = [
            b["instance_id"]
            for b in self._discovered_blocks.get(BLOCK_TYPE_LOGIC_STATE, [])
        ]

        if not available:
            return await self.async_step_logic_meters()

        options = {sid: sid for sid in available}

        return self.async_show_form(
            step_id="logic_states",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_LOGIC_STATES, default=[]): cv.multi_select(
                        options
                    ),
                }
            ),
        )

    async def async_step_logic_meters(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle logic meter block selection."""
        if user_input is not None:
            self._selected_logic_meters = user_input.get(CONF_LOGIC_METERS, [])
            return self._create_entry()

        available = [
            b["instance_id"]
            for b in self._discovered_blocks.get(BLOCK_TYPE_LOGIC_METER, [])
        ]

        if not available:
            return self._create_entry()

        options = {mid: mid for mid in available}

        return self.async_show_form(
            step_id="logic_meters",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_LOGIC_METERS, default=[]): cv.multi_select(
                        options
                    ),
                }
            ),
        )

    def _create_entry(self) -> ConfigFlowResult:
        """Create the config entry with all selected blocks."""
        options = {
            CONF_SOURCE_SELECTORS: self._selected_source_selectors,
            CONF_MUTES: self._selected_mutes,
            CONF_LOGIC_STATES: self._selected_logic_states,
            CONF_LOGIC_METERS: self._selected_logic_meters,
            CONF_LEVELS: self._selected_levels,
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

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of connection details."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

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
                await tesira.invalidate_connection()

            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_HOST: host,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=entry.data.get(CONF_HOST, "")): str,
                    vol.Required(
                        CONF_USERNAME, default=entry.data.get(CONF_USERNAME, "")
                    ): str,
                    vol.Optional(
                        CONF_PASSWORD, default=entry.data.get(CONF_PASSWORD, "")
                    ): str,
                }
            ),
            errors=errors,
        )


class TesiraOptionsFlow(OptionsFlow):
    """Handle options flow for Tesira Control.

    Re-discovers blocks and lets the user reconfigure all block selections.
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
        self._selected_source_selectors: list[str] = []
        self._selected_routers: list[str] = []
        self._selected_levels: list[str] = []
        self._selected_mutes: list[str] = []
        self._selected_logic_states: list[str] = []
        self._selected_logic_meters: list[str] = []

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

        return await self.async_step_source_selectors()

    async def async_step_source_selectors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle source selector block selection in options."""
        if user_input is not None:
            self._selected_source_selectors = user_input.get(CONF_SOURCE_SELECTORS, [])
            return await self.async_step_select_routers()

        available = [
            b["instance_id"]
            for b in self._discovered_blocks.get(BLOCK_TYPE_SOURCE_SELECTOR, [])
        ]

        if not available:
            return await self.async_step_select_routers()

        # Pre-select from current config
        current = self.config_entry.options.get(CONF_SOURCE_SELECTORS, [])
        defaults = [sid for sid in current if sid in available]

        options = {sid: sid for sid in available}

        return self.async_show_form(
            step_id="source_selectors",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SOURCE_SELECTORS, default=defaults
                    ): cv.multi_select(options),
                }
            ),
        )

    async def async_step_select_routers(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle router block selection in options."""
        if user_input is not None:
            self._selected_routers = user_input.get(CONF_ROUTERS, [])
            # Filter routers to only selected ones
            self._routers = [
                r for r in self._routers if r["instance_id"] in self._selected_routers
            ]
            if self._routers:
                return await self.async_step_router()
            return await self.async_step_levels()

        available = [
            b["instance_id"] for b in self._discovered_blocks.get(BLOCK_TYPE_ROUTER, [])
        ]

        if not available:
            return await self.async_step_levels()

        # Pre-select from current config
        current = [
            rc[CONF_ROUTER_ID] for rc in self.config_entry.options.get(CONF_ROUTERS, [])
        ]
        defaults = [rid for rid in current if rid in available]

        options = {rid: rid for rid in available}

        return self.async_show_form(
            step_id="select_routers",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_ROUTERS, default=defaults): cv.multi_select(
                        options
                    ),
                }
            ),
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
            self._selected_levels = user_input.get(CONF_LEVELS, [])
            return await self.async_step_mutes()

        available_levels = [
            lid for lid in self._level_blocks if lid not in self._assigned_levels
        ]

        if not available_levels:
            self._selected_levels = []
            return await self.async_step_mutes()

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

    async def async_step_mutes(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle mute block selection in options."""
        if user_input is not None:
            self._selected_mutes = user_input.get(CONF_MUTES, [])
            return await self.async_step_logic_states()

        available = [
            b["instance_id"] for b in self._discovered_blocks.get(BLOCK_TYPE_MUTE, [])
        ]

        if not available:
            return await self.async_step_logic_states()

        # Pre-select from current config
        current = self.config_entry.options.get(CONF_MUTES, [])
        defaults = [mid for mid in current if mid in available]

        options = {mid: mid for mid in available}

        return self.async_show_form(
            step_id="mutes",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_MUTES, default=defaults): cv.multi_select(
                        options
                    ),
                }
            ),
        )

    async def async_step_logic_states(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle logic state block selection in options."""
        if user_input is not None:
            self._selected_logic_states = user_input.get(CONF_LOGIC_STATES, [])
            return await self.async_step_logic_meters()

        available = [
            b["instance_id"]
            for b in self._discovered_blocks.get(BLOCK_TYPE_LOGIC_STATE, [])
        ]

        if not available:
            return await self.async_step_logic_meters()

        # Pre-select from current config
        current = self.config_entry.options.get(CONF_LOGIC_STATES, [])
        defaults = [sid for sid in current if sid in available]

        options = {sid: sid for sid in available}

        return self.async_show_form(
            step_id="logic_states",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_LOGIC_STATES, default=defaults): cv.multi_select(
                        options
                    ),
                }
            ),
        )

    async def async_step_logic_meters(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle logic meter block selection in options."""
        if user_input is not None:
            self._selected_logic_meters = user_input.get(CONF_LOGIC_METERS, [])
            return self._create_options_entry()

        available = [
            b["instance_id"]
            for b in self._discovered_blocks.get(BLOCK_TYPE_LOGIC_METER, [])
        ]

        if not available:
            return self._create_options_entry()

        # Pre-select from current config
        current = self.config_entry.options.get(CONF_LOGIC_METERS, [])
        defaults = [mid for mid in current if mid in available]

        options = {mid: mid for mid in available}

        return self.async_show_form(
            step_id="logic_meters",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_LOGIC_METERS, default=defaults): cv.multi_select(
                        options
                    ),
                }
            ),
        )

    def _create_options_entry(self) -> ConfigFlowResult:
        """Create options entry with updated block selections."""
        return self.async_create_entry(
            title=self.config_entry.title,
            data={
                CONF_SOURCE_SELECTORS: self._selected_source_selectors,
                CONF_MUTES: self._selected_mutes,
                CONF_LOGIC_STATES: self._selected_logic_states,
                CONF_LOGIC_METERS: self._selected_logic_meters,
                CONF_LEVELS: self._selected_levels,
                CONF_ROUTERS: self._router_configs,
            },
        )
