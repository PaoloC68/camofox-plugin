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


def set_vnc(user_id: str, vnc_url: str, display_mode: str) -> None:
    """Write VNC/display state for a userId."""
    data = _read()
    entry = data.get(user_id, {})
    entry["vnc_url"] = vnc_url
    entry["display_mode"] = display_mode
    entry["ts"] = time.time()
    data[user_id] = entry
    _write(data)


def set_browsing(user_id: str, active: bool, blocked: bool = False) -> None:
    """Write browsing activity state for a userId."""
    data = _read()
    entry = data.get(user_id, {})
    entry["browsing"] = active
    entry["blocked"] = blocked if active else False
    entry["ts"] = time.time()
    data[user_id] = entry
    _write(data)


def _normalize_entry(entry: dict) -> dict:
    normalized = dict(entry)
    ts = float(normalized.get("ts", 0) or 0)
    is_stale = ts and (time.time() - ts) > _BROWSING_ACTIVE_TTL_SECONDS
    if normalized.get("browsing") and not normalized.get("blocked") and is_stale:
        normalized["browsing"] = False
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
