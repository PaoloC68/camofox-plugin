"""CamoFox media tool — screenshots, resource extraction, downloads."""

from helpers.tool import Tool, Response

from usr.plugins.camofox_browser.helpers.client import (
    CamofoxClient,
    CamofoxConnectionError,
    CamofoxApiError,
    CamofoxAuthError,
)
from usr.plugins.camofox_browser.helpers.config import get_config
from usr.plugins.camofox_browser.helpers.user_id import resolve_user_id

_BLOB_URL_LIMIT = 25

# Module-level singleton client.
_client_instance: CamofoxClient | None = None


def _get_client() -> CamofoxClient:
    global _client_instance
    if _client_instance is None:
        cfg = get_config()
        _client_instance = CamofoxClient(
            base_url=cfg["server_url"],
            api_key=cfg.get("api_key", ""),
            admin_key=cfg.get("admin_key", ""),
        )
    return _client_instance


class CamofoxMedia(Tool):
    """CamoFox media capture and download operations.

    Supported actions (self.args["action"]):
        screenshot, extract_resources, batch_download,
        resolve_blobs, list_downloads, get_download, delete_download
    """

    async def execute(self, **kwargs) -> Response:
        action = self.args.get("action", "")
        user_id = resolve_user_id(self.agent)

        try:
            result = await self._dispatch(action, user_id)
            return Response(message=result, break_loop=False)
        except CamofoxConnectionError as e:
            return Response(
                message=f"CamoFox server unreachable: {e}",
                break_loop=False,
            )
        except CamofoxAuthError as e:
            return Response(
                message=f"CamoFox authentication failed: {e}",
                break_loop=False,
            )
        except CamofoxApiError as e:
            return Response(
                message=f"CamoFox error ({e.status}): {e}",
                break_loop=False,
            )
        except Exception as e:
            return Response(
                message=f"Unexpected error in camofox_media: {e}",
                break_loop=False,
            )

    async def _dispatch(self, action: str, user_id: str) -> str:
        client = _get_client()
        a = self.args

        if action == "screenshot":
            tab_id = a["tabId"]
            fmt = a.get("format", "png")
            full_page = str(a.get("full_page", "false")).lower() == "true"
            data = await client.post(
                f"/tabs/{tab_id}/screenshot",
                data={"format": fmt, "fullPage": full_page, "userId": user_id},
            )
            url = data.get("url", data.get("path", ""))
            return f"Screenshot captured: {url}"

        elif action == "extract_resources":
            tab_id = a["tabId"]
            resource_type = a.get("type", "all")
            data = await client.get(
                f"/tabs/{tab_id}/resources?userId={user_id}&type={resource_type}"
            )
            resources = data if isinstance(data, list) else data.get("resources", [])
            if not resources:
                return f"No resources of type {resource_type!r} found in tab {tab_id}."
            return f"Found {len(resources)} resource(s) in tab {tab_id}: {resources}"

        elif action == "batch_download":
            urls = a.get("urls", [])
            if isinstance(urls, str):
                urls = [u.strip() for u in urls.split(",") if u.strip()]
            save_dir = a.get("save_dir", "")
            body: dict = {"urls": urls, "userId": user_id}
            if save_dir:
                body["saveDir"] = save_dir
            data = await client.post("/downloads/batch", data=body)
            count = data.get("queued", len(urls))
            return f"Queued {count} download(s): {data}"

        elif action == "resolve_blobs":
            urls = a.get("urls", [])
            if isinstance(urls, str):
                urls = [u.strip() for u in urls.split(",") if u.strip()]
            if len(urls) > _BLOB_URL_LIMIT:
                return (
                    f"Too many blob URLs: {len(urls)} provided, "
                    f"maximum is {_BLOB_URL_LIMIT}. Split into smaller batches."
                )
            tab_id = a["tabId"]
            data = await client.post(
                f"/tabs/{tab_id}/resolve-blobs",
                data={"urls": urls, "userId": user_id},
            )
            return f"Resolved {len(urls)} blob URL(s): {data}"

        elif action == "list_downloads":
            data = await client.get(f"/downloads?userId={user_id}")
            downloads = data if isinstance(data, list) else data.get("downloads", [])
            if not downloads:
                return "No downloads in queue."
            return f"Downloads ({len(downloads)}): {downloads}"

        elif action == "get_download":
            download_id = a["downloadId"]
            data = await client.get(f"/downloads/{download_id}?userId={user_id}")
            return f"Download {download_id}: {data}"

        elif action == "delete_download":
            download_id = a["downloadId"]
            data = await client.delete(f"/downloads/{download_id}?userId={user_id}")
            return f"Download {download_id} deleted: {data}"

        else:
            return (
                f"Unknown action: {action!r}. Valid actions: "
                "screenshot, extract_resources, batch_download, "
                "resolve_blobs, list_downloads, get_download, delete_download"
            )

    def get_log_object(self):
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://image {self.agent.agent_name}: CamoFox Media",
            content="",
            kvps=self.args,
        )
