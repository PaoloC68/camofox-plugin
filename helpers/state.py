"""Shared state for CamoFox plugin — FILE-BASED.

Uses /tmp/camofox_state.json so state is shared regardless of how Python
modules are loaded (different import paths, different sys.modules entries).
This avoids the module-identity problem where tools and API handlers end
up with separate in-memory dicts.
"""

import json
import os
import time

_STATE_FILE = "/tmp/camofox_plugin_state.json"
_BROWSING_ACTIVE_TTL_SECONDS = 120
_VNC_IDLE_TTL_SECONDS = 10


def _read() -> dict:
    """Read the full state dict from file."""
    try:
        with open(_STATE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write(data: dict) -> None:
    """Write the full state dict to file (atomic-ish)."""
    tmp = _STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, _STATE_FILE)


def _update_last_activity(entry: dict) -> None:
    entry["ts"] = max(
        float(entry.get("browsing_ts", 0) or 0),
        float(entry.get("vnc_ts", 0) or 0),
    )


def set_vnc(user_id: str, vnc_url: str, display_mode: str) -> None:
    """Write VNC/display state for a userId."""
    data = _read()
    entry = data.get(user_id, {})
    now = time.time()
    entry["vnc_url"] = vnc_url or ""
    entry["display_mode"] = display_mode
    entry["vnc_ts"] = now
    _update_last_activity(entry)
    data[user_id] = entry
    _write(data)


def clear_vnc(user_id: str, display_mode: str = "headless") -> None:
    """Clear any persisted VNC URL for a userId and reset the display mode."""
    data = _read()
    entry = data.get(user_id, {})
    now = time.time()
    entry["vnc_url"] = ""
    entry["display_mode"] = display_mode
    entry["vnc_ts"] = now
    _update_last_activity(entry)
    data[user_id] = entry
    _write(data)


def set_browsing(user_id: str, active: bool, blocked: bool = False) -> None:
    """Write browsing activity state for a userId."""
    data = _read()
    entry = data.get(user_id, {})
    now = time.time()
    entry["browsing"] = active
    entry["blocked"] = blocked if active else False
    entry["browsing_ts"] = now
    _update_last_activity(entry)
    data[user_id] = entry
    _write(data)


def _normalize_entry(entry: dict) -> dict:
    normalized = dict(entry)
    legacy_ts = float(normalized.get("ts", 0) or 0)
    browsing_ts = float(
        normalized.get(
            "browsing_ts",
            legacy_ts if normalized.get("browsing") or normalized.get("blocked") else 0,
        )
        or 0
    )
    vnc_ts = float(
        normalized.get(
            "vnc_ts",
            legacy_ts
            if normalized.get("vnc_url")
            or normalized.get("display_mode", "headless") != "headless"
            else 0,
        )
        or 0
    )
    normalized["browsing_ts"] = browsing_ts
    normalized["vnc_ts"] = vnc_ts
    browsing_age = time.time() - browsing_ts if browsing_ts else 0
    vnc_age = time.time() - vnc_ts if vnc_ts else 0
    is_browsing_stale = browsing_ts and browsing_age > _BROWSING_ACTIVE_TTL_SECONDS
    is_vnc_idle = vnc_ts and vnc_age > _VNC_IDLE_TTL_SECONDS
    if normalized.get("browsing") and not normalized.get("blocked") and is_browsing_stale:
        normalized["browsing"] = False
    # Clear idle VNC URL after timeout, but preserve the user-selected
    # display_mode — that reflects intent and should only change via an
    # explicit toggle.
    if (
        not normalized.get("browsing")
        and not normalized.get("blocked")
        and normalized.get("vnc_url")
        and is_vnc_idle
    ):
        normalized["vnc_url"] = ""
    _update_last_activity(normalized)
    return normalized


def get(user_id: str = "") -> dict:
    """Get state for a userId, or the most recently active if empty."""
    data = {uid: _normalize_entry(entry) for uid, entry in _read().items()}
    if user_id and user_id in data:
        return {**data[user_id], "_userId": user_id}
    # Find any active entry
    for uid, entry in data.items():
        if entry.get("browsing") or entry.get("vnc_url") or entry.get("display_mode", "headless") != "headless":
            return {**entry, "_userId": uid}
    # Return most recent entry
    if data:
        most_recent = max(data.items(), key=lambda x: x[1].get("ts", 0))
        return {**most_recent[1], "_userId": most_recent[0]}
    return {}


def get_all() -> dict:
    """Return all state (for debugging)."""
    return {uid: _normalize_entry(entry) for uid, entry in _read().items()}
