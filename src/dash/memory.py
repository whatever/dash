"""Embeddings and fact extraction through Bedrock, plus prompt assembly."""

import asyncio
import json
from collections.abc import Sequence
from typing import Any, Protocol

import boto3

# Below this cosine distance a new fact counts as a repeat of a stored one.
DUPLICATE_DISTANCE = 0.08
# Above this the memory is not relevant enough to put in the prompt.
RELEVANT_DISTANCE = 0.65

EXTRACT_PROMPT = """You maintain long-term memory for a personal assistant.
Read the exchange below. List the durable facts about the user that are worth \
remembering in future conversations: preferences, people, projects, plans, accounts, \
decisions. Skip small talk, one-off requests, and anything already obvious.
Write each fact as one short standalone sentence in the third person ("The user ...").
Answer with only a JSON array of strings. Answer [] if there is nothing to keep.

<user>
{user}
</user>
<assistant>
{assistant}
</assistant>"""


class Embedder(Protocol):
    async def embed(self, text: str) -> list[float]: ...


class Extractor(Protocol):
    async def extract(self, user: str, assistant: str) -> list[str]: ...


def parse_facts(text: str) -> list[str]:
    """Pull the JSON array out of a model reply. Anything malformed means no facts."""
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end < start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item.strip() for item in data if isinstance(item, str) and item.strip()]  # pyright: ignore[reportUnknownVariableType]


def system_prompt(memories: Sequence[str]) -> str | None:
    if not memories:
        return None
    lines = "\n".join(f"- {m}" for m in memories)
    return (
        "Things you remember about the user from earlier conversations. "
        "Use them when relevant. Do not mention this list unless asked.\n" + lines
    )


class Bedrock:
    def __init__(self, embed_model: str, extract_model: str) -> None:
        # Credentials and region come from the standard AWS env chain (hermes-bedrock secret).
        self._client: Any = boto3.client("bedrock-runtime")  # pyright: ignore[reportUnknownMemberType]
        self._embed_model = embed_model
        self._extract_model = extract_model

    async def embed(self, text: str) -> list[float]:
        body = json.dumps({"inputText": text[:20000], "normalize": True})
        response = await asyncio.to_thread(
            self._client.invoke_model, modelId=self._embed_model, body=body
        )
        return list(json.loads(response["body"].read())["embedding"])

    async def extract(self, user: str, assistant: str) -> list[str]:
        prompt = EXTRACT_PROMPT.format(user=user[:8000], assistant=assistant[:8000])
        response = await asyncio.to_thread(
            self._client.converse,
            modelId=self._extract_model,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 512, "temperature": 0},
        )
        parts = response["output"]["message"]["content"]
        return parse_facts("".join(p.get("text", "") for p in parts))
