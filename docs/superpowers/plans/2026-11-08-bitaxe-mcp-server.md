# Bitaxe MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and publish a Python MCP server that exposes all 17 tools of the ESP-Miner/AxeOS HTTP API (info, tuning, pool/wallet config, disruptive device actions), with confirm-gating on anything risky, a README, and push it to the (currently empty) GitHub remote `origin` (`https://github.com/TWeb79/BitAxeMCP.git`).

**Architecture:** A small installable package, `bitaxe_mcp/`, split into `client.py` (a thin async httpx wrapper over every endpoint, raising one `BitaxeError` type) and `server.py` (FastMCP tool definitions that call the client and apply confirm-gating). Tests run live against the real device when `BITAXE_HOST` is set (via a git-ignored `.env`), and skip gracefully otherwise so the public repo's test suite doesn't require hardware to run.

**Tech Stack:** Python 3.10+, `mcp` (official SDK, `FastMCP`), `httpx` (async), `python-dotenv` (local `.env` loading), `pytest` + `pytest-asyncio`.

**Spec:** `/Users/ai.weber/Documents/Projects/bitace/docs/superpowers/specs/2026-11-08-bitaxe-mcp-server-design.md`

## Global Constraints

- Python 3.10+; dependencies limited to `mcp`, `httpx`, `python-dotenv` (runtime) and `pytest`, `pytest-asyncio` (dev).
- `BITAXE_HOST` has no built-in default — the server must fail fast with a clear error if it's unset. `BITAXE_PORT` defaults to `80`.
- No authentication exists on the AxeOS API — nothing to manage beyond reachability.
- Exactly 17 tools, these names: `get_system_info`, `get_asic_info`, `get_statistics`, `get_scoreboard`, `scan_wifi`, `get_logs`, `pause_mining`, `resume_mining`, `identify_device`, `dismiss_block_found`, `update_settings`, `update_pool`, `delete_pool`, `restart_device`, `set_boot_partition`, `update_firmware`, `update_web_interface`.
- `update_settings(settings, confirm=False)` must require `confirm=True` whenever `settings` contains any of `ssid`, `wifiPass`, `hostname`, `pools` — even though the tool is otherwise ungated.
- `update_pool`, `delete_pool`, `restart_device`, `set_boot_partition`, `update_firmware`, `update_web_interface` always require `confirm=True`.
- WebSocket endpoints (`/api/ws`, `/api/ws/live`) and swarm/fleet endpoints are explicitly out of scope.
- This repo is public on GitHub: no file may ever contain a real LAN IP, SSID, WiFi password, Bitcoin payout address, or MAC address. `.env.example` ships a placeholder (`192.168.1.100`) only.
- `BitaxeError` message formats (verbatim from spec): unreachable → `"Bitaxe at {host}:{port} is unreachable: {detail}"`; 401 → `"Unauthorized — client network not permitted by the device"`; 400 → the device's own JSON `message`; 500 → `"Device internal error: {detail}"`.

## Review Focus

- `BITAXE_HOST` unset entirely → must fail fast with a clear, actionable error at server startup, not a confusing exception from deep inside an HTTP call. *(Task 4)*
- Device unreachable or timing out mid-call → `BitaxeClient` must raise `BitaxeError` with the specified wording, never leak a raw `httpx` exception up to the MCP client. *(Task 2)*
- `update_settings` called with a mix of safe and risky keys (e.g. `{"frequency": 565, "hostname": "x"}`) without `confirm=True` → must be rejected as a whole, since the underlying `PATCH /api/system` is one atomic call with no partial apply. *(Task 4)*
- `delete_pool` called on the index that is currently the active primary or fallback pool → the device returns a specific 400 message ("Cannot delete a pool that is currently selected..."); the client/tool must surface that message verbatim, not a generic error. *(Task 3)*
- `update_firmware`/`update_web_interface` called with a `file_path` that doesn't exist or isn't readable → must raise a clear "file not found" error *before* any network call is attempted, never silently POST an empty body. *(Task 5)*

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `bitaxe_mcp/__init__.py`
- Create: `.env.example`
- Create: `tests/__init__.py`
- Test: `tests/test_package.py`

**Interfaces:**
- Produces: `bitaxe_mcp.__version__ == "0.1.0"`; an installable package named `bitaxe-mcp`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_package.py
import bitaxe_mcp

def test_package_version():
    assert bitaxe_mcp.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_package.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bitaxe_mcp'`

- [ ] **Step 3: Create the package scaffolding**

`bitaxe_mcp/__init__.py`:
```python
__version__ = "0.1.0"
```

`pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "bitaxe-mcp"
version = "0.1.0"
description = "MCP server wrapping the Bitaxe/ESP-Miner AxeOS HTTP API"
requires-python = ">=3.10"
dependencies = [
    "mcp>=1.2.0",
    "httpx>=0.27",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23"]

[project.scripts]
bitaxe-mcp = "bitaxe_mcp.server:main"

[tool.setuptools.packages.find]
include = ["bitaxe_mcp*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

`.env.example`:
```
# Copy this file to .env and set your Bitaxe's real LAN address.
# .env is git-ignored — never commit your real device IP.
BITAXE_HOST=192.168.1.100
BITAXE_PORT=80
```

`tests/__init__.py`: empty file.

Then run: `pip install -e ".[dev]"`

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_package.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml bitaxe_mcp/__init__.py .env.example tests/__init__.py tests/test_package.py
git commit -m "chore: scaffold bitaxe-mcp package"
```

---

## Task 2: BitaxeClient read-only methods

**Files:**
- Create: `bitaxe_mcp/client.py`
- Create: `tests/conftest.py`
- Test: `tests/test_client_readonly.py`

**Interfaces:**
- Consumes: nothing beyond `httpx`.
- Produces: `class BitaxeError(Exception)`; `class BitaxeClient.__init__(self, host: str, port: int = 80, timeout: float = 10.0)`; `async def get_system_info(self) -> dict`; `async def get_asic_info(self) -> dict`; `async def get_statistics(self, columns: list[str] | None = None) -> dict`; `async def get_scoreboard(self) -> list[dict]`; `async def scan_wifi(self) -> dict`; `async def get_logs(self) -> str`; private `async def _request(self, method: str, path: str, **kwargs) -> httpx.Response` used by all client methods (later tasks reuse it).

- [ ] **Step 1: Write the failing tests**

```python
# tests/conftest.py
import os
import pytest
from dotenv import load_dotenv

load_dotenv()

@pytest.fixture
def bitaxe_host():
    host = os.environ.get("BITAXE_HOST")
    if not host:
        pytest.skip("BITAXE_HOST not set — no live device configured for tests")
    return host
```

```python
# tests/test_client_readonly.py
import pytest
from bitaxe_mcp.client import BitaxeClient, BitaxeError

@pytest.fixture
def client(bitaxe_host):
    return BitaxeClient(host=bitaxe_host)

async def test_get_system_info(client):
    info = await client.get_system_info()
    assert "hashRate" in info
    assert "ASICModel" in info

async def test_get_asic_info(client):
    asic = await client.get_asic_info()
    assert "frequencyOptions" in asic
    assert "voltageOptions" in asic

async def test_get_statistics_with_columns(client):
    stats = await client.get_statistics(columns=["hashrate", "asicTemp"])
    assert "labels" in stats
    assert "statistics" in stats

async def test_get_scoreboard(client):
    board = await client.get_scoreboard()
    assert isinstance(board, list)

async def test_scan_wifi(client):
    result = await client.scan_wifi()
    assert "networks" in result

async def test_get_logs(client):
    logs = await client.get_logs()
    assert isinstance(logs, str)

async def test_unreachable_host_raises_bitaxe_error():
    # 192.0.2.1 is TEST-NET-1 (RFC 5737): guaranteed unroutable, safe to hardcode.
    client = BitaxeClient(host="192.0.2.1", timeout=1.0)
    with pytest.raises(BitaxeError, match="unreachable"):
        await client.get_system_info()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_client_readonly.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bitaxe_mcp.client'`

- [ ] **Step 3: Implement `bitaxe_mcp/client.py`**

```python
class BitaxeError(Exception):
    ...

class BitaxeClient:
    def __init__(self, host: str, port: int = 80, timeout: float = 10.0): ...
    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response: ...
    async def get_system_info(self) -> dict: ...
    async def get_asic_info(self) -> dict: ...
    async def get_statistics(self, columns: list[str] | None = None) -> dict: ...
    async def get_scoreboard(self) -> list[dict]: ...
    async def scan_wifi(self) -> dict: ...
    async def get_logs(self) -> str: ...
```

`_request` builds `httpx.AsyncClient(base_url=f"http://{host}:{port}")` per call (or reuse one stored on `self`, implementer's choice), catches `httpx.ConnectError`/`httpx.TimeoutException` and raises `BitaxeError(f"Bitaxe at {host}:{port} is unreachable: {exc}")`; on response status 401 raises `BitaxeError("Unauthorized — client network not permitted by the device")`; on 400 raises `BitaxeError(response.json().get("message", response.text))`; on 500 raises `BitaxeError(f"Device internal error: {response.text}")`; otherwise returns the response. `get_statistics` passes `params={"columns": ",".join(columns)}` when `columns` is given. `get_logs` returns `response.text` (not JSON); all other methods return `response.json()`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_client_readonly.py -v`
Expected: PASS (6 live tests skip if `BITAXE_HOST` unset in `.env`; the unreachable-host test always runs)

- [ ] **Step 5: Commit**

```bash
git add bitaxe_mcp/client.py tests/conftest.py tests/test_client_readonly.py
git commit -m "feat: add BitaxeClient read-only methods"
```

---

## Task 3: BitaxeClient action/write methods

**Files:**
- Modify: `bitaxe_mcp/client.py`
- Test: `tests/test_client_actions.py`

**Interfaces:**
- Consumes: `BitaxeClient`, `BitaxeError`, `_request` from Task 2.
- Produces (added to `BitaxeClient`): `async def update_settings(self, settings: dict) -> dict`; `async def pause_mining(self) -> dict`; `async def resume_mining(self) -> dict`; `async def identify_device(self) -> dict`; `async def dismiss_block_found(self) -> dict`; `async def update_pool(self, idx: int, pool: dict) -> dict`; `async def delete_pool(self, idx: int) -> dict`; `async def restart_device(self) -> dict`; `async def set_boot_partition(self, partition: str) -> dict`; `async def update_firmware(self, firmware_bytes: bytes) -> str`; `async def update_web_interface(self, www_bytes: bytes) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_client_actions.py
import pytest
from bitaxe_mcp.client import BitaxeClient, BitaxeError

@pytest.fixture
def client(bitaxe_host):
    return BitaxeClient(host=bitaxe_host)

async def test_update_settings_noop(client):
    info = await client.get_system_info()
    result = await client.update_settings({
        "frequency": info["frequency"],
        "coreVoltage": int(info["coreVoltage"]),
    })
    assert result  # no exception raised means the device accepted it

async def test_pause_then_resume_mining(client):
    paused = await client.pause_mining()
    assert "message" in paused
    resumed = await client.resume_mining()
    assert "message" in resumed

async def test_identify_device(client):
    result = await client.identify_device()
    assert "message" in result

async def test_pool_upsert_and_delete_on_unused_slot(client):
    info = await client.get_system_info()
    used = {info["primaryPoolIndex"], info["secondaryPoolIndex"]}
    free_idx = None
    for idx, pool in enumerate(info["pools"]):
        if idx not in used and not pool.get("stratumURL"):
            free_idx = idx
            break
    if free_idx is None:
        pytest.skip("no free, currently-empty pool slot to safely test against")

    result = await client.update_pool(free_idx, {
        "stratumURL": "test.invalid",
        "stratumPort": 3333,
        "stratumUser": "test",
    })
    assert "updated successfully" in result["message"]

    result = await client.delete_pool(free_idx)
    assert "cleared successfully" in result["message"]

async def test_delete_active_pool_raises_bitaxe_error(client):
    info = await client.get_system_info()
    with pytest.raises(BitaxeError, match="currently selected"):
        await client.delete_pool(info["primaryPoolIndex"])

async def test_set_boot_partition_rejects_invalid_label(client):
    with pytest.raises(BitaxeError):
        await client.set_boot_partition("not_a_real_partition")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_client_actions.py -v`
Expected: FAIL with `AttributeError: 'BitaxeClient' object has no attribute 'update_settings'` (and similarly for the other new methods)

- [ ] **Step 3: Implement the action methods in `bitaxe_mcp/client.py`**

- `update_settings`: `PATCH /api/system`, `json=settings`, returns `.json()`.
- `pause_mining` / `resume_mining`: `POST /api/system/pause` / `/resume`, returns `.json()`.
- `identify_device`: `POST /api/system/identify`, returns `.json()`.
- `dismiss_block_found`: `POST /api/system/blockFound/dismiss`, returns `.json()`.
- `update_pool(idx, pool)`: `PUT /api/system/pools/{idx}`, `json=pool`, returns `.json()`.
- `delete_pool(idx)`: `DELETE /api/system/pools/{idx}`, returns `.json()`.
- `restart_device`: `POST /api/system/restart`, returns `.json()`.
- `set_boot_partition(partition)`: `POST /api/system/boot`, `json={"partition": partition}`, returns `.json()`.
- `update_firmware(firmware_bytes)`: `POST /api/system/OTA`, `content=firmware_bytes`, `headers={"Content-Type": "application/octet-stream"}`, returns `.text`.
- `update_web_interface(www_bytes)`: `POST /api/system/OTAWWW`, same pattern, returns `.text`.

All of these reuse `_request`, so the existing 400/401/500/unreachable error handling applies automatically — no new error-handling code needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_client_actions.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bitaxe_mcp/client.py tests/test_client_actions.py
git commit -m "feat: add BitaxeClient action/write methods"
```

---

## Task 4: MCP server — read-only, mining-control, and update_settings tools

**Files:**
- Create: `bitaxe_mcp/server.py`
- Test: `tests/test_server_tools.py`

**Interfaces:**
- Consumes: `BitaxeClient`, `BitaxeError` from Tasks 2–3.
- Produces: module-level `mcp = FastMCP("Bitaxe")`; `def get_client() -> BitaxeClient` (raises `RuntimeError("BITAXE_HOST environment variable is not set")` if missing); `RISKY_SETTINGS_KEYS = {"ssid", "wifiPass", "hostname", "pools"}`; `def main() -> None` (calls `mcp.run()`); tools `get_system_info`, `get_asic_info`, `get_statistics`, `get_scoreboard`, `scan_wifi`, `get_logs`, `pause_mining`, `resume_mining`, `identify_device`, `dismiss_block_found`, `update_settings(settings: dict, confirm: bool = False)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_server_tools.py
import os
import pytest

def test_get_client_missing_host_raises(monkeypatch):
    monkeypatch.delenv("BITAXE_HOST", raising=False)
    import importlib
    import bitaxe_mcp.server as server
    importlib.reload(server)
    with pytest.raises(RuntimeError, match="BITAXE_HOST"):
        server.get_client()

async def test_update_settings_rejects_risky_key_without_confirm(monkeypatch):
    import bitaxe_mcp.server as server
    with pytest.raises(ValueError, match="confirm=True"):
        await server.update_settings.fn({"hostname": "newname"})

async def test_update_settings_rejects_mixed_keys_without_confirm():
    import bitaxe_mcp.server as server
    with pytest.raises(ValueError, match="confirm=True"):
        await server.update_settings.fn({"frequency": 565, "hostname": "x"})

async def test_update_settings_allows_safe_keys_without_confirm(monkeypatch):
    import bitaxe_mcp.server as server
    from unittest.mock import AsyncMock

    fake_client = AsyncMock()
    fake_client.update_settings.return_value = {"status": "success"}
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = await server.update_settings.fn({"frequency": 565})
    fake_client.update_settings.assert_awaited_once_with({"frequency": 565})
    assert "success" in result or "updated" in result.lower()

async def test_tool_registration_includes_expected_names():
    import bitaxe_mcp.server as server
    tools = await server.mcp.list_tools()
    names = {t.name for t in tools}
    expected = {
        "get_system_info", "get_asic_info", "get_statistics", "get_scoreboard",
        "scan_wifi", "get_logs", "pause_mining", "resume_mining",
        "identify_device", "dismiss_block_found", "update_settings",
    }
    assert expected <= names
```

Note: `server.update_settings.fn` assumes FastMCP's `@mcp.tool()` decorator exposes the original function via a `.fn` attribute (true for the current `mcp` SDK). If the installed version differs, call the tool through whatever attribute/method the installed `mcp.server.fastmcp.FastMCP` tool object exposes for direct invocation in tests — check the installed package's source if `.fn` doesn't exist. Same caveat applies to `mcp.list_tools()`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bitaxe_mcp.server'`

- [ ] **Step 3: Implement `bitaxe_mcp/server.py`**

```python
import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from bitaxe_mcp.client import BitaxeClient, BitaxeError

load_dotenv()

mcp = FastMCP("Bitaxe")

RISKY_SETTINGS_KEYS = {"ssid", "wifiPass", "hostname", "pools"}

def get_client() -> BitaxeClient:
    host = os.environ.get("BITAXE_HOST")
    if not host:
        raise RuntimeError(
            "BITAXE_HOST environment variable is not set. "
            "Set it to your Bitaxe's LAN address (see .env.example)."
        )
    port = int(os.environ.get("BITAXE_PORT", "80"))
    return BitaxeClient(host=host, port=port)

@mcp.tool()
async def get_system_info() -> dict:
    """Get the Bitaxe's full live status: hashrate, temperatures, power, voltage, pool config, uptime, and share counts."""
    return await get_client().get_system_info()

# ... get_asic_info, get_statistics, get_scoreboard, scan_wifi, get_logs: same thin-wrapper pattern,
# docstrings describing what each returns (see spec's tool catalog table for the one-liner).

@mcp.tool()
async def pause_mining() -> dict:
    """Pause mining. Reversible; call resume_mining to continue."""
    return await get_client().pause_mining()

# ... resume_mining, identify_device, dismiss_block_found: same pattern.

@mcp.tool()
async def update_settings(settings: dict, confirm: bool = False) -> str:
    """Update Bitaxe settings (any subset of: frequency, coreVoltage, autofanspeed,
    manualFanSpeed, minFanSpeed, temptarget, overclockEnabled, displayTimeout,
    rotation, invertscreen, statsFrequency, display, hostname, ssid, wifiPass, pools).

    Changing ssid, wifiPass, hostname, or pools requires confirm=True — these can
    disconnect the device from the network or affect mining payout routing.
    """
    risky = RISKY_SETTINGS_KEYS & settings.keys()
    if risky and not confirm:
        raise ValueError(
            f"Changing {sorted(risky)} requires confirm=True "
            "(can disconnect the device or affect payout routing)."
        )
    result = await get_client().update_settings(settings)
    return f"Settings updated: {result}"

def main() -> None:
    mcp.run()

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server_tools.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bitaxe_mcp/server.py tests/test_server_tools.py
git commit -m "feat: add MCP server with read-only, mining-control, and update_settings tools"
```

---

## Task 5: MCP server — pool/wallet and disruptive action tools

**Files:**
- Modify: `bitaxe_mcp/server.py`
- Test: `tests/test_server_gating.py`

**Interfaces:**
- Consumes: `get_client`, `BitaxeClient`, `BitaxeError` from Task 4.
- Produces (added tools): `update_pool(idx: int, pool: dict, confirm: bool = False)`; `delete_pool(idx: int, confirm: bool = False)`; `restart_device(confirm: bool = False)`; `set_boot_partition(partition: str, confirm: bool = False)`; `update_firmware(file_path: str, confirm: bool = False)`; `update_web_interface(file_path: str, confirm: bool = False)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_server_gating.py
import pytest
from unittest.mock import AsyncMock

@pytest.fixture
def fake_client(monkeypatch):
    import bitaxe_mcp.server as server
    client = AsyncMock()
    monkeypatch.setattr(server, "get_client", lambda: client)
    return client

async def test_update_pool_requires_confirm(fake_client):
    import bitaxe_mcp.server as server
    with pytest.raises(ValueError, match="confirm=True"):
        await server.update_pool.fn(0, {"stratumURL": "x", "stratumPort": 3333, "stratumUser": "u"})
    fake_client.update_pool.assert_not_awaited()

async def test_update_pool_calls_client_when_confirmed(fake_client):
    import bitaxe_mcp.server as server
    pool = {"stratumURL": "x", "stratumPort": 3333, "stratumUser": "u"}
    await server.update_pool.fn(0, pool, confirm=True)
    fake_client.update_pool.assert_awaited_once_with(0, pool)

async def test_delete_pool_requires_confirm(fake_client):
    import bitaxe_mcp.server as server
    with pytest.raises(ValueError, match="confirm=True"):
        await server.delete_pool.fn(0)
    fake_client.delete_pool.assert_not_awaited()

async def test_restart_device_requires_confirm(fake_client):
    import bitaxe_mcp.server as server
    with pytest.raises(ValueError, match="confirm=True"):
        await server.restart_device.fn()
    fake_client.restart_device.assert_not_awaited()

async def test_set_boot_partition_requires_confirm(fake_client):
    import bitaxe_mcp.server as server
    with pytest.raises(ValueError, match="confirm=True"):
        await server.set_boot_partition.fn("ota_0")
    fake_client.set_boot_partition.assert_not_awaited()

async def test_update_firmware_requires_confirm(fake_client, tmp_path):
    import bitaxe_mcp.server as server
    fw = tmp_path / "fw.bin"
    fw.write_bytes(b"\x00\x01")
    with pytest.raises(ValueError, match="confirm=True"):
        await server.update_firmware.fn(str(fw))
    fake_client.update_firmware.assert_not_awaited()

async def test_update_firmware_missing_file_raises_before_network_call(fake_client):
    import bitaxe_mcp.server as server
    with pytest.raises(FileNotFoundError):
        await server.update_firmware.fn("/nonexistent/path.bin", confirm=True)
    fake_client.update_firmware.assert_not_awaited()

async def test_update_web_interface_requires_confirm(fake_client, tmp_path):
    import bitaxe_mcp.server as server
    www = tmp_path / "www.bin"
    www.write_bytes(b"\x00\x01")
    with pytest.raises(ValueError, match="confirm=True"):
        await server.update_web_interface.fn(str(www))
    fake_client.update_web_interface.assert_not_awaited()

async def test_update_web_interface_missing_file_raises_before_network_call(fake_client):
    import bitaxe_mcp.server as server
    with pytest.raises(FileNotFoundError):
        await server.update_web_interface.fn("/nonexistent/path.bin", confirm=True)
    fake_client.update_web_interface.assert_not_awaited()

async def test_all_17_tools_registered():
    import bitaxe_mcp.server as server
    tools = await server.mcp.list_tools()
    names = {t.name for t in tools}
    assert names == {
        "get_system_info", "get_asic_info", "get_statistics", "get_scoreboard",
        "scan_wifi", "get_logs", "pause_mining", "resume_mining",
        "identify_device", "dismiss_block_found", "update_settings",
        "update_pool", "delete_pool", "restart_device", "set_boot_partition",
        "update_firmware", "update_web_interface",
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server_gating.py -v`
Expected: FAIL with `AttributeError: module 'bitaxe_mcp.server' has no attribute 'update_pool'`

- [ ] **Step 3: Implement the 6 tools in `bitaxe_mcp/server.py`**

Each follows: `if not confirm: raise ValueError("<action> requires confirm=True ...")`, then (for the two file-based tools) `data = pathlib.Path(file_path).read_bytes()` — a missing file raises `FileNotFoundError` naturally here, before `get_client()` or any network call — then calls the matching `BitaxeClient` method and returns a short success string. `update_pool`'s docstring explicitly tells the caller to confirm `pool["stratumUser"]` is the intended payout address before calling with `confirm=True`. `update_web_interface`'s docstring notes this is the AxeOS "custom frontend" feature — it replaces the dashboard's web UI assets, not anything related to the hash search.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server_gating.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bitaxe_mcp/server.py tests/test_server_gating.py
git commit -m "feat: add pool/wallet and disruptive device-action tools with confirm-gating"
```

---

## Task 6: README

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: the finished tool catalog from Tasks 4–5 (17 tool names + one-line descriptions, drawn from the spec's tool catalog table).

- [ ] **Step 1: Write `README.md`**

Sections, in order: **Overview** (what this is, and the explicit non-goal that it does not make mining "AI-assisted" — it wraps the device's management API only); **Requirements** (Python 3.10+, a Bitaxe on the same LAN); **Installation** (`pip install -e .`); **Configuration** (copy `.env.example` to `.env`, set `BITAXE_HOST`/`BITAXE_PORT`; note `.env` is git-ignored); **Running the server** (`bitaxe-mcp` or `python -m bitaxe_mcp.server`); **Registering with an MCP client** (a Claude Code `claude mcp add` example and a `claude_desktop_config.json` snippet, both using `${BITAXE_HOST}` placeholders, never a real IP); **Tool reference** — a markdown table with one row per tool: name, HTTP endpoint, confirm required (yes/no), one-line description; **Safety model** (explain the confirm-gating rule set, copied from Global Constraints); **Testing** (`pytest`; live tests skip automatically without `BITAXE_HOST`); **Privacy** (this repo ships no personal data; every user must supply their own `BITAXE_HOST`).

- [ ] **Step 2: Verify no personal data and full tool coverage**

Run (substitute the user's actual device IP/SSID/wallet patterns, kept out of this tracked file): `grep -niE "<redacted-personal-data-patterns>" README.md`
Expected: no output (empty)

Run: `grep -c '^| \`' README.md` (or equivalent count of tool-table rows)
Expected: 17

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add README"
```

---

## Task 7: Finalize and publish to GitHub

**Files:** none (repo-wide verification and publish step).

- [ ] **Step 1: Repo-wide personal-data guard**

Run (substitute the user's actual device IP/SSID/wallet/MAC patterns, kept out of this tracked file): `grep -rniE "<redacted-personal-data-patterns>" --exclude-dir=.git .`
Expected: no output (empty). If anything matches, fix it before proceeding — do not push.

- [ ] **Step 2: Review what will be pushed**

Run: `git status` and `git log --oneline`
Expected: only `bitaxe_mcp/`, `tests/`, `pyproject.toml`, `.env.example`, `.gitignore`, `README.md`, and `docs/superpowers/` are tracked; no `.env`, no `research_notes/`, no `reports/`, no `.claude/`.

- [ ] **Step 3: Push to the configured remote**

Run: `git push -u origin master`
Expected: push succeeds; GitHub shows the branch.

- [ ] **Step 4: Verify the push**

Run: `git ls-remote origin` and compare the `master` ref to `git rev-parse HEAD`
Expected: they match.
