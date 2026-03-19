PLUGIN_NAME = "camofox_browser"

DEFAULTS = {
    "server_url": "http://localhost:9377",
    "api_key": "",
    "admin_key": "",
    "default_user_id": "",
    "default_headless": True,
    "default_geo_preset": "",
    "auto_start_server": True,
}


def normalize_headless_mode(value) -> str:
    """Normalize config values to the strings expected by CamoFox env vars."""
    if isinstance(value, bool):
        return "true" if value else "false"

    normalized = str(value).strip().lower()
    if normalized == "virtual":
        return "virtual"
    if normalized in {"false", "0", "no", "headed"}:
        return "false"
    return "true"


def get_config(project_name: str | None = None, agent_profile: str | None = None) -> dict:
    """Return plugin config merged over defaults."""
    from helpers import plugins  # lazy: avoids framework import chain at module load time

    user_cfg = plugins.get_plugin_config(
        PLUGIN_NAME,
        project_name=project_name,
        agent_profile=agent_profile,
    ) or {}
    merged = {**DEFAULTS}
    for key in DEFAULTS:
        if key in user_cfg and user_cfg[key] != "":
            merged[key] = user_cfg[key]
    return merged
