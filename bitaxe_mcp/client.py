import httpx


class BitaxeError(Exception):
    """Raised for any Bitaxe API failure: unreachable device, auth, or a bad request."""


def _parse_json_or_text(response: httpx.Response) -> dict:
    try:
        return response.json()
    except ValueError:
        return {"message": response.text}


class BitaxeClient:
    """Thin async HTTP wrapper over the ESP-Miner/AxeOS HTTP API."""

    def __init__(
        self,
        host: str,
        port: int = 80,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.transport = transport

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = f"http://{self.host}:{self.port}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as http:
                response = await http.request(method, url, **kwargs)
        except httpx.TransportError as exc:
            raise BitaxeError(
                f"Bitaxe at {self.host}:{self.port} is unreachable: {exc}"
            ) from exc

        if response.status_code == 401:
            raise BitaxeError("Unauthorized — client network not permitted by the device")
        if response.status_code == 400:
            body = _parse_json_or_text(response)
            message = body.get("message", response.text) if isinstance(body, dict) else response.text
            raise BitaxeError(message)
        if response.status_code == 500:
            raise BitaxeError(f"Device internal error: {response.text}")
        if response.is_error:
            raise BitaxeError(f"HTTP {response.status_code}: {response.text}")

        return response

    async def get_system_info(self) -> dict:
        response = await self._request("GET", "/api/system/info")
        return _parse_json_or_text(response)

    async def get_asic_info(self) -> dict:
        response = await self._request("GET", "/api/system/asic")
        return _parse_json_or_text(response)

    async def get_statistics(self, columns: list[str] | None = None) -> dict:
        params = {"columns": ",".join(columns)} if columns else None
        response = await self._request("GET", "/api/system/statistics", params=params)
        return _parse_json_or_text(response)

    async def get_scoreboard(self) -> list[dict]:
        response = await self._request("GET", "/api/system/scoreboard")
        return _parse_json_or_text(response)

    async def scan_wifi(self) -> dict:
        response = await self._request("GET", "/api/system/wifi/scan")
        return _parse_json_or_text(response)

    async def get_logs(self) -> str:
        response = await self._request("GET", "/api/system/logs")
        return response.text

    async def update_settings(self, settings: dict) -> dict:
        response = await self._request("PATCH", "/api/system", json=settings)
        return _parse_json_or_text(response)

    async def pause_mining(self) -> dict:
        response = await self._request("POST", "/api/system/pause")
        return _parse_json_or_text(response)

    async def resume_mining(self) -> dict:
        response = await self._request("POST", "/api/system/resume")
        return _parse_json_or_text(response)

    async def identify_device(self) -> dict:
        response = await self._request("POST", "/api/system/identify")
        return _parse_json_or_text(response)

    async def dismiss_block_found(self) -> dict:
        response = await self._request("POST", "/api/system/blockFound/dismiss")
        return _parse_json_or_text(response)

    async def update_pool(self, idx: int, pool: dict) -> dict:
        response = await self._request("PUT", f"/api/system/pools/{idx}", json=pool)
        return _parse_json_or_text(response)

    async def delete_pool(self, idx: int) -> dict:
        response = await self._request("DELETE", f"/api/system/pools/{idx}")
        return _parse_json_or_text(response)

    async def restart_device(self) -> dict:
        response = await self._request("POST", "/api/system/restart")
        return _parse_json_or_text(response)

    async def set_boot_partition(self, partition: str) -> dict:
        response = await self._request("POST", "/api/system/boot", json={"partition": partition})
        return _parse_json_or_text(response)

    async def update_firmware(self, firmware_bytes: bytes) -> str:
        response = await self._request(
            "POST", "/api/system/OTA",
            content=firmware_bytes,
            headers={"Content-Type": "application/octet-stream"},
        )
        return response.text

    async def update_web_interface(self, www_bytes: bytes) -> str:
        response = await self._request(
            "POST", "/api/system/OTAWWW",
            content=www_bytes,
            headers={"Content-Type": "application/octet-stream"},
        )
        return response.text
