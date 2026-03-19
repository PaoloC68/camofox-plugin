"""Same-origin ASGI proxy for the CamoFox noVNC viewer."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
from pathlib import Path

import aiohttp

from usr.plugins.camofox_browser.helpers.viewer_url import (
    VIEWER_ROUTE_PREFIX,
    decode_viewer_token,
)

log = logging.getLogger("camofox.viewer_proxy")


class CamofoxViewerProxyApp:
    def __init__(
        self,
        *,
        novnc_root: str | Path = "/opt/noVNC",
        secret: str | None = None,
        session_factory=None,
        token_ttl_seconds: int = 3600,
    ):
        self.novnc_root = Path(novnc_root)
        self.secret = secret
        self.session_factory = session_factory or aiohttp.ClientSession
        self.token_ttl_seconds = token_ttl_seconds

    async def __call__(self, scope, receive, send):
        scope_type = scope.get("type")
        if scope_type == "http":
            await self._handle_http(scope, send)
            return
        if scope_type == "websocket":
            await self._handle_websocket(scope, receive, send)
            return
        await self._send_http(send, 404, b"Unsupported scope type")

    def _resolve_request(self, path: str) -> tuple[dict | None, str | None]:
        normalized = path or "/"
        if normalized.startswith(VIEWER_ROUTE_PREFIX):
            normalized = normalized[len(VIEWER_ROUTE_PREFIX):] or "/"
        if not normalized.startswith("/t-"):
            return None, None

        parts = normalized.split("/", 2)
        if len(parts) < 3:
            return None, None
        token = parts[1][2:]
        resource_path = "/" + parts[2]
        try:
            payload = decode_viewer_token(
                token,
                secret=self.secret,
                max_age=self.token_ttl_seconds,
            )
        except Exception:
            return None, None
        return payload, resource_path

    async def _handle_http(self, scope, send) -> None:
        payload, resource_path = self._resolve_request(scope.get("path", "/"))
        if payload is None or resource_path is None:
            await self._send_http(send, 401, b"Invalid viewer token")
            return

        relative_path = resource_path.lstrip("/") or "vnc.html"
        asset_path = (self.novnc_root / relative_path).resolve()
        try:
            asset_path.relative_to(self.novnc_root.resolve())
        except ValueError:
            await self._send_http(send, 403, b"Access denied")
            return

        if not asset_path.is_file():
            await self._send_http(send, 404, b"Asset not found")
            return

        content_type = mimetypes.guess_type(str(asset_path))[0] or "application/octet-stream"
        await self._send_http(send, 200, asset_path.read_bytes(), content_type=content_type)

    _UPSTREAM_CONNECT_RETRIES = 5
    _UPSTREAM_CONNECT_DELAY = 1.0  # seconds between retries

    async def _handle_websocket(self, scope, receive, send) -> None:
        payload, resource_path = self._resolve_request(scope.get("path", "/"))
        if payload is None or resource_path != "/websockify":
            log.warning("viewer-proxy: rejected WebSocket — invalid token or path")
            await send({"type": "websocket.close", "code": 4401})
            return

        query_string = scope.get("query_string", b"").decode()
        upstream_scheme = "wss" if payload["upstream_scheme"] == "https" else "ws"
        upstream_url = (
            f"{upstream_scheme}://{payload['upstream_host']}:{payload['upstream_port']}"
            f"{payload.get('upstream_ws_path', '/websockify')}"
        )
        if query_string:
            upstream_url = f"{upstream_url}?{query_string}"

        # Accept the WebSocket first so uvicorn doesn't log a bare 403.
        # noVNC will see a proper close frame with a reason if upstream fails.
        await send({"type": "websocket.accept"})

        session = self.session_factory()
        upstream_ws = None
        try:
            # Retry upstream connection — websockify may still be starting
            # after the display toggle.
            last_err: Exception | None = None
            for attempt in range(self._UPSTREAM_CONNECT_RETRIES):
                try:
                    upstream_ws = await session.ws_connect(upstream_url)
                    last_err = None
                    break
                except (OSError, aiohttp.ClientError) as exc:
                    last_err = exc
                    if attempt < self._UPSTREAM_CONNECT_RETRIES - 1:
                        await asyncio.sleep(self._UPSTREAM_CONNECT_DELAY)

            if last_err is not None:
                log.warning("viewer-proxy: upstream %s unreachable after %d attempts: %s",
                            upstream_url, self._UPSTREAM_CONNECT_RETRIES, last_err)
                await send({"type": "websocket.close", "code": 4502})
                return

            async def browser_to_upstream():
                while True:
                    message = await receive()
                    msg_type = message.get("type")
                    if msg_type == "websocket.receive":
                        if message.get("text") is not None:
                            await upstream_ws.send_str(message["text"])
                        elif message.get("bytes") is not None:
                            await upstream_ws.send_bytes(message["bytes"])
                    elif msg_type == "websocket.disconnect":
                        return

            async def upstream_to_browser():
                async for message in upstream_ws:
                    if message.type == aiohttp.WSMsgType.TEXT:
                        await send({"type": "websocket.send", "text": message.data})
                    elif message.type == aiohttp.WSMsgType.BINARY:
                        await send({"type": "websocket.send", "bytes": message.data})
                    elif message.type in {
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.CLOSING,
                    }:
                        return

            browser_task = asyncio.create_task(browser_to_upstream())
            upstream_task = asyncio.create_task(upstream_to_browser())
            done, pending = await asyncio.wait(
                {browser_task, upstream_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            await asyncio.gather(*done, return_exceptions=True)
        finally:
            if upstream_ws is not None:
                await upstream_ws.close()
            close = getattr(session, "close", None)
            if callable(close):
                await close()
            await send({"type": "websocket.close", "code": 1000})

    async def _send_http(
        self,
        send,
        status: int,
        body: bytes,
        *,
        content_type: str = "text/plain; charset=utf-8",
    ) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [[b"content-type", content_type.encode()]],
            }
        )
        await send({"type": "http.response.body", "body": body, "more_body": False})
