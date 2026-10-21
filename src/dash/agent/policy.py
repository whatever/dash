"""Which tools the agent is offered and which need a person's approval, from `AGENT_TOOL_POLICY`."""

from typing import Any, Literal

from pydantic import BaseModel, TypeAdapter
from pydantic_ai import RunContext, ToolDefinition
from pydantic_ai.toolsets import AbstractToolset

from dash.agent.deps import TurnDeps, call_key

Verdict = Literal["never", "ask", "auto"]
NEVER: Verdict = "never"
ASK: Verdict = "ask"
AUTO: Verdict = "auto"

_RULES = TypeAdapter(dict[str, Verdict])


class ToolPolicy(BaseModel):
    """A verdict per tool name. `<server>_*` covers every tool of that MCP server."""

    rules: dict[str, Verdict] = {}

    @classmethod
    def parse(cls, text: str) -> "ToolPolicy":
        """Return the policy written as the given JSON object, or the empty policy."""
        return cls(rules=_RULES.validate_json(text) if text.strip() else {})

    def verdict(self, tool: str) -> Verdict:
        """Return the verdict for the given tool name."""
        if tool in self.rules:
            return self.rules[tool]
        servers = [key for key in self.rules if key.endswith("_*") and tool.startswith(key[:-1])]
        return self.rules[max(servers, key=len)] if servers else AUTO

    def offered(self, toolset: AbstractToolset[TurnDeps]) -> AbstractToolset[TurnDeps]:
        """Return the given toolset without `never` tools, and with `ask` tools needing approval.

        A call a saved rule approved runs without asking.
        """

        def shown(ctx: RunContext[TurnDeps], tool: ToolDefinition) -> bool:
            return self.verdict(tool.name) != NEVER

        def asks(ctx: RunContext[TurnDeps], tool: ToolDefinition, args: dict[str, Any]) -> bool:
            if self.verdict(tool.name) != ASK:
                return False
            return call_key(tool.name, args) not in ctx.deps.approved

        return toolset.filtered(shown).approval_required(asks)
