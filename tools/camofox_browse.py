"""CamoFox browser tool — tab management, navigation, and interaction."""

from helpers.tool import Tool, Response

from usr.plugins.camofox_browser.helpers.client import (
    CamofoxClient,
    CamofoxConnectionError,
    CamofoxApiError,
    CamofoxAuthError,
)
from usr.plugins.camofox_browser.helpers.config import get_config
from usr.plugins.camofox_browser.helpers.user_id import resolve_user_id
from usr.plugins.camofox_browser.helpers import state as shared_state

# Snapshot pagination: truncate at this many characters and note continuation.
_SNAPSHOT_TRUNCATE = 32_000

# Maps friendly engine names to CamoFox @search macros.
SEARCH_MACROS: dict[str, str] = {
    "google": "@google_search",
    "bing": "@bing_search",
    "duckduckgo": "@ddg_search",
    "ddg": "@ddg_search",
    "brave": "@brave_search",
    "ecosia": "@ecosia_search",
    "perplexity": "@perplexity_search",
}

# Module-level singleton client (created lazily).
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


class CamofoxBrowse(Tool):
    """Browser control: open/close tabs, navigate, interact, snapshot.

    Supported actions (self.args["action"]):
        open, close, list_tabs, navigate, snapshot,
        click, type, press, scroll, scroll_element,
        wait, back, forward, refresh, search
    """

    async def execute(self, **kwargs) -> Response:
        action = self.args.get("action", "")
        user_id = resolve_user_id(self.agent)

        # Signal that the agent is actively browsing
        shared_state.set_browsing(user_id, active=True)

        # Auto-switch to virtual display if still headless so the WebUI
        # viewer can connect immediately without waiting for a user click.
        current = shared_state.get(user_id)
        if current.get("display_mode", "headless") == "headless":
            try:
                client = _get_client()
                data = await client.post(
                    f"/sessions/{user_id}/toggle-display",
                    data={"headless": "virtual"},
                )
                vnc_url = data.get("vncUrl", "")
                shared_state.set_vnc(user_id, vnc_url, "virtual")
            except Exception:
                pass  # non-fatal: viewer just won't be available yet

        try:
            result = await self._dispatch(action, user_id)

            # Detect anti-bot/CAPTCHA blocks in snapshot results
            if action == "snapshot" and self._looks_blocked(result):
                shared_state.set_browsing(user_id, active=True, blocked=True)
                result += (
                    "\n\n⚠️ BLOCKED: This page appears to be an anti-bot challenge or CAPTCHA. "
                    "You should switch to virtual display mode so the user can solve it:\n"
                    "1. Use camofox_session → toggle_display with headless: \"virtual\"\n"
                    "2. Tell the user the browser needs their help\n"
                    "3. Wait for the user to confirm, then switch back to headless"
                )

            # Mark not browsing when closing
            if action == "close":
                shared_state.set_browsing(user_id, active=False)

            return Response(message=result, break_loop=False)
        except ValueError as e:
            return Response(message=str(e), break_loop=False)
        except CamofoxConnectionError as e:
            shared_state.set_browsing(user_id, active=False)
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
                message=f"Unexpected error in camofox_browse: {e}",
                break_loop=False,
            )

    @staticmethod
    def _looks_blocked(snapshot_text: str) -> bool:
        """Detect common anti-bot/CAPTCHA patterns in snapshot text."""
        lower = snapshot_text.lower()
        blockers = [
            "captcha", "recaptcha", "hcaptcha", "cf-challenge",
            "verify you are human", "verify you're human",
            "are you a robot", "not a robot",
            "please verify", "security check",
            "access denied", "blocked", "forbidden",
            "cloudflare", "ray id", "checking your browser",
            "just a moment", "enable javascript and cookies",
            "unusual traffic", "automated queries",
            "interstitial", "challenge-platform",
        ]
        return any(b in lower for b in blockers)

    def _base_body(self, user_id: str) -> dict:
        """Base request body with userId and sessionKey (required by CamoFox API)."""
        return {
            "userId": user_id,
            "sessionKey": self.args.get("sessionKey", "default"),
        }

    def _require_tab_id(self) -> str:
        """Extract tabId from args or raise with a helpful message."""
        tab_id = self.args.get("tabId")
        if not tab_id:
            raise ValueError(
                "Missing required 'tabId' parameter. "
                "Use action 'list_tabs' to see open tabs, or 'open' to create one first."
            )
        return tab_id

    async def _dispatch(self, action: str, user_id: str) -> str:
        client = _get_client()
        a = self.args
        base = self._base_body(user_id)

        if action == "open":
            url = a.get("url", "about:blank")
            body = {**base, "url": url}
            if a.get("preset"):
                body["preset"] = a["preset"]
            if a.get("viewport"):
                body["viewport"] = a["viewport"]
            data = await client.post("/tabs", data=body)
            tab_id = data.get("tabId", data.get("id", ""))
            return f"Opened tab {tab_id} at {url}"

        elif action == "close":
            tab_id = self._require_tab_id()
            await client.delete(f"/tabs/{tab_id}?userId={user_id}")
            return f"Closed tab {tab_id}"

        elif action == "list_tabs":
            data = await client.get(f"/tabs?userId={user_id}")
            tabs = data if isinstance(data, list) else data.get("tabs", [])
            if not tabs:
                return "No open tabs."
            lines = [f"  [{t.get('tabId', t.get('id', '?'))}] {t.get('url', '')}" for t in tabs]
            return "Open tabs:\n" + "\n".join(lines)

        elif action == "navigate":
            tab_id = self._require_tab_id()
            body = {**base}
            if a.get("url"):
                body["url"] = a["url"]
            if a.get("macro"):
                body["macro"] = a["macro"]
            if a.get("query"):
                body["query"] = a["query"]
            await client.post(f"/tabs/{tab_id}/navigate", data=body)
            return f"Navigated tab {tab_id} to {a.get('url', a.get('macro', ''))}"

        elif action == "snapshot":
            tab_id = self._require_tab_id()
            offset = a.get("offset", "")
            qs = f"userId={user_id}"
            if offset:
                qs += f"&offset={offset}"
            data = await client.get(f"/tabs/{tab_id}/snapshot?{qs}")
            text = data if isinstance(data, str) else data.get("snapshot", str(data))
            if len(text) > _SNAPSHOT_TRUNCATE:
                text = text[:_SNAPSHOT_TRUNCATE] + (
                    f"\n\n[Snapshot truncated at {_SNAPSHOT_TRUNCATE} chars. "
                    f"Use offset parameter to get more.]"
                )
            return text

        elif action == "click":
            tab_id = self._require_tab_id()
            body = {**base}
            if a.get("ref"):
                body["ref"] = a["ref"]
            elif a.get("selector"):
                body["selector"] = a["selector"]
            await client.post(f"/tabs/{tab_id}/click", data=body)
            target = a.get("ref") or a.get("selector", "")
            return f"Clicked {target!r} in tab {tab_id}"

        elif action == "type":
            tab_id = self._require_tab_id()
            body = {**base, "text": a.get("text", "")}
            if a.get("ref"):
                body["ref"] = a["ref"]
            elif a.get("selector"):
                body["selector"] = a["selector"]
            await client.post(f"/tabs/{tab_id}/type", data=body)
            target = a.get("ref") or a.get("selector", "")
            return f"Typed into {target!r} in tab {tab_id}"

        elif action == "press":
            tab_id = self._require_tab_id()
            body = {**base, "key": a.get("key", "")}
            if a.get("ref"):
                body["ref"] = a["ref"]
            elif a.get("selector"):
                body["selector"] = a["selector"]
            await client.post(f"/tabs/{tab_id}/press", data=body)
            return f"Pressed {a.get('key', '')!r} in tab {tab_id}"

        elif action == "scroll":
            tab_id = self._require_tab_id()
            direction = a.get("direction", "down")
            amount = int(a.get("amount", 3))
            await client.post(f"/tabs/{tab_id}/scroll", data={
                **base, "direction": direction, "amount": amount,
            })
            return f"Scrolled {direction} by {amount} in tab {tab_id}"

        elif action == "scroll_element":
            tab_id = self._require_tab_id()
            body = {**base, "direction": a.get("direction", "down")}
            if a.get("ref"):
                body["ref"] = a["ref"]
            elif a.get("selector"):
                body["selector"] = a["selector"]
            await client.post(f"/tabs/{tab_id}/scroll-element", data=body)
            target = a.get("ref") or a.get("selector", "")
            return f"Scrolled element {target!r} in tab {tab_id}"

        elif action == "wait":
            tab_id = self._require_tab_id()
            body = {**base}
            if a.get("timeout"):
                body["timeout"] = int(a["timeout"])
            if a.get("waitForNetwork"):
                body["waitForNetwork"] = True
            if a.get("selector"):
                body["selector"] = a["selector"]
            await client.post(f"/tabs/{tab_id}/wait", data=body)
            return f"Wait complete in tab {tab_id}"

        elif action == "back":
            tab_id = self._require_tab_id()
            await client.post(f"/tabs/{tab_id}/back", data=base)
            return f"Navigated back in tab {tab_id}"

        elif action == "forward":
            tab_id = self._require_tab_id()
            await client.post(f"/tabs/{tab_id}/forward", data=base)
            return f"Navigated forward in tab {tab_id}"

        elif action == "refresh":
            tab_id = self._require_tab_id()
            await client.post(f"/tabs/{tab_id}/refresh", data=base)
            return f"Refreshed tab {tab_id}"

        elif action == "search":
            engine = a.get("engine", "google").lower()
            query = a.get("query", "")
            macro = SEARCH_MACROS.get(engine, SEARCH_MACROS["google"])
            tab_id = a.get("tabId")
            if tab_id:
                await client.post(f"/tabs/{tab_id}/navigate", data={
                    **base, "macro": macro, "query": query,
                })
                return f"Searched {engine!r} for {query!r} in tab {tab_id}"
            else:
                data = await client.post("/tabs", data={
                    **base, "url": f"https://www.google.com/search?q={query}",
                })
                new_tab = data.get("tabId", data.get("id", ""))
                return f"Opened new tab {new_tab} searching {engine!r} for {query!r}"

        else:
            return f"Unknown action: {action!r}. Valid actions: open, close, list_tabs, navigate, snapshot, click, type, press, scroll, scroll_element, wait, back, forward, refresh, search"

    def get_log_object(self):
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://globe {self.agent.agent_name}: CamoFox Browse",
            content="",
            kvps=self.args,
        )
