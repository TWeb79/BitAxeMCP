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
