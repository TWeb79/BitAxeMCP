import os
import pathlib
import sys
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from bitaxe_mcp.client import BitaxeClient

load_dotenv()

mcp = FastMCP("Bitaxe")

RISKY_SETTINGS_KEYS = {
    "ssid", "wifiPass", "hostname", "pools",
    "stratumURL", "stratumUser", "stratumPassword", "stratumPort",
    "stratumProtocol", "stratumV2ChannelType", "stratumV2AuthorityPubkey",
    "fallbackStratumURL", "fallbackStratumUser", "fallbackStratumPassword",
    "fallbackStratumPort", "fallbackStratumProtocol", "fallbackStratumV2ChannelType",
    "fallbackStratumV2AuthorityPubkey", "primaryPoolIndex", "secondaryPoolIndex",
    "useFallbackStratum",
}
_RISKY_KEYS_LOWER = {k.lower() for k in RISKY_SETTINGS_KEYS}


def _risky_keys_in(settings: dict) -> set[str]:
    return {k for k in settings if k.lower() in _RISKY_KEYS_LOWER}


def get_client() -> BitaxeClient:
    host = os.environ.get("BITAXE_HOST")
    if not host:
        raise RuntimeError(
            "BITAXE_HOST environment variable is not set. "
            "Set it to your Bitaxe's LAN address (see .env.example)."
        )
    port = int(os.environ.get("BITAXE_PORT", "80"))
    return BitaxeClient(host=host, port=port)


def _validate_startup_config() -> None:
    """Fail fast with a clear stderr message if the server is misconfigured,
    rather than letting every tool call fail lazily inside the AI client."""
    host = os.environ.get("BITAXE_HOST")
    if not host:
        print(
            "Error: BITAXE_HOST environment variable is not set. "
            "Set it to your Bitaxe's LAN address (see .env.example).",
            file=sys.stderr,
        )
        sys.exit(1)
    port_str = os.environ.get("BITAXE_PORT", "80")
    try:
        int(port_str)
    except ValueError:
        print(f"Error: BITAXE_PORT must be an integer, got {port_str!r}.", file=sys.stderr)
        sys.exit(1)


@mcp.tool()
async def get_system_info() -> dict:
    """Get the Bitaxe's full live status: hashrate, temperatures, power, voltage, pool config, uptime, and share counts."""
    return await get_client().get_system_info()


@mcp.tool()
async def get_asic_info() -> dict:
    """Get the ASIC chip model and its valid frequency/voltage option lists for this hardware."""
    return await get_client().get_asic_info()


@mcp.tool()
async def get_statistics(columns: list[str] | None = None) -> dict:
    """Get historical time-series stats (e.g. hashrate, temperature, power). Optionally filter to specific column names."""
    return await get_client().get_statistics(columns)


@mcp.tool()
async def get_scoreboard() -> list[dict]:
    """Get the top 20 best-difficulty shares this device has ever found."""
    return await get_client().get_scoreboard()


@mcp.tool()
async def scan_wifi() -> dict:
    """Scan for WiFi networks visible to the device. Note: on some hardware this briefly disrupts the device's own WiFi connection."""
    return await get_client().scan_wifi()


@mcp.tool()
async def get_logs() -> str:
    """Get the device's raw text system log."""
    return await get_client().get_logs()


@mcp.tool()
async def pause_mining() -> dict:
    """Pause mining. Reversible; call resume_mining to continue."""
    return await get_client().pause_mining()


@mcp.tool()
async def resume_mining() -> dict:
    """Resume mining after a pause."""
    return await get_client().resume_mining()


@mcp.tool()
async def identify_device() -> dict:
    """Make the device blink/chirp so you can physically identify it. Cosmetic only."""
    return await get_client().identify_device()


@mcp.tool()
async def dismiss_block_found() -> dict:
    """Clear the device's 'block found' notification banner. The block-found count is preserved."""
    return await get_client().dismiss_block_found()


@mcp.tool()
async def update_settings(settings: dict, confirm: bool = False) -> str:
    """Update Bitaxe settings (any subset of: frequency, coreVoltage, autofanspeed,
    manualFanSpeed, minFanSpeed, temptarget, overclockEnabled, displayTimeout,
    rotation, invertscreen, statsFrequency, display, hostname, ssid, wifiPass, pools).

    Changing ssid, wifiPass, hostname, pools, or any flat stratum/pool field
    (stratumURL, stratumUser, stratumPassword, primaryPoolIndex, etc. — see
    RISKY_SETTINGS_KEYS) requires confirm=True — these can disconnect the
    device from the network or affect mining payout routing. The check is
    case-insensitive.
    """
    risky = _risky_keys_in(settings)
    if risky and not confirm:
        raise ValueError(
            f"Changing {sorted(risky)} requires confirm=True "
            "(can disconnect the device or affect payout routing)."
        )
    result = await get_client().update_settings(settings)
    return f"Settings updated: {result}"


@mcp.tool()
async def update_pool(idx: int, pool: dict, confirm: bool = False) -> str:
    """Set pool slot idx (0-7): stratumURL, stratumPort, stratumUser (wallet/worker),
    stratumPassword, protocol, TLS, etc.

    Requires confirm=True. Before calling with confirm=True, double-check that
    pool["stratumUser"] is the payout address/worker you actually intend —
    this controls where mined rewards are routed.
    """
    if not confirm:
        raise ValueError("update_pool requires confirm=True (changes payout routing).")
    result = await get_client().update_pool(idx, pool)
    return f"Pool {idx} updated: {result}"


@mcp.tool()
async def delete_pool(idx: int, confirm: bool = False) -> str:
    """Clear pool slot idx (0-7). The device itself refuses to delete whichever
    slot is currently the active primary or fallback pool.

    Requires confirm=True.
    """
    if not confirm:
        raise ValueError("delete_pool requires confirm=True (removes pool configuration).")
    result = await get_client().delete_pool(idx)
    return f"Pool {idx} deleted: {result}"


@mcp.tool()
async def restart_device(confirm: bool = False) -> str:
    """Reboot the device now. Causes a brief mining interruption.

    Requires confirm=True.
    """
    if not confirm:
        raise ValueError("restart_device requires confirm=True (causes a reboot).")
    result = await get_client().restart_device()
    return f"Restart initiated: {result}"


@mcp.tool()
async def set_boot_partition(partition: str, confirm: bool = False) -> str:
    """Pick which OTA partition (e.g. ota_0, ota_1, factory) boots next.

    Requires confirm=True.
    """
    if not confirm:
        raise ValueError("set_boot_partition requires confirm=True (changes next-boot firmware).")
    result = await get_client().set_boot_partition(partition)
    return f"Boot partition set: {result}"


@mcp.tool()
async def update_firmware(file_path: str, confirm: bool = False) -> str:
    """Flash new firmware (an esp-miner.bin-style image) from a local file path via OTA.

    Requires confirm=True. Reads the file locally before any network call, so a
    missing/unreadable file fails immediately rather than sending an empty body.
    """
    if not confirm:
        raise ValueError("update_firmware requires confirm=True (flashes running firmware).")
    data = pathlib.Path(file_path).read_bytes()
    result = await get_client().update_firmware(data)
    return f"Firmware update: {result}"


@mcp.tool()
async def update_web_interface(file_path: str, confirm: bool = False) -> str:
    """Flash a custom web UI (SPIFFS 'www' image) from a local file path and enable it.
    This is AxeOS's "custom frontend" feature — it replaces the dashboard's web UI
    assets only; it has no connection to the ASIC's hash search.

    Requires confirm=True. Reads the file locally before any network call, so a
    missing/unreadable file fails immediately rather than sending an empty body.
    """
    if not confirm:
        raise ValueError("update_web_interface requires confirm=True (replaces the device's web UI).")
    data = pathlib.Path(file_path).read_bytes()
    result = await get_client().update_web_interface(data)
    return f"Web interface update: {result}"


def main() -> None:
    _validate_startup_config()
    mcp.run()


if __name__ == "__main__":
    main()
