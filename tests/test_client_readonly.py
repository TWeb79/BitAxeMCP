import httpx
import pytest
from bitaxe_mcp.client import BitaxeClient, BitaxeError

@pytest.fixture
def client(bitaxe_host):
    # Real-device /wifi/scan and /logs occasionally take >10s while the
    # ASIC is also mining concurrently; use a longer timeout for these
    # live reliability tests than the client's 10s production default.
    return BitaxeClient(host=bitaxe_host, timeout=30.0)

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

async def test_mid_connection_read_error_raises_bitaxe_error(monkeypatch):
    # Observed live against the real device: a dropped connection mid-read
    # raises httpx.ReadError, a transport error distinct from
    # ConnectError/TimeoutException. It must still be wrapped as
    # BitaxeError, never leaked as a raw httpx exception.
    async def raise_read_error(self, *args, **kwargs):
        raise httpx.ReadError("connection reset")

    monkeypatch.setattr(httpx.AsyncClient, "request", raise_read_error)

    client = BitaxeClient(host="192.0.2.1")
    with pytest.raises(BitaxeError, match="unreachable"):
        await client.get_system_info()
