"""Thin Groq SDK adapter that exposes `.invoke(messages)` and
`.with_structured_output(PydanticModel)`.

We avoid `langchain-groq` because it pins a `groq` SDK range incompatible with
the version installed in this conda env.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Type

from groq import Groq
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from app.config import settings


def _to_groq_messages(messages: list[BaseMessage]) -> list[dict[str, str]]:
    out = []
    for m in messages:
        if isinstance(m, SystemMessage):
            role = "system"
        elif isinstance(m, HumanMessage):
            role = "user"
        elif isinstance(m, AIMessage):
            role = "assistant"
        else:
            role = "user"
        out.append({"role": role, "content": m.content})
    return out


class GroqChat:
    def __init__(self, model: str, temperature: float = 0.1):
        self._client = Groq(api_key=settings.groq_api_key)
        self._model = model
        self._temperature = temperature

    def invoke(self, messages: list[BaseMessage]) -> AIMessage:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=_to_groq_messages(messages),
            temperature=self._temperature,
        )
        return AIMessage(content=resp.choices[0].message.content or "")

    def with_structured_output(self, schema: Type[BaseModel]) -> "GroqStructured":
        return GroqStructured(self, schema)


class GroqStructured:
    def __init__(self, parent: GroqChat, schema: Type[BaseModel]):
        self._parent = parent
        self._schema = schema

    def invoke(self, messages: list[BaseMessage]) -> BaseModel:
        schema_json = self._schema.model_json_schema()
        instruction = SystemMessage(content=(
            "Respond ONLY with a JSON object matching this JSON schema. "
            "No prose, no markdown fences.\n\n"
            f"Schema: {json.dumps(schema_json)}"
        ))
        groq_msgs = _to_groq_messages([instruction, *messages])
        resp = self._parent._client.chat.completions.create(
            model=self._parent._model,
            messages=groq_msgs,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            stripped = raw.strip().lstrip("`").rstrip("`")
            if stripped.lower().startswith("json"):
                stripped = stripped[4:].strip()
            data = json.loads(stripped)
        return self._schema.model_validate(data)


@lru_cache(maxsize=1)
def get_llm() -> GroqChat:
    return GroqChat(settings.groq_model, temperature=0.1)


@lru_cache(maxsize=1)
def get_fast_llm() -> GroqChat:
    return GroqChat(settings.groq_model_fast, temperature=0.0)
