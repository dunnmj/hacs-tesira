# Tesira Control — Home Assistant Custom Integration (HACS)

Control **Biamp Tesira** DSP systems from Home Assistant using the Tesira Text Protocol.

This is a **YAML-configured integration** (no Config Flow / UI setup).

---

## Overview

- **Domain:** `tesira_ttp`
- **Platforms:** `media_player`, `switch`
- **Configuration:** `configuration.yaml`
- **Connection:** SSH (via `asyncssh`)
- **Protocol:** Tesira Text Protocol Server
- **Action:** `tesira_ttp.send_command`

The integration maintains:
- a command connection for control
- a subscription connection for live updates (levels, mutes, source changes)

---

## Features

- Source selection via `media_player`
- Volume and mute control
- Router output control with volume and mute per zone
- Per-channel mute switches
- Real-time updates using Tesira publish subscriptions
- Raw command service for advanced/custom control

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

## Configuration (YAML only)

This integration is configured entirely in `configuration.yaml`.

> ⚠️ Changes to configuration require a Home Assistant restart.

### Example configuration

```yaml
tesira_ttp:
  - name: "Tesira DSP"
    ip_address: 192.168.1.50
    username: "admin"
    password: "your_password"
    zones:
      - "01 - Lounge Source Selector"
      - "02 - Bar Source Selector"
    mutes:
      - "01 - Lounge Inputs"
      - "02 - Bar Inputs"
    routers:
      - router_id: "ZoneRouter"
        level_blocks:
          - "Zone1Level"
          - "Zone2Level"
          - "Zone3Level"
```

### Configuration options

Each item under `tesira_ttp:` supports:

| Key | Required | Description |
|----|----|----|
| name | ✅ | Friendly name for this Tesira config block |
| ip_address | ✅ | IP address or hostname of the Tesira device |
| username | ✅ | SSH username |
| password | ✅ | SSH password |
| zones | ✅ | List of Source Selector instance IDs to expose as `media_player` entities |
| mutes | ❌ | List of Mute Block instance IDs used to create per-channel mute switches |
| routers | ❌ | List of Router configurations (see Router Outputs section below) |

---

## Entities

### Media Player (`media_player`)

A `media_player` entity is created for each instance ID listed under `zones`.

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

Router outputs provide zone-based routing with independent volume and mute control.

**Configuration Structure:**

Each router configuration requires:
- **router_id**: The instance ID of the Router block in Tesira
- **level_blocks**: A list of Level block instance IDs (one per output zone)

The integration creates one `media_player` entity for each Level block in the list. The Level blocks are mapped to Router outputs in order (first Level block = output 1, second = output 2, etc.).

**Important:** Router blocks in Tesira use:
- **0-indexed inputs** (0, 1, 2, 3, 4 for a 5-input router)
- **1-indexed outputs** (1, 2, 3, 4, 5 for a 5-output router)

This is different from Source Selectors which are 1-indexed for both sources and outputs.

**What each entity controls:**
- **Source selection**: Routes any Router input to that specific output
- **Volume control**: Adjusts the Level block volume in dB
- **Mute control**: Mutes/unmutes the Level block

**Example:**

```yaml
tesira_ttp:
  - name: "Tesira DSP"
    ip_address: 192.168.1.50
    username: "admin"
    password: "password"
    zones:
      - "MainSourceSelector"
    routers:
      - router_id: "ZoneRouter"
        level_blocks:
          - "Zone1Level"
          - "Zone2Level"
          - "Zone3Level"
```

This creates 3 media_player entities:
- Each controls routing from the ZoneRouter inputs to its respective output
- Each has independent volume and mute control via its Level block
- Entity names are derived from the Level block labels in Tesira

**Real-time updates:**

The integration subscribes to:
- Router output routing changes
- Level block volume changes
- Level block mute state changes

All three subscriptions work together to provide complete zone control.

---

### Switch (`switch`)

For each instance ID listed under `mutes`, the integration:
- Queries the mute block  
- Discovers the number of channels  
- Creates one mute switch per channel  

Each switch controls the channel mute state directly.

---

## Entity Naming Behavior (Important!)

### Media player entity names

Media player names are derived from the instance ID you provide in YAML, not queried from Tesira.

Naming rules:
- If the instance ID contains `"- "` or `"-"`, everything after that is used  
- Otherwise, the full instance ID is used  

Examples:

| Instance ID | Entity Name |
|------------|------------|
| `01 - Lounge Source Selector` | `Lounge Source Selector` |
| `MainRoomSourceSelector` | `MainRoomSourceSelector` |

You control media player naming by how you name your Tesira blocks.

---

### Switch entity names (mute channels)

Switch names are a combination of:
1. The cleaned instance ID (same logic as above)  
2. The channel label fetched directly from Tesira  

Format:

`<Instance Name> - <Input Label>`

Example:

`Lounge Inputs - Mic 1`  
`Lounge Inputs - Lectern`

Channel labels come directly from the Tesira configuration.

---

### Media player source names

Source names are pulled directly from Tesira.

For each source selector:
- The integration queries each source  
- Uses the Tesira source label as the selectable source name in Home Assistant  

---

## Actions

### `tesira.send_command`

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
    - 'SourceSelector1 set outputMute true'
    - 'SourceSelector1 set outputLevel -20.0'
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
- Ensure `zones` is defined (required)
- Verify instance IDs exactly match Tesira block instance IDs

**Switches missing**
- `mutes` is optional
- Input blocks must expose channel labels

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
- your YAML configuration (with secrets removed)
- relevant debug logs
- Tesira firmware version and block instance IDs
