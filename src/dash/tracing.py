import os


def setup() -> None:
    """Send OpenTelemetry traces to Phoenix if PHOENIX_COLLECTOR_ENDPOINT is set."""
    if not os.environ.get("PHOENIX_COLLECTOR_ENDPOINT"):
        return
    from openinference.instrumentation.bedrock import BedrockInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from phoenix.otel import register

    provider = register(project_name=os.environ.get("PHOENIX_PROJECT_NAME") or "dash", batch=True)
    BedrockInstrumentor().instrument(tracer_provider=provider)
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)
