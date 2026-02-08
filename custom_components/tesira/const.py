"""Constants for the Tesira integration."""

DOMAIN = "tesira_ttp"

CONF_SOURCE_SELECTORS = "source_selectors"
CONF_MUTES = "mutes"
CONF_LEVELS = "levels"
CONF_LOGIC_METERS = "logic_meters"
CONF_LOGIC_STATES = "logic_states"
CONF_ROUTERS = "routers"
CONF_ROUTER_ID = "router_id"
CONF_LEVEL_BLOCKS = "level_blocks"
CONF_LEVEL_BLOCK = "level_block"

NONE_SELECTION = "__none__"

# Block type strings returned by Tesira blockInfo
BLOCK_TYPE_SOURCE_SELECTOR = "Source Selector"
BLOCK_TYPE_ROUTER = "Router"
BLOCK_TYPE_LEVEL = "Level"
BLOCK_TYPE_MUTE = "Mute Control"
BLOCK_TYPE_LOGIC_STATE = "Logic State"
BLOCK_TYPE_LOGIC_METER = "Logic Meter"

# Supported block types for auto-discovery
AUTO_ADD_BLOCK_TYPES = {
    BLOCK_TYPE_SOURCE_SELECTOR,
    BLOCK_TYPE_LOGIC_STATE,
    BLOCK_TYPE_LOGIC_METER,
    BLOCK_TYPE_MUTE,
}

SERVICE_NAME = "send_command"
