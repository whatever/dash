from pydantic_ai import CancellationToken, UsageLimits
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import DeltaToolCall
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.toolsets import FunctionToolset

from dash.agent import build_model, history
from dash.agent.engine import StreamedParts
from dash.agent.events import Delta
from tests.fakes import ScriptedModel


def test_model_name_passes_through_without_a_base_url() -> None:
    assert build_model("bedrock:global.anthropic.claude-opus-5-5") == (
        "bedrock:global.anthropic.claude-opus-5-5"
    )


def test_base_url_selects_an_openai_compatible_model() -> None:
    model = build_model("dash-opus", "http://litellm:4000/v1", "sk-test")

    assert isinstance(model, OpenAIChatModel)
    assert model.model_name == "dash-opus"
    assert model.base_url.rstrip("/") == "http://litellm:4000/v1"


def test_a_replaced_part_emits_only_new_text() -> None:
    parts = StreamedParts()

    assert parts.start(0, "Hel") == "Hel"
    assert parts.add(0, "lo") == "lo"
    assert parts.start(0, "Hello there") == " there"
    assert parts.start(0, "Goodbye") == ""
    assert parts.start(1, "Next") == "Next"


def test_history_round_trips_and_seeds_from_messages() -> None:
    seeded = history.seed([("user", "hi"), ("assistant", "hello"), ("user", "")])

    assert [type(m) for m in seeded.messages] == [ModelRequest, ModelResponse]
    first = seeded.messages[0].parts[0]
    assert isinstance(first, UserPromptPart)
    assert first.content == "hi"
    assert seeded.messages[1].parts == [TextPart("hello")]
    assert history.load(history.dump(seeded)).messages == seeded.messages


async def test_each_turn_gets_a_fresh_budget() -> None:
    tools = FunctionToolset[None]()

    @tools.tool_plain
    def terminal(command: str) -> str:
        """Run a command."""
        return f"ran {command}"

    call = {0: DeltaToolCall(name="terminal", json_args='{"command": "ls"}')}
    model = ScriptedModel([call], ["one"], [call], ["two"], [call], ["three"])
    engine = model.engine([tools], UsageLimits(request_limit=3))
    conversation = history.seed([])

    async def on_delta(delta: Delta) -> None:
        return None

    for prompt in ("a", "b", "c"):
        turn = await engine.run(
            conversation, prompt, instructions=None, on_delta=on_delta, cancel=CancellationToken()
        )
        conversation = turn.conversation

    assert conversation.messages[-1].parts == [TextPart("three")]
