import os
from dataclasses import dataclass
from typing import Literal

Thinking = Literal["minimal", "low", "medium", "high", "xhigh"]
THINKING: tuple[Thinking, ...] = ("minimal", "low", "medium", "high", "xhigh")


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"{name} is not set.")
    return value


def _thinking(value: str) -> Thinking | None:
    """Return the thinking level named by the given value, or None when it is empty."""
    if not value:
        return None
    levels: dict[str, Thinking] = {t: t for t in THINKING}
    level = levels.get(value)
    if level is None:
        raise RuntimeError(f"AGENT_THINKING must be one of {', '.join(THINKING)}.")
    return level


@dataclass(frozen=True)
class Settings:
    database_url: str
    public_url: str
    redis_url: str
    agent_model: str
    agent_base_url: str
    agent_api_key: str
    agent_thinking: Thinking | None
    agent_request_limit: int
    agent_tool_call_limit: int
    agent_tool_policy: str
    agent_mcp_servers: str
    agent_web_search: bool
    sandbox_host: str
    sandbox_port: int
    sandbox_user: str
    sandbox_key_path: str
    nango_url: str
    nango_public_url: str
    nango_connect_url: str
    nango_secret_key: str
    embed_model: str
    extract_model: str
    memory_top_k: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=_env("DATABASE_URL"),
            public_url=_env("PUBLIC_URL", "").rstrip("/"),
            redis_url=_env("REDIS_URL", "redis://localhost:6379/0"),
            agent_model=_env("AGENT_MODEL", "bedrock:global.anthropic.claude-opus-5-5"),
            agent_base_url=_env("AGENT_BASE_URL", "").rstrip("/"),
            agent_api_key=_env("AGENT_API_KEY", ""),
            agent_thinking=_thinking(_env("AGENT_THINKING", "")),
            agent_request_limit=int(_env("AGENT_REQUEST_LIMIT", "60")),
            agent_tool_call_limit=int(_env("AGENT_TOOL_CALL_LIMIT", "100")),
            agent_tool_policy=_env("AGENT_TOOL_POLICY", ""),
            agent_mcp_servers=_env("AGENT_MCP_SERVERS", ""),
            agent_web_search=_env("AGENT_WEB_SEARCH", "on") != "off",
            sandbox_host=_env("SANDBOX_HOST", ""),
            sandbox_port=int(_env("SANDBOX_PORT", "2222")),
            sandbox_user=_env("SANDBOX_USER", "agent"),
            sandbox_key_path=_env("SANDBOX_KEY_PATH", "/run/secrets/sandbox/id_ed25519"),
            nango_url=_env("NANGO_URL", "http://localhost:3003").rstrip("/"),
            # Browser-facing addresses. Empty means "same as NANGO_URL".
            nango_public_url=_env("NANGO_PUBLIC_URL", "").rstrip("/"),
            nango_connect_url=_env("NANGO_CONNECT_URL", "").rstrip("/"),
            nango_secret_key=_env("NANGO_SECRET_KEY", ""),
            embed_model=_env("EMBED_MODEL", "amazon.titan-embed-text-v2:0"),
            extract_model=_env("EXTRACT_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
            memory_top_k=int(_env("MEMORY_TOP_K", "8")),
        )
