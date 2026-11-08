# Bitaxe MCP

An MCP (Model Context Protocol) server that wraps the full HTTP API of a
[Bitaxe](https://github.com/bitaxeorg/ESP-Miner) home Bitcoin miner (ESP-Miner /
AxeOS firmware), so any MCP-aware AI client — Claude Code, Claude Desktop, or
anything else that speaks MCP — can monitor and tune your miner
conversationally instead of via raw `curl` calls.

**What this is not:** this does not make Bitcoin mining itself
"AI-assisted" or non-brute-force. SHA-256's avalanche effect means there is
no exploitable pattern in the hash search for any AI to target — see the
background research this project grew out of. This server only wraps the
device's existing *management* API (telemetry and configuration), the same
category of value as tuning convenience or fleet monitoring. The ASIC's
hash engine itself is untouched.

## Requirements

- Python 3.10+
- A Bitaxe (or compatible ESP-Miner/AxeOS device) reachable on your LAN

## Installation

```bash
pip install -e .
```

## Configuration

Copy `.env.example` to `.env` and set your device's real address:

```bash
cp .env.example .env
# edit .env: BITAXE_HOST=<your device's LAN IP>, BITAXE_PORT=80
```

`.env` is git-ignored — your device's address never gets committed. There is
no built-in default; the server fails fast with a clear error if
`BITAXE_HOST` isn't set.

## Running the server

```bash
bitaxe-mcp
# or
python -m bitaxe_mcp.server
```

It runs over stdio, the way Claude Code and Claude Desktop launch local MCP
servers as a subprocess.

## Registering with an MCP client

**Claude Code:**

```bash
claude mcp add bitaxe --env BITAXE_HOST=${BITAXE_HOST} --env BITAXE_PORT=80 -- bitaxe-mcp
```

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "bitaxe": {
      "command": "bitaxe-mcp",
      "env": {
        "BITAXE_HOST": "${BITAXE_HOST}",
        "BITAXE_PORT": "80"
      }
    }
  }
}
```

Replace `${BITAXE_HOST}` with your device's actual LAN address — never
commit a config file with a real IP in it.

## Tool reference

17 tools, covering every HTTP endpoint ESP-Miner v2.15.4 exposes except the
two WebSocket streaming endpoints (not a fit for MCP's request/response
model) and multi-device swarm endpoints (out of scope — this targets one
device).

| Tool | Endpoint | Confirm required | Description |
|---|---|---|---|
| `get_system_info` | `GET /api/system/info` | No | Full live status: hashrate, temps, power, voltage, pools, uptime, shares. |
| `get_asic_info` | `GET /api/system/asic` | No | Chip model and valid frequency/voltage option lists. |
| `get_statistics` | `GET /api/system/statistics` | No | Historical time-series stats, optionally filtered by column. |
| `get_scoreboard` | `GET /api/system/scoreboard` | No | Top 20 best-difficulty shares ever found. |
| `scan_wifi` | `GET /api/system/wifi/scan` | No | Nearby WiFi networks visible to the device. |
| `get_logs` | `GET /api/system/logs` | No | Raw text system log dump. |
| `pause_mining` | `POST /api/system/pause` | No | Pause mining (reversible). |
| `resume_mining` | `POST /api/system/resume` | No | Resume mining after a pause. |
| `identify_device` | `POST /api/system/identify` | No | Blink/chirp the device; cosmetic only. |
| `dismiss_block_found` | `POST /api/system/blockFound/dismiss` | No | Clear the "block found" banner; count is preserved. |
| `update_settings` | `PATCH /api/system` | Only for `ssid`/`wifiPass`/`hostname`/`pools`/flat stratum fields | Update tuning/display/network settings. |
| `update_pool` | `PUT /api/system/pools/{idx}` | Yes | Set a pool slot's URL/user/password/etc. |
| `delete_pool` | `DELETE /api/system/pools/{idx}` | Yes | Clear a pool slot. |
| `restart_device` | `POST /api/system/restart` | Yes | Reboot now. |
| `set_boot_partition` | `POST /api/system/boot` | Yes | Pick which OTA partition boots next. |
| `update_firmware` | `POST /api/system/OTA` | Yes | Flash new firmware from a local file. |
| `update_web_interface` | `POST /api/system/OTAWWW` | Yes | Flash a custom web UI (AxeOS's "custom frontend" feature). |

## Safety model

Every tool that can disconnect the device from your network, affect mining
payout routing, or cause real downtime requires an explicit `confirm=True`
argument, independent of whatever approval your MCP client already asks
for:

- **`update_settings`** is ungated by default, but if the settings dict
  contains (case-insensitively) `ssid`, `wifiPass`, `hostname`, `pools`, or
  any flat stratum/pool field (`stratumURL`, `stratumUser`,
  `stratumPassword`, `primaryPoolIndex`, etc. — see `RISKY_SETTINGS_KEYS`
  in `bitaxe_mcp/server.py`), it raises `ValueError` unless `confirm=True`
  is passed — these can disconnect the device from WiFi or change where
  mined rewards go.
- **`update_pool`, `delete_pool`, `restart_device`, `set_boot_partition`,
  `update_firmware`, `update_web_interface`** always require
  `confirm=True`.
- Before calling `update_pool` with `confirm=True`, double-check that
  `pool["stratumUser"]` is actually the payout address/worker you intend —
  this is exactly the kind of accidental payout-redirection risk a careless
  call could cause.
- `update_firmware` and `update_web_interface` read the local file *before*
  any network call, so a missing or unreadable path fails immediately
  instead of silently POSTing an empty body.
- Connection failures (unreachable device, dropped connection mid-request)
  are always raised as a single `BitaxeError` with a clear message — never
  a raw `httpx` exception.

## Testing

```bash
pytest
```

Tests that need a live device are automatically skipped if `BITAXE_HOST`
isn't set (or isn't in your `.env`), so the suite runs cleanly with no
hardware attached. With a device configured, they exercise it directly —
including read-only calls, a reversible no-op settings update, and pool
upsert/delete against a currently-unused slot.

## Privacy

This repository ships with no personal data: no real LAN IP, WiFi
SSID/password, Bitcoin payout address, or MAC address appears in any
tracked file. `.env.example` contains only a placeholder address
(`192.168.1.100`). Every user supplies their own `BITAXE_HOST` via a local,
git-ignored `.env` file.
