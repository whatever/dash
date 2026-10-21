"""Which tools the agent is offered, from `AGENT_TOOL_POLICY`."""

from typing import Literal

from pydantic import BaseModel, TypeAdapter
from pydantic_ai import RunContext, ToolDefinition
from pydantic_ai.toolsets import AbstractToolset

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

    def offered(self, toolset: AbstractToolset[None]) -> AbstractToolset[None]:
        """Return the given toolset without the tools this policy does not let run."""

        def runs(ctx: RunContext[None], tool: ToolDefinition) -> bool:
            return self.verdict(tool.name) == AUTO

        return toolset.filtered(runs)
