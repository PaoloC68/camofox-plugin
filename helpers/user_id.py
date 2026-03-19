from usr.plugins.camofox_browser.helpers.config import get_config


def resolve_user_id(agent=None, project_name: str | None = None) -> str:
    """Resolve CamoFox userId from config override, agent context, or fallback."""
    cfg = get_config(project_name=project_name)
    override = cfg.get("default_user_id", "").strip()
    if override:
        return override
    if agent is not None:
        agent_num = getattr(agent, "order_in_execution", 0)
        return f"a0-agent-{agent_num}"
    return "a0-default"
