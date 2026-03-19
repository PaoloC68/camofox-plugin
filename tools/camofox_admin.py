"""CamoFox admin tool — server health, presets, and process lifecycle."""

from helpers.tool import Tool, Response

from usr.plugins.camofox_browser.helpers.client import (
    CamofoxClient,
    CamofoxConnectionError,
    CamofoxApiError,
    CamofoxAuthError,
)
from usr.plugins.camofox_browser.helpers.cli import (
    CamofoxCli,
    CamofoxCliNotFoundError,
    CamofoxCliError,
)
from usr.plugins.camofox_browser.helpers.config import get_config

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


def _get_cli() -> CamofoxCli:
    cfg = get_config()
    return CamofoxCli(
        binary_path=cfg.get("binary_path") or None,
        default_user=cfg.get("default_user_id", ""),
    )


class CamofoxAdmin(Tool):
    """CamoFox administrative operations.

    Supported actions (self.args["action"]):
        health, presets, server_start, server_stop
    """

    async def execute(self, **kwargs) -> Response:
        action = self.args.get("action", "")

        try:
            result = await self._dispatch(action)
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
        except CamofoxCliNotFoundError as e:
            return Response(
                message=f"CamoFox CLI not found: {e}",
                break_loop=False,
            )
        except CamofoxCliError as e:
            return Response(
                message=f"CamoFox CLI error: {e}",
                break_loop=False,
            )
        except Exception as e:
            return Response(
                message=f"Unexpected error in camofox_admin: {e}",
                break_loop=False,
            )

    async def _dispatch(self, action: str) -> str:
        a = self.args

        if action == "health":
            client = _get_client()
            data = await client.get("/health")
            return f"CamoFox server healthy: {data}"

        elif action == "presets":
            client = _get_client()
            data = await client.get("/presets")
            presets = data if isinstance(data, list) else data.get("presets", [])
            if not presets:
                return "No geo presets configured."
            lines = [f"  {p.get('name', str(p))}" for p in presets]
            return f"Available presets ({len(presets)}):\n" + "\n".join(lines)

        elif action == "server_start":
            cli = _get_cli()
            result = await cli.execute("server", "start")
            return f"CamoFox server start requested: {result}"

        elif action == "server_stop":
            cli = _get_cli()
            result = await cli.execute("server", "stop")
            return f"CamoFox server stop requested: {result}"

        else:
            return (
                f"Unknown action: {action!r}. Valid actions: health, presets, server_start, server_stop"
            )

    def get_log_object(self):
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://settings {self.agent.agent_name}: CamoFox Admin",
            content="",
            kvps=self.args,
        )
