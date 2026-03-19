"""API handler: CamoFox VNC/display state relay."""

from helpers.api import ApiHandler, Request

from usr.plugins.camofox_browser.helpers.client import (
    CamofoxClient,
    CamofoxConnectionError,
    CamofoxApiError,
    CamofoxAuthError,
)
from usr.plugins.camofox_browser.helpers.config import get_config
from usr.plugins.camofox_browser.helpers.user_id import resolve_user_id
from usr.plugins.camofox_browser.helpers import state as shared_state
from usr.plugins.camofox_browser.helpers.viewer_url import viewer_state_for_request


# Re-export for backward compat (tools import these)
def set_vnc_state(user_id: str, vnc_url: str, display_mode: str) -> None:
    shared_state.set_vnc(user_id, vnc_url, display_mode)


def set_browsing_active(user_id: str, active: bool, blocked: bool = False) -> None:
    shared_state.set_browsing(user_id, active, blocked)


def get_vnc_state(user_id: str = "") -> dict:
    return shared_state.get(user_id)


class CamofoxVnc(ApiHandler):

    @classmethod
    def requires_auth(cls) -> bool:
        return True

    async def process(self, input: dict, request: Request) -> dict:
        action = input.get("action", "get_state")
        user_id = input.get("userId", "")
        cfg = get_config()

        if action == "get_state":
            # Pass userId as-is (empty string = find any active state)
            return {
                "ok": True,
                "userId": user_id,
                "state": viewer_state_for_request(
                    shared_state.get(user_id),
                    request=request,
                    server_url=cfg["server_url"],
                ),
            }
        elif action == "toggle":
            return await self._toggle(
                user_id or resolve_user_id(),
                input.get("display_mode", "headed"),
                request,
            )
        elif action == "debug":
            return {"ok": True, "all_state": shared_state.get_all()}
        else:
            return {"ok": False, "error": f"Unknown action: {action!r}"}

    async def _toggle(self, user_id: str, raw_mode: str, request: Request | None = None) -> dict:
        if raw_mode in ("true", "headless"):
            display_mode = "headless"
        elif raw_mode == "virtual":
            display_mode = "virtual"
        else:
            display_mode = "headed"

        cfg = get_config()
        client = CamofoxClient(
            base_url=cfg["server_url"],
            api_key=cfg.get("api_key", ""),
            admin_key=cfg.get("admin_key", ""),
        )
        try:
            data = await client.post(
                f"/sessions/{user_id}/toggle-display",
                data={"headless": display_mode},
            )
            vnc_url = data.get("vncUrl", "")
            shared_state.set_vnc(user_id, vnc_url, display_mode)
            return {
                "ok": True,
                "userId": user_id,
                "state": viewer_state_for_request(
                    shared_state.get(user_id),
                    request=request,
                    server_url=cfg["server_url"],
                ),
            }
        except (CamofoxConnectionError, CamofoxApiError, CamofoxAuthError) as e:
            return {"ok": False, "error": str(e)}
        finally:
            await client.close()
