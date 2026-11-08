# Bitaxe MCP Server — Design

## Purpose

Wrap the Bitaxe/ESP-Miner (AxeOS) HTTP API in an MCP server so any MCP-aware AI
client (Claude Code, Claude Desktop, etc.) can monitor and tune a home Bitaxe
miner conversationally instead of via manual `curl` calls. This formalizes
what was done manually throughout the originating conversation (reading
`/api/system/info`, PATCHing settings, POSTing an OTA firmware update) into a
reusable tool.

Non-goal: this does **not** make Bitcoin mining itself "AI-assisted" or
non-brute-force. It only wraps the device's existing management API
(telemetry + configuration), which is a separate, legitimate category of
value (operational tuning convenience) established earlier in the
conversation's research. The hash search itself is untouched.

## Scope

- Single Bitaxe device, not a multi-device "swarm."
- Host/port configurable via environment variables; `BITAXE_HOST` has **no
  built-in default** (fails fast with a clear error if unset) so no
  particular user's LAN address is baked into the code or shipped in the
  public repo; default port `80`.
- No authentication exists on the AxeOS HTTP API itself (confirmed live
  against the real device this session) — the server's only access control
  is "can this process reach that IP," same as any other LAN client.
- Source of truth for endpoints/schemas: ESP-Miner's own
  `main/http_server/openapi.yaml` (fetched at firmware v2.15.4, the version
  currently running on the target device) plus the handler implementations in
  `main/http_server/http_server.c` for the two endpoints absent from the
  OpenAPI doc (`PUT`/`DELETE /api/system/pools/{idx}`).

## Architecture

Two files, one small package:

- **`bitaxe_client.py`** — a thin async HTTP client (httpx) with one method
  per API endpoint. Responsible for: building requests, raising a single
  clear exception type (`BitaxeError`) on connection failure, timeout, or a
  non-2xx response (with the device's own error body surfaced in the message
  where available). Contains no MCP-specific code and no safety/confirmation
  logic — it is a faithful, low-level wrapper, independently testable against
  the real device.
- **`bitaxe_server.py`** — defines the MCP tools using `FastMCP` from the
  official `mcp` Python SDK. Each tool: validates/shapes arguments, applies
  the confirm-gating rules below, calls the matching `bitaxe_client` method,
  and returns a plain-text or small-JSON summary (not the raw device
  response) so an AI client gets a readable result. Docstrings are the tool
  descriptions an MCP client sees, so each one explains what the underlying
  field/action actually does, not just its name.

Transport: stdio (`mcp.run()` default), matching how Claude Code/Claude
Desktop launch local MCP servers as a subprocess.

Config: `BITAXE_HOST` env var (required, no default), `BITAXE_PORT`
(default `80`). No credentials to manage, since the device has none.
Local development uses a `.env` file (git-ignored) holding the real
`BITAXE_HOST`; the repo ships only `.env.example` with a placeholder address
(e.g. `192.168.1.100`).

## Tool catalog

### Read-only (no gating)

| Tool | Endpoint | Notes |
|---|---|---|
| `get_system_info` | `GET /api/system/info` | Full live snapshot: hashrate, temps, power, voltage, pools, uptime, shares, etc. — the `SystemInfo` schema. |
| `get_asic_info` | `GET /api/system/asic` | Chip model, default/valid frequency and voltage option lists for this hardware. |
| `get_statistics` | `GET /api/system/statistics` | Historical time series; optional `columns` filter (e.g. `hashrate,asicTemp,power`). |
| `get_scoreboard` | `GET /api/system/scoreboard` | Top 20 best-difficulty shares ever found on this device. |
| `scan_wifi` | `GET /api/system/wifi/scan` | Nearby WiFi networks visible to the device. |
| `get_logs` | `GET /api/system/logs` | Raw text log dump. |

### Mining control (no gating — instantly reversible, non-destructive)

| Tool | Endpoint | Notes |
|---|---|---|
| `pause_mining` | `POST /api/system/pause` | |
| `resume_mining` | `POST /api/system/resume` | |
| `identify_device` | `POST /api/system/identify` | Blinks/chirps the device; cosmetic only. |
| `dismiss_block_found` | `POST /api/system/blockFound/dismiss` | Clears the "block found" UI banner; count is preserved. |

### Tuning (one generic tool, conditionally gated)

| Tool | Endpoint | Notes |
|---|---|---|
| `update_settings` | `PATCH /api/system` | Accepts any subset of the `Settings` schema fields (`frequency`, `coreVoltage`, `autofanspeed`, `manualFanSpeed`, `minFanSpeed`, `temptarget`, `overclockEnabled`, `displayTimeout`, `rotation`, `invertscreen`, `statsFrequency`, `display`, `hostname`, `ssid`, `wifiPass`, `pools`, …) as a dict. |

Gating rule inside `update_settings`: if the provided dict contains any of
`ssid`, `wifiPass`, `hostname`, or `pools`, the call requires
`confirm=True` even though the tool itself is otherwise ungated — these four
can disconnect the device from the network (`ssid`/`wifiPass`) or affect
payout routing (`pools`), which is a materially different risk class than
`frequency`/`coreVoltage`/fan/display settings. The docstring states this
explicitly so an AI client sees the rule before calling it.

### Pool / wallet configuration (always `confirm=True`)

| Tool | Endpoint | Notes |
|---|---|---|
| `update_pool` | `PUT /api/system/pools/{idx}` | Upserts one pool slot (0–7): URL, port, user (wallet/worker), password, protocol, TLS, etc. Docstring explicitly tells the caller to confirm the `stratumUser` is the intended payout address before calling — this is the exact "don't let something silently redirect my payout" concern raised earlier in the conversation. |
| `delete_pool` | `DELETE /api/system/pools/{idx}` | Clears a slot. The device itself refuses to delete whichever slot is currently primary or fallback; the client surfaces that error as-is. |

### Disruptive device actions (always `confirm=True`)

| Tool | Endpoint | Notes |
|---|---|---|
| `restart_device` | `POST /api/system/restart` | Reboots now; brief mining downtime. |
| `set_boot_partition` | `POST /api/system/boot` | Picks which OTA partition (`ota_0`/`ota_1`/`factory`) boots next. |
| `update_firmware` | `POST /api/system/OTA` | Takes a local file path to a `esp-miner.bin`-style image, reads it, POSTs the raw bytes. This is what was done manually earlier via `curl --data-binary`. |
| `update_web_interface` | `POST /api/system/OTAWWW` | Flashes the SPIFFS `www` partition from a local file and flips `useCustomWWW`. **This is the "custom frontend" feature** — it replaces the dashboard's web UI assets only; it has no path into the ASIC's hash-search engine (established in the conversation's earlier research/discussion). |

That's 17 tools, covering every HTTP endpoint ESP-Miner v2.15.4 exposes
except the two WebSocket endpoints (`/api/ws`, `/api/ws/live`), which are
explicitly out of scope (see below).

## Out of scope

- **WebSocket live stats** (`/api/ws`, `/api/ws/live`) — these stream
  continuously; MCP tools are request/response. `get_system_info` and
  `get_statistics` already cover the same data via polling, which fits the
  MCP call model better. Not included in v1.
- **Swarm/fleet endpoints** — per the earlier scoping decision, this targets
  one device; swarm config exists in NVS (`NVS_CONFIG_SWARM`) but has no
  dedicated REST surface distinct from `pools`/`update_settings` to wrap.
- **Multi-device orchestration, scheduling, or any "smart search" logic** —
  explicitly not a goal; see Purpose.

## Error handling

`bitaxe_client` raises `BitaxeError(message)` for:
- Connection refused / timeout → `"Bitaxe at {host}:{port} is unreachable: {detail}"`
- HTTP 401 → `"Unauthorized — client network not permitted by the device"`
- HTTP 400 → the device's own JSON error message (field validation failures,
  e.g. frequency/voltage out of range, invalid pool index)
- HTTP 500 → `"Device internal error: {detail}"`

Every MCP tool catches `BitaxeError` and returns it as the tool's error
result (not a raw traceback), so the calling AI client sees a clear,
actionable message.

## Testing approach

- `bitaxe_client` methods: tested live against the real device (via
  `BITAXE_HOST` from a local, git-ignored `.env`, never committed) for every
  read-only endpoint and for `update_settings` with a reversible no-op
  change (set `frequency`/`coreVoltage` to their current values) to confirm
  the write path end-to-end without changing operating behavior. Any
  response captured for a fixture/test file is redacted first — `stratumUser`
  (wallet address), `ssid`, and `macAddr` replaced with placeholders — before
  it is written to a tracked file.
- `update_pool`/`delete_pool`: tested against a throwaway unused pool slot
  index (not the active primary/fallback), so the device's own
  "can't delete active pool" guard is exercised rather than real pool config.
- `restart_device`, `update_firmware`, `update_web_interface`,
  `set_boot_partition`: confirm-gating logic (missing-confirm rejection) is
  unit-tested without hitting the device; live invocation is left to the user
  to trigger deliberately, since each causes real downtime or (for OTA)
  modifies the running firmware.
- MCP tool registration/dispatch: a smoke test that starts the server and
  lists tools, confirming all 17 are registered with non-empty descriptions.

## Privacy (this repo is public on GitHub)

This project is published to a public GitHub repo, so nothing personal may
ever be committed:

- No file in the repo contains a real LAN IP, WiFi SSID/password, Bitcoin
  payout address, or MAC address. `BITAXE_HOST` is required at runtime with
  no default; the only address appearing in docs/examples is a placeholder
  (`192.168.1.100`).
- `.gitignore` excludes `.env` (the file actually holding the real
  `BITAXE_HOST`), Python build/cache artifacts, and this repo's unrelated
  `research_notes/`/`reports/` directories (deep-research output from a
  separate task in the same working directory — not part of this project).
- Before any commit, a quick `git diff --staged` / `git status` check (and,
  for this repo specifically, a grep for the known real wallet address,
  SSID, and MAC — see conversation history) confirms nothing personal slipped
  in via a captured API response or log.

## Dependencies

- `mcp` (official Python SDK, FastMCP interface)
- `httpx` (async HTTP client)
- Python 3.10+

## Delivery

Packaged as a small Python project (`pyproject.toml` + the two modules) under
this repo, plus a `README.md` covering: installation, environment variables,
the full tool list with one-line descriptions, the confirm-gating rules, and
how to register it in Claude Code's or Claude Desktop's MCP config.
