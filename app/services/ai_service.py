"""
AI Service — unified interface to LLMs through LiteLLM.
Supports direct providers (OpenAI, Anthropic) and aggregators (OpenRouter).
"""

import logging
from dataclasses import dataclass
import litellm
from app.core.config import settings

logger = logging.getLogger(__name__)

# Configure litellm to use OpenRouter as default
litellm.set_verbose = False

# Map of user-friendly model names to litellm model identifiers
# Format for OpenRouter: "openrouter/<provider>/<model>"
AVAILABLE_MODELS: dict[str, dict] = {
    "gpt-4o": {
        "id": "openrouter/openai/gpt-4o",
        "name": "GPT-4o",
        "description": "Мультимодальная модель от OpenAI",
        "category": "text",
        "emoji": "🟢",
    },
    "gpt-4o-mini": {
        "id": "openrouter/openai/gpt-4o-mini",
        "name": "GPT-4o Mini",
        "description": "Быстрая и дешевая модель от OpenAI",
        "category": "text",
        "emoji": "🟢",
    },
    "claude-3.5-sonnet": {
        "id": "openrouter/anthropic/claude-3.5-sonnet",
        "name": "Claude 3.5 Sonnet",
        "description": "Лучшая модель Anthropic для кода и анализа",
        "category": "text",
        "emoji": "🟣",
    },
    "gemini-2.0-flash": {
        "id": "openrouter/google/gemini-2.0-flash-001",
        "name": "Gemini 2.0 Flash",
        "description": "Быстрая модель от Google",
        "category": "text",
        "emoji": "🔵",
    },
    "llama-3.1-70b": {
        "id": "openrouter/meta-llama/llama-3.1-70b-instruct",
        "name": "Llama 3.1 70B",
        "description": "Open-source модель от Meta",
        "category": "text",
        "emoji": "🟠",
    },
    "deepseek-v3": {
        "id": "openrouter/deepseek/deepseek-chat",
        "name": "DeepSeek V3",
        "description": "Мощная китайская open-source модель",
        "category": "text",
        "emoji": "⚫",
    },
}


@dataclass
class AIResponse:
    """Result of an AI completion call."""
    content: str
    tokens_input: int
    tokens_output: int
    cost_usd: float
    model_used: str


async def chat_completion(
    messages: list[dict[str, str]],
    model_id: str = "openrouter/google/gemini-2.0-flash-001",
) -> AIResponse:
    """
    Send messages to an LLM via LiteLLM and return a structured response.

    Args:
        messages: List of {"role": ..., "content": ...} dicts.
        model_id: LiteLLM-compatible model identifier.

    Returns:
        AIResponse with content, token counts, and USD cost.
    """
    try:
        response = await litellm.acompletion(
            model=model_id,
            messages=messages,
            api_key=settings.openrouter_api_key,
            # OpenRouter-specific headers
            extra_headers={
                "HTTP-Referer": "https://t.me/prsta_ai_bot",
                "X-Title": "PRSTA AI Bot",
            },
        )

        content = response.choices[0].message.content or ""
        usage = response.usage

        # LiteLLM auto-calculates cost when available
        cost_usd = 0.0
        try:
            cost_usd = litellm.completion_cost(completion_response=response)
        except Exception:
            logger.warning(f"Could not calculate cost for model {model_id}")

        return AIResponse(
            content=content,
            tokens_input=usage.prompt_tokens if usage else 0,
            tokens_output=usage.completion_tokens if usage else 0,
            cost_usd=cost_usd,
            model_used=model_id,
        )

    except Exception as e:
        logger.error(f"AI completion error: {e}")
        raise


async def stream_chat_completion(
    messages: list[dict[str, str]],
    model_id: str = "openrouter/google/gemini-2.0-flash-001",
):
    """
    Stream messages from an LLM via LiteLLM.
    Yields partial content chunks as they arrive.

    After iteration is complete, call get_stream_cost() with the full response.
    """
    try:
        response = await litellm.acompletion(
            model=model_id,
            messages=messages,
            api_key=settings.openrouter_api_key,
            stream=True,
            extra_headers={
                "HTTP-Referer": "https://t.me/prsta_ai_bot",
                "X-Title": "PRSTA AI Bot",
            },
        )

        full_content = ""
        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                full_content += delta.content
                yield delta.content

    except Exception as e:
        logger.error(f"AI stream error: {e}")
        raise


def estimate_cost(model_id: str, tokens_input: int, tokens_output: int) -> float:
    """
    Estimate cost in USD for a given model and token counts.
    Uses litellm first, falls back to manual pricing table.
    """
    # Try litellm built-in cost calculation first
    try:
        cost = litellm.completion_cost(
            model=model_id,
            prompt="",
            completion="",
            prompt_tokens=tokens_input,
            completion_tokens=tokens_output,
        )
        if cost and cost > 0:
            return cost
    except Exception:
        pass

    # Fallback: manual pricing table (per 1M tokens, USD)
    # Prices from OpenRouter as of 2025
    PRICING = {
        "openrouter/openai/gpt-4o": {"input": 2.50, "output": 10.00},
        "openrouter/openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "openrouter/anthropic/claude-3.5-sonnet": {"input": 3.00, "output": 15.00},
        "openrouter/google/gemini-2.0-flash-001": {"input": 0.10, "output": 0.40},
        "openrouter/meta-llama/llama-3.1-70b-instruct": {"input": 0.52, "output": 0.75},
        "openrouter/deepseek/deepseek-chat": {"input": 0.14, "output": 0.28},
    }

    pricing = PRICING.get(model_id)
    if pricing:
        cost_input = (tokens_input / 1_000_000) * pricing["input"]
        cost_output = (tokens_output / 1_000_000) * pricing["output"]
        return cost_input + cost_output

    # Last resort: generic minimal pricing
    logger.warning(f"No pricing for {model_id}, using fallback")
    cost_input = (tokens_input / 1_000_000) * 0.50
    cost_output = (tokens_output / 1_000_000) * 1.50
    return max(cost_input + cost_output, 0.000005)  # minimum charge


