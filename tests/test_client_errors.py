import httpx
import pytest
from bitaxe_mcp.client import BitaxeClient, BitaxeError


def make_client(handler):
    return BitaxeClient(host="unit-test", transport=httpx.MockTransport(handler))


async def test_400_with_json_message_raises_bitaxe_error_with_message():
    def handler(request):
        return httpx.Response(400, json={"message": "Cannot delete a pool that is currently selected as primary or fallback"})
    client = make_client(handler)
    with pytest.raises(BitaxeError, match="currently selected"):
        await client.delete_pool(0)


async def test_400_with_plain_text_body_raises_bitaxe_error_with_text():
    def handler(request):
        return httpx.Response(400, text="Cannot delete a pool that is currently selected as primary or fallback")
    client = make_client(handler)
    with pytest.raises(BitaxeError, match="currently selected"):
        await client.delete_pool(0)


async def test_400_with_non_dict_json_body_does_not_crash():
    def handler(request):
        return httpx.Response(400, json=["unexpected", "array"])
    client = make_client(handler)
    with pytest.raises(BitaxeError):
        await client.delete_pool(0)


async def test_401_raises_unauthorized():
    def handler(request):
        return httpx.Response(401)
    client = make_client(handler)
    with pytest.raises(BitaxeError, match="Unauthorized"):
        await client.get_system_info()


async def test_500_raises_device_internal_error():
    def handler(request):
        return httpx.Response(500, text="boom")
    client = make_client(handler)
    with pytest.raises(BitaxeError, match="Device internal error"):
        await client.get_system_info()


async def test_404_raises_bitaxe_error_not_raw_json_decode_error():
    def handler(request):
        return httpx.Response(404, text="Not Found")
    client = make_client(handler)
    with pytest.raises(BitaxeError):
        await client.get_system_info()


async def test_200_with_non_json_body_returns_message_dict_not_raw_exception():
    def handler(request):
        return httpx.Response(200, text="System will restart shortly.")
    client = make_client(handler)
    result = await client.restart_device()
    assert result == {"message": "System will restart shortly."}
