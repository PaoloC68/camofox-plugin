import aiohttp
import asyncio
import logging

logger = logging.getLogger(__name__)


class CamofoxConnectionError(Exception):
    """CamoFox server is unreachable."""
    pass


class CamofoxApiError(Exception):
    """CamoFox server returned an error response."""
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(f"CamoFox API error ({status}): {message}")


class CamofoxAuthError(CamofoxApiError):
    """CamoFox server rejected authentication."""
    pass


class CamofoxClient:
    """Async HTTP client for CamoFox REST API."""

    def __init__(self, base_url: str, api_key: str = "", admin_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.admin_key = admin_key
        self._initialized = False
        self._session: aiohttp.ClientSession | None = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    def _build_headers(self, path: str) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.admin_key and "/stop" in path:
            headers["x-admin-key"] = self.admin_key
        return headers

    async def ensure_initialized(self):
        """Lazy health-check on first use. Logs warning if unreachable."""
        if self._initialized:
            return
        self._initialized = True
        try:
            await self.get("/health")
            logger.info("CamoFox server reachable at %s", self.base_url)
        except CamofoxConnectionError:
            logger.warning(
                "CamoFox server unreachable at %s. Tools will return connection errors.",
                self.base_url,
            )
        except Exception as e:
            logger.warning("CamoFox health check failed: %s", e)

    async def request(self, method: str, path: str, data: dict | None = None, **kwargs) -> dict:
        """Send request to CamoFox server, return parsed JSON."""
        url = f"{self.base_url}{path}"
        headers = self._build_headers(path)
        session = self._get_session()

        try:
            async with session.request(
                method, url, json=data, headers=headers, **kwargs
            ) as resp:
                if resp.status == 401 or resp.status == 403:
                    text = await resp.text()
                    raise CamofoxAuthError(resp.status, text)
                if resp.status >= 400:
                    # Try to get structured error from JSON response
                    error_detail = ""
                    try:
                        err_json = await resp.json()
                        error_detail = err_json.get("error", err_json.get("message", ""))
                        if not error_detail:
                            error_detail = str(err_json)
                    except Exception:
                        error_detail = await resp.text()
                    raise CamofoxApiError(
                        resp.status,
                        f"{method} {path} -> {error_detail}"
                    )
                try:
                    return await resp.json()
                except Exception:
                    # Some endpoints return non-JSON (e.g., screenshots)
                    text = await resp.text()
                    return {"ok": True, "raw": text}
        except aiohttp.ClientConnectorError as e:
            raise CamofoxConnectionError(
                f"Cannot connect to CamoFox at {self.base_url}: {e}"
            ) from e
        except (CamofoxApiError, CamofoxAuthError, CamofoxConnectionError):
            raise
        except Exception as e:
            raise CamofoxApiError(0, f"{method} {path} -> unexpected: {e}") from e

    async def get(self, path: str, **kwargs) -> dict:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, data: dict | None = None, **kwargs) -> dict:
        return await self.request("POST", path, data=data, **kwargs)

    async def delete(self, path: str, **kwargs) -> dict:
        return await self.request("DELETE", path, **kwargs)

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
