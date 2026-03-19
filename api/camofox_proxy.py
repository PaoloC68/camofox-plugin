"""API handler: transparent HTTP proxy to CamoFox REST API."""

from helpers.api import ApiHandler, Request

from usr.plugins.camofox_browser.helpers.client import (
    CamofoxClient,
    CamofoxConnectionError,
    CamofoxApiError,
    CamofoxAuthError,
)
from usr.plugins.camofox_browser.helpers.config import get_config


class CamofoxProxy(ApiHandler):
    """Forward an arbitrary request to the CamoFox server and return the response.

    Input:
        {
            "method": "GET" | "POST" | "DELETE" | ...,
            "path": "/some/camofox/path",
            "body": {...}   # optional, used for POST/PUT/PATCH
        }

    Responses:
        success -> {"ok": True, "data": <server_response>}
        error   -> {"ok": False, "error": str, "code": int}
    """

    @classmethod
    def requires_auth(cls) -> bool:
        return True

    async def process(self, input: dict, request: Request) -> dict:
        method = (input.get("method") or "GET").upper()
        path = input.get("path", "")
        body = input.get("body") or None

        if not path:
            return {"ok": False, "error": "Missing required field: path", "code": 400}

        cfg = get_config()
        client = CamofoxClient(
            base_url=cfg["server_url"],
            api_key=cfg.get("api_key", ""),
            admin_key=cfg.get("admin_key", ""),
        )
        try:
            data = await client.request(method, path, data=body)
            return {"ok": True, "data": data}
        except CamofoxConnectionError as e:
            return {"ok": False, "error": str(e), "code": 503}
        except CamofoxAuthError as e:
            return {"ok": False, "error": str(e), "code": e.status}
        except CamofoxApiError as e:
            return {"ok": False, "error": str(e), "code": e.status}
        finally:
            await client.close()
