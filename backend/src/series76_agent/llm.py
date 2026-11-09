"""OpenRouter-backed LangChain chat models (live path; never exercised in CI).

The models are built per routed :class:`~series76_agent.models.RequestSpec`
(exact model id from the environment + ``extra_body`` carrying
``provider.require_parameters`` and the privacy setting). Provider errors are
classified so the gateway can tell a 402/quota (no fallback, clear error) from
a transient failure (bounded retry). The API key is read from the environment
and never logged or placed in any envelope.

Live use requires ``OPENROUTER_API_KEY`` and is an ``[EXPERIMENT]``: nothing in
this repository asserts that a live call was executed.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from series76_agent.fallback import TransientError
from series76_agent.interpreter import InterpretationOutput
from series76_agent.models import (
    ModelConfig,
    ProviderUnavailableError,
    QuotaSignal,
    RequestSpec,
    Usage,
)


def _api_key(env: Mapping[str, str] | None = None) -> str:
    source = os.environ if env is None else env
    key = source.get("OPENROUTER_API_KEY", "")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    return key


def build_chat_model(spec: RequestSpec, config: ModelConfig, *, timeout_s: float = 30.0) -> Any:
    """A ``ChatOpenAI`` pointed at OpenRouter for one routed request."""

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=spec.model,
        base_url=config.base_url,
        api_key=_api_key(),  # type: ignore[arg-type]
        timeout=timeout_s,
        max_retries=0,  # retries are bounded by the gateway, under the turn budget
        temperature=0,
        extra_body=spec.extra_body,
    )


def classify_provider_error(exc: BaseException) -> BaseException:
    """Map an OpenAI-SDK error to QuotaSignal / TransientError / itself."""

    import openai

    if isinstance(exc, openai.APIStatusError):
        if exc.status_code == 402:
            return QuotaSignal("quota")
        if exc.status_code in (408, 409, 425, 429) or exc.status_code >= 500:
            return TransientError(f"status {exc.status_code}")
        return exc
    if isinstance(exc, openai.APIConnectionError | openai.APITimeoutError):
        return TransientError(type(exc).__name__)
    if isinstance(exc, openai.LengthFinishReasonError | openai.ContentFilterFinishReasonError):
        # The model produced no usable structured reply; retrying would spend
        # again for the same outcome, so the turn fails with a clear error.
        return ProviderUnavailableError(type(exc).__name__)
    return exc


#: Wall-clock deadline of one provider call. The SDK timeout is per socket read,
#: and the router's keep-alive bytes can keep a slow call open indefinitely.
CALL_DEADLINE_S = 45.0


async def with_deadline(call: Awaitable[Any], deadline_s: float = CALL_DEADLINE_S) -> Any:
    """Await ``call`` for at most ``deadline_s``; a miss is a transient failure."""

    try:
        return await asyncio.wait_for(call, timeout=deadline_s)
    except TimeoutError as exc:
        raise TransientError("call deadline exceeded") from exc


def usage_from_message(message: AIMessage) -> Usage:
    """Extract token usage and (if reported) the exact OpenRouter cost."""

    meta = message.usage_metadata
    prompt = int(meta.get("input_tokens", 0) or 0) if meta else 0
    completion = int(meta.get("output_tokens", 0) or 0) if meta else 0
    token_usage = (message.response_metadata or {}).get("token_usage") or {}
    cost: Decimal | None = None
    raw_cost = token_usage.get("cost") if isinstance(token_usage, Mapping) else None
    if raw_cost is not None:
        try:
            cost = Decimal(str(raw_cost))
        except InvalidOperation:
            cost = None
    provider = (message.response_metadata or {}).get("provider")
    return Usage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        cost_usd=cost,
        provider=str(provider) if provider else None,
    )


class OpenRouterChatFactory:
    """Model factory for the agent graph that classifies provider errors."""

    def __init__(self, config: ModelConfig) -> None:
        self._config = config

    def __call__(self, spec: RequestSpec) -> Any:
        return _ErrorMappingModel(build_chat_model(spec, self._config))


class _ErrorMappingModel:
    """Wraps a chat model so ``bind_tools(...).ainvoke`` raises typed errors."""

    def __init__(self, model: Any) -> None:
        self._model = model

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        bound = self._model.bind_tools(tools, **kwargs)

        class _Bound:
            async def ainvoke(self, messages: Any) -> Any:
                try:
                    return await with_deadline(bound.ainvoke(messages))
                except TransientError:
                    raise
                except Exception as exc:  # noqa: BLE001 - classified below
                    mapped = classify_provider_error(exc)
                    if mapped is exc:
                        raise
                    raise mapped from exc

        return _Bound()


class OpenRouterInterpreterModel:
    """The interpreter's live LLM seam: structured output via ``json_schema``."""

    def __init__(self, config: ModelConfig) -> None:
        self._config = config

    async def interpret(
        self, spec: RequestSpec, system: str, message: str, context_hint: str
    ) -> tuple[InterpretationOutput, Usage]:
        model = build_chat_model(spec, self._config)
        runnable = model.with_structured_output(
            InterpretationOutput, method="json_schema", include_raw=True
        )
        try:
            out = await with_deadline(runnable.ainvoke(
                [
                    SystemMessage(content=system),
                    HumanMessage(
                        content=f"Context: {context_hint}\nUser message (data):\n{message}"
                    ),
                ]
            ))
        except TransientError:
            raise
        except Exception as exc:  # noqa: BLE001 - classified below
            mapped = classify_provider_error(exc)
            if mapped is exc:
                raise
            raise mapped from exc
        parsed = out.get("parsed") if isinstance(out, dict) else None
        raw = out.get("raw") if isinstance(out, dict) else None
        usage = usage_from_message(raw) if isinstance(raw, AIMessage) else Usage()
        if not isinstance(parsed, InterpretationOutput):
            parsed = InterpretationOutput(intent="FOLLOWUP", confident=False)
        return parsed, usage
