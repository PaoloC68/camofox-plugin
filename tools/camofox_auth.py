"""CamoFox auth tool — credential vault management (save, load, inject, list, delete)."""

from helpers.tool import Tool, Response

from usr.plugins.camofox_browser.helpers.cli import (
    CamofoxCli,
    CamofoxCliNotFoundError,
    CamofoxCliError,
)
from usr.plugins.camofox_browser.helpers.config import get_config
from usr.plugins.camofox_browser.helpers.user_id import resolve_user_id

# Module-level singleton CLI (created lazily).
_cli_instance: CamofoxCli | None = None


def _get_cli() -> CamofoxCli:
    global _cli_instance
    if _cli_instance is None:
        cfg = get_config()
        _cli_instance = CamofoxCli(
            binary_path=cfg.get("binary_path") or None,
            default_user=cfg.get("default_user_id", ""),
        )
    return _cli_instance


class CamofoxAuth(Tool):
    """CamoFox credential vault operations.

    All vault operations are performed via the local CamoFox CLI (encrypted local storage).

    Supported actions (self.args["action"]):
        save, load, inject, list, delete
    """

    async def execute(self, **kwargs) -> Response:
        action = self.args.get("action", "")
        user_id = resolve_user_id(self.agent)

        try:
            result = await self._dispatch(action, user_id)
            return Response(message=result, break_loop=False)
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
                message=f"Unexpected error in camofox_auth: {e}",
                break_loop=False,
            )

    async def _dispatch(self, action: str, user_id: str) -> str:
        cli = _get_cli()
        a = self.args

        if action == "save":
            profile = a.get("profile", user_id)
            username = a["username"]
            password = a["password"]
            label = a.get("label", "")
            cmd = ["vault", "save", "--profile", profile, "--username", username, "--password", password]
            if label:
                cmd += ["--label", label]
            result = await cli.execute(*cmd)
            return f"Credentials saved for profile {profile!r}: {result}"

        elif action == "load":
            profile = a.get("profile", user_id)
            label = a.get("label", "")
            cmd = ["vault", "load", "--profile", profile]
            if label:
                cmd += ["--label", label]
            result = await cli.execute(*cmd)
            return f"Credentials loaded for profile {profile!r}: {result}"

        elif action == "inject":
            profile = a["profile"]
            tab_id = a["tabId"]
            username_ref = a["username_ref"]
            password_ref = a["password_ref"]
            result = await cli.execute(
                "vault", "inject",
                "--profile", profile,
                "--tab", str(tab_id),
                "--username-ref", username_ref,
                "--password-ref", password_ref,
            )
            return f"Credentials injected into tab {tab_id} for profile {profile!r}: {result}"

        elif action == "list":
            profile = a.get("profile", user_id)
            result = await cli.execute("vault", "list", "--profile", profile)
            entries = result if isinstance(result, list) else result.get("entries", result)
            if not entries:
                return f"No credentials stored for profile {profile!r}."
            return f"Stored credentials for {profile!r}: {entries}"

        elif action == "delete":
            profile = a.get("profile", user_id)
            label = a.get("label", "")
            cmd = ["vault", "delete", "--profile", profile]
            if label:
                cmd += ["--label", label]
            result = await cli.execute(*cmd)
            return f"Credentials deleted for profile {profile!r}: {result}"

        else:
            return (
                f"Unknown action: {action!r}. Valid actions: save, load, inject, list, delete"
            )

    def get_log_object(self):
        # Exclude password from logged kvps.
        safe_args = {k: v for k, v in self.args.items() if k != "password"}
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://lock {self.agent.agent_name}: CamoFox Auth",
            content="",
            kvps=safe_args,
        )
