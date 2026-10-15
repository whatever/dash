import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from dash import hermes, tracing
from dash.hermes import Hermes

SSE = (
    'data: {"choices":[{"delta":{"content":"hel"}}]}\n\n'
    'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
    "data: [DONE]\n\n"
)


def test_setup_without_endpoint_is_a_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PHOENIX_COLLECTOR_ENDPOINT", raising=False)
    tracing.setup()
    assert not isinstance(trace.get_tracer_provider(), TracerProvider)


async def test_stream_records_an_llm_span(monkeypatch: pytest.MonkeyPatch) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(hermes, "tracer", provider.get_tracer("test"))
    client = Hermes("http://hermes.invalid/v1", "", "hermes-opus")
    client._client = httpx.AsyncClient(  # pyright: ignore[reportPrivateUsage]
        base_url="http://hermes.invalid/v1",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text=SSE)),
    )
    deltas = [d async for d in client.stream([{"role": "user", "content": "hi"}])]
    assert "".join(d.text for d in deltas) == "hello"
    (span,) = exporter.get_finished_spans()
    attributes = dict(span.attributes or {})
    assert attributes["openinference.span.kind"] == "LLM"
    assert attributes["llm.model_name"] == "hermes-opus"
    assert attributes["llm.input_messages.0.message.content"] == "hi"
    assert attributes["llm.output_messages.0.message.content"] == "hello"
