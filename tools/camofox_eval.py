"""CamoFox eval tool — JavaScript evaluation, console capture, error tracing."""

from helpers.tool import Tool, Response

from usr.plugins.camofox_browser.helpers.client import (
    CamofoxClient,
    CamofoxConnectionError,
    CamofoxApiError,
    CamofoxAuthError,
)
from usr.plugins.camofox_browser.helpers.config import get_config
from usr.plugins.camofox_browser.helpers.user_id import resolve_user_id

# 64 KB expression limit (bytes).
_EXPRESSION_LIMIT = 64 * 1024

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


class CamofoxEval(Tool):
    """CamoFox JavaScript evaluation and console tools.

    Supported actions (self.args["action"]):
        evaluate, evaluate_extended, console, errors,
        clear_console, trace_start, trace_stop
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
                message=f"Unexpected error in camofox_eval: {e}",
                break_loop=False,
            )

    async def _dispatch(self, action: str, user_id: str) -> str:
        client = _get_client()
        a = self.args

        if action == "evaluate":
            tab_id = a["tabId"]
            expression = a.get("expression", "")
            if len(expression.encode()) > _EXPRESSION_LIMIT:
                return (
                    f"Expression too large: {len(expression.encode())} bytes "
                    f"(limit is {_EXPRESSION_LIMIT} bytes / 64 KB)."
                )
            data = await client.post(
                f"/tabs/{tab_id}/evaluate",
                data={"expression": expression, "userId": user_id},
            )
            return f"Result: {data.get('result', data)}"

        elif action == "evaluate_extended":
            tab_id = a["tabId"]
            expression = a.get("expression", "")
            if len(expression.encode()) > _EXPRESSION_LIMIT:
                return (
                    f"Expression too large: {len(expression.encode())} bytes "
                    f"(limit is {_EXPRESSION_LIMIT} bytes / 64 KB)."
                )
            include_console = str(a.get("include_console", "false")).lower() == "true"
            data = await client.post(
                f"/tabs/{tab_id}/evaluate-extended",
                data={
                    "expression": expression,
                    "includeConsole": include_console,
                    "userId": user_id,
                },
            )
            return f"Extended result: {data}"

        elif action == "console":
            tab_id = a["tabId"]
            limit = int(a.get("limit", 100))
            data = await client.get(
                f"/tabs/{tab_id}/console?userId={user_id}&limit={limit}"
            )
            entries = data if isinstance(data, list) else data.get("entries", [])
            if not entries:
                return f"Console is empty for tab {tab_id}."
            lines = [f"  [{e.get('level', 'log')}] {e.get('text', '')}" for e in entries]
            return f"Console log ({len(entries)} entries):\n" + "\n".join(lines)

        elif action == "errors":
            tab_id = a["tabId"]
            data = await client.get(f"/tabs/{tab_id}/errors?userId={user_id}")
            errors = data if isinstance(data, list) else data.get("errors", [])
            if not errors:
                return f"No JS errors in tab {tab_id}."
            lines = [f"  {e.get('message', str(e))}" for e in errors]
            return f"JS errors ({len(errors)}):\n" + "\n".join(lines)

        elif action == "clear_console":
            tab_id = a["tabId"]
            await client.post(
                f"/tabs/{tab_id}/console/clear",
                data={"userId": user_id},
            )
            return f"Console cleared for tab {tab_id}"

        elif action == "trace_start":
            tab_id = a["tabId"]
            categories = a.get("categories", "")
            body: dict = {"userId": user_id}
            if categories:
                body["categories"] = categories
            data = await client.post(f"/tabs/{tab_id}/trace/start", data=body)
            return f"Trace started for tab {tab_id}: {data}"

        elif action == "trace_stop":
            tab_id = a["tabId"]
            data = await client.post(
                f"/tabs/{tab_id}/trace/stop",
                data={"userId": user_id},
            )
            path = data.get("path", data.get("file", ""))
            return f"Trace stopped for tab {tab_id}. Output: {path or data}"

        else:
            return (
                f"Unknown action: {action!r}. Valid actions: "
                "evaluate, evaluate_extended, console, errors, "
                "clear_console, trace_start, trace_stop"
            )

    def get_log_object(self):
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://code {self.agent.agent_name}: CamoFox Eval",
            content="",
            kvps=self.args,
        )
