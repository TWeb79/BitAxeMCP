import pytest

def test_get_client_missing_host_raises(monkeypatch):
    monkeypatch.delenv("BITAXE_HOST", raising=False)
    import bitaxe_mcp.server as server
    with pytest.raises(RuntimeError, match="BITAXE_HOST"):
        server.get_client()

def test_main_exits_cleanly_when_host_missing(monkeypatch, capsys):
    monkeypatch.delenv("BITAXE_HOST", raising=False)
    import bitaxe_mcp.server as server
    with pytest.raises(SystemExit) as exc_info:
        server._validate_startup_config()
    assert exc_info.value.code == 1
    assert "BITAXE_HOST" in capsys.readouterr().err

def test_main_exits_cleanly_when_port_invalid(monkeypatch, capsys):
    monkeypatch.setenv("BITAXE_HOST", "203.0.113.9")
    monkeypatch.setenv("BITAXE_PORT", "notanumber")
    import bitaxe_mcp.server as server
    with pytest.raises(SystemExit) as exc_info:
        server._validate_startup_config()
    assert exc_info.value.code == 1
    assert "BITAXE_PORT" in capsys.readouterr().err

async def test_update_settings_rejects_risky_key_without_confirm():
    import bitaxe_mcp.server as server
    with pytest.raises(ValueError, match="confirm=True"):
        await server.update_settings({"hostname": "newname"})

async def test_update_settings_rejects_mixed_keys_without_confirm():
    import bitaxe_mcp.server as server
    with pytest.raises(ValueError, match="confirm=True"):
        await server.update_settings({"frequency": 565, "hostname": "x"})

async def test_update_settings_rejects_risky_key_case_insensitively():
    import bitaxe_mcp.server as server
    with pytest.raises(ValueError, match="confirm=True"):
        await server.update_settings({"SSID": "newname"})

async def test_update_settings_rejects_flat_stratum_keys_without_confirm():
    import bitaxe_mcp.server as server
    with pytest.raises(ValueError, match="confirm=True"):
        await server.update_settings({"stratumUser": "attacker-controlled-address"})

async def test_update_settings_allows_safe_keys_without_confirm(monkeypatch):
    import bitaxe_mcp.server as server
    from unittest.mock import AsyncMock

    fake_client = AsyncMock()
    fake_client.update_settings.return_value = {"status": "success"}
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = await server.update_settings({"frequency": 565})
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
