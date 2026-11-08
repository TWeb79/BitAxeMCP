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
        await server.update_pool(0, {"stratumURL": "x", "stratumPort": 3333, "stratumUser": "u"})
    fake_client.update_pool.assert_not_awaited()

async def test_update_pool_calls_client_when_confirmed(fake_client):
    import bitaxe_mcp.server as server
    pool = {"stratumURL": "x", "stratumPort": 3333, "stratumUser": "u"}
    await server.update_pool(0, pool, confirm=True)
    fake_client.update_pool.assert_awaited_once_with(0, pool)

async def test_delete_pool_requires_confirm(fake_client):
    import bitaxe_mcp.server as server
    with pytest.raises(ValueError, match="confirm=True"):
        await server.delete_pool(0)
    fake_client.delete_pool.assert_not_awaited()

async def test_restart_device_requires_confirm(fake_client):
    import bitaxe_mcp.server as server
    with pytest.raises(ValueError, match="confirm=True"):
        await server.restart_device()
    fake_client.restart_device.assert_not_awaited()

async def test_set_boot_partition_requires_confirm(fake_client):
    import bitaxe_mcp.server as server
    with pytest.raises(ValueError, match="confirm=True"):
        await server.set_boot_partition("ota_0")
    fake_client.set_boot_partition.assert_not_awaited()

async def test_update_firmware_requires_confirm(fake_client, tmp_path):
    import bitaxe_mcp.server as server
    fw = tmp_path / "fw.bin"
    fw.write_bytes(b"\x00\x01")
    with pytest.raises(ValueError, match="confirm=True"):
        await server.update_firmware(str(fw))
    fake_client.update_firmware.assert_not_awaited()

async def test_update_firmware_missing_file_raises_before_network_call(fake_client):
    import bitaxe_mcp.server as server
    with pytest.raises(FileNotFoundError):
        await server.update_firmware("/nonexistent/path.bin", confirm=True)
    fake_client.update_firmware.assert_not_awaited()

async def test_update_web_interface_requires_confirm(fake_client, tmp_path):
    import bitaxe_mcp.server as server
    www = tmp_path / "www.bin"
    www.write_bytes(b"\x00\x01")
    with pytest.raises(ValueError, match="confirm=True"):
        await server.update_web_interface(str(www))
    fake_client.update_web_interface.assert_not_awaited()

async def test_update_web_interface_missing_file_raises_before_network_call(fake_client):
    import bitaxe_mcp.server as server
    with pytest.raises(FileNotFoundError):
        await server.update_web_interface("/nonexistent/path.bin", confirm=True)
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
