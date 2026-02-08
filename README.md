# Tesira Control — Home Assistant Custom Integration (HACS)

Control **Biamp Tesira** DSP systems from Home Assistant using the Tesira Text Protocol.

---

## Overview

- **Domain:** `tesira_ttp`
- **Platforms:** `media_player`, `switch`, `number`, `binary_sensor`
- **Configuration:** UI config flow with auto-discovery
- **Connection:** SSH (via `asyncssh`)
- **Protocol:** Tesira Text Protocol Server
- **Action:** `tesira_ttp.send_command`

The integration maintains:

- a command connection for control
- a subscription connection for live updates (levels, mutes, source changes)

---

## Features

- **Auto-discovery** of all supported block types on the Tesira device
- Source selection via `media_player`
- Volume and mute control
- Router output control with volume and mute per zone
- Standalone level control via `number` entities (percentage slider)
- Per-channel mute switches
- Logic state switches (on/off control of Tesira logic state blocks)
- Logic meter binary sensors (read-only monitoring of Tesira logic meter blocks)
- Real-time updates using Tesira publish subscriptions
- Raw command service for advanced/custom control
- Options flow to reconfigure blocks without removing the integration

---

## Installation (HACS)

1. Open **HACS** in Home Assistant
2. Go to **Integrations**
3. Open the menu (⋮) → **Custom repositories**
4. Add:
   - **Repository:** https://github.com/dunnmj/hacs-tesira
   - **Category:** Integration
5. Search for **Tesira Control**
6. Install and **restart Home Assistant**

---

## Configuration (UI)

This integration is configured entirely through the Home Assistant UI.

### Adding the integration

1. Go to **Settings** → **Devices & services** → **Add integration**
2. Search for **Tesira Control**
3. Enter connection details:
   - **Name**: A friendly name for this Tesira device
   - **Host**: IP address or hostname of the Tesira device
   - **Username**: SSH username
   - **Password**: SSH password (leave blank if not required)
4. The integration connects and **auto-discovers** all supported blocks on the device

> **Default credentials:**
>
> - **Unprotected Tesira**: username `default`, password blank
> - **Protected Tesira**: username `admin`, password as set on the device

### Auto-discovered block types

The following block types are discovered and added automatically — no user action required:

| Block type      | Platform        | Description                           |
| --------------- | --------------- | ------------------------------------- |
| Source Selector | `media_player`  | Source selection with volume and mute |
| Mute Control    | `switch`        | Per-channel mute switches             |
| Logic State     | `switch`        | On/off control switches               |
| Logic Meter     | `binary_sensor` | Read-only state monitoring            |

### Router configuration

If routers are discovered, you are walked through each router **one output at a time**:

1. For each output, select a **Level block** to assign (or choose "None" to skip)
2. Assigned level blocks are removed from the available list for subsequent outputs
3. Each assigned output becomes a `media_player` entity with source routing, volume, and mute

### Level block selection

After router configuration (or immediately if no routers exist), you can select **standalone Level blocks** to add as `number` entities. Blocks already assigned to routers are not shown.

### Reconfiguring

To change block assignments after setup:

1. Go to **Settings** → **Devices & services** → **Tesira Control**
2. Click **Configure**
3. The integration re-discovers blocks and walks you through router and level selection again

> Changes take effect immediately — no restart required.

---

## Entities

### Media Player (`media_player`)

A `media_player` entity is created for each discovered Source Selector block.

Supported features:

- Source selection
- Volume control
- Mute/unmute

The integration subscribes to:

- `outputLevel`
- `outputMute`
- `sourceSelection`

for real-time state updates.

---

### Router Outputs (`media_player`)

Router outputs provide zone-based routing with optional volume and mute control.

A `media_player` entity is created for **every** router output. The Level blocks are mapped to router outputs in order (first Level block = output 1, second = output 2, etc.).

- **With a Level block assigned**: The entity supports source selection, volume control, and mute
- **Without a Level block** (skipped during setup): The entity supports source selection only — no volume or mute controls

**Important:** Router blocks in Tesira use:

- **0-indexed inputs** (0, 1, 2, 3, 4 for a 5-input router)
- **1-indexed outputs** (1, 2, 3, 4, 5 for a 5-output router)

This is different from Source Selectors which are 1-indexed for both sources and outputs.

**What each entity controls:**

- **Source selection**: Routes any Router input to that specific output
- **Volume control** _(with Level block only)_: Adjusts the Level block volume in dB
- **Mute control** _(with Level block only)_: Mutes/unmutes the Level block

**Real-time updates:**

The integration subscribes to:

- Router output routing changes
- Level block volume changes
- Level block mute state changes

All three subscriptions work together to provide complete zone control.

---

### Number (`number`)

A `number` entity is created for each Level block selected during setup (standalone, not assigned to a router).

Each entity exposes a Tesira Level block as a percentage slider (0–100%). The dB-to-percentage conversion uses the same logarithmic scale as the media player volume controls.

Supported features:

- Set level as a percentage (0–100%)
- Real-time updates via Tesira subscriptions

The integration subscribes to:

- `level 1`

for real-time state updates.

---

### Switch (`switch`)

#### Mute switches

For each discovered Mute Control block, the integration:

- Queries the mute block
- Discovers the number of channels
- Creates one mute switch per channel

Each switch controls the channel mute state directly.

#### Logic State switches

A `switch` entity is created for each discovered Logic State block.

These control Tesira Logic State blocks. Only channel 1 is supported — multi-channel logic state blocks are not. Turning the switch on sets the state to `true`, turning it off sets it to `false`.

The integration subscribes to:

- `state 1`

for real-time state updates.

---

### Binary Sensor — Logic Meters (`binary_sensor`)

A `binary_sensor` entity is created for each discovered Logic Meter block.

These provide read-only monitoring of Tesira Logic Meter blocks. Only channel 1 is supported — multi-channel logic meter blocks are not. The sensor is `on` when the meter value is `true` and `off` when `false`.

The integration subscribes to:

- `state 1`

for real-time state updates.

---

## Entity Naming Behavior

Entity names are derived from the Tesira block instance ID.

Naming rules:

1. If the instance ID contains `"-"`, everything **before the last** `"-"` is used (with whitespace trimmed)
2. If the instance ID has **no** `"-"`, known block type suffixes (e.g. `SourceSelector`, `Level`, `MuteControl`, `Router`, `LogicState`, `LogicMeter`) are stripped, and the remaining camelCase text is split into separate words

Examples:

| Instance ID                   | Entity Name |
| ----------------------------- | ----------- |
| `01 - Lounge Source Selector` | `01`        |
| `Source - Office`             | `Source`    |
| `Zone 1 - Level`              | `Zone 1`    |
| `MainRoomSourceSelector`      | `Main Room` |
| `BarSourceSelector`           | `Bar`       |
| `LoungeLevel`                 | `Lounge`    |

You control entity naming by how you name your Tesira blocks.

### Router output entity names

Router output entity naming depends on whether a Level block was assigned:

- **With a Level block**: Named after the Level block's instance ID, using the standard naming rules above
- **Without a Level block**: Named using the router's instance ID (via standard naming rules) combined with the output label fetched from Tesira

Examples:

| Router Instance ID | Level Block            | Output Label | Entity Name     |
| ------------------ | ---------------------- | ------------ | --------------- |
| `Studio - Router`  | `Studio Upper - Level` | —            | `Studio Upper`  |
| `Studio - Router`  | _(none)_               | `Zone 3`     | `Studio Zone 3` |
| `ZoneRouter`       | `Zone1Level`           | —            | `Zone1`         |
| `ZoneRouter`       | _(none)_               | `Patio`      | `Zone Patio`    |

### Switch entity names (mute channels)

Switch names are a combination of:

1. The cleaned instance ID (same logic as above)
2. The channel label fetched directly from Tesira

Format: `<Instance Name> - <Input Label>`

Example: `01 - Mic 1`, `01 - Lectern`

Channel labels come directly from the Tesira configuration.

### Media player source names

Source names are pulled directly from Tesira.

For each source selector:

- The integration queries each source
- Uses the Tesira source label as the selectable source name in Home Assistant

---

## Actions

### `tesira_ttp.send_command`

Send raw Tesira Text Protocol commands to a device.

**Target:** A `media_player` entity from this integration
**Field:** `command_strings` (list of strings)

### Example

```yaml
action: tesira_ttp.send_command
target:
  entity_id: media_player.lounge_source_selector
data:
  command_strings:
    - "SourceSelector1 set outputMute true"
    - "SourceSelector1 set outputLevel -20.0"
```

This service is useful for:

- Unsupported blocks
- Advanced control
- Debugging

---

## Troubleshooting

### Enable debug logging

```yaml
logger:
  default: info
  logs:
    custom_components.tesira: debug
```

Restart Home Assistant, reproduce the issue, and include logs when opening issues (remove secrets).

### Common issues

**No entities appear**

- Ensure the Tesira device has blocks with supported types (Source Selector, Router, Level, Mute Control, Logic State, Logic Meter)
- Verify the integration connected successfully (check the integration card for errors)

**Switches missing**

- Mute Control blocks must expose channel labels
- Logic State blocks are auto-discovered — check that they exist in your Tesira configuration

**Level sliders missing**

- Level blocks must be selected during setup or assigned to a router output
- Use **Configure** on the integration card to re-run block selection

**Router entities missing**

- Level blocks must be assigned to router outputs during setup
- Ensure the router block has outputs configured in Tesira

**Connection issues**

- Confirm SSH access to the Tesira
- Ensure the Text Protocol Server is enabled
- Check firewalls (SSH/TCP)

---

## Development Notes

- Uses `asyncssh`
- Maintains separate command and subscription connections
- Designed for local, low-latency control

Contributions and improvements welcome.

---

## Support / Issues

Please open GitHub issues and include:

- relevant debug logs
- Tesira firmware version and block instance IDs
