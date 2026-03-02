"""
AI Service — unified interface to LLMs through LiteLLM.
Fetches model pricing dynamically from OpenRouter API.
"""

import logging
import asyncio
from dataclasses import dataclass
import aiohttp
import litellm
from app.core.config import settings

logger = logging.getLogger(__name__)

# Configure litellm
litellm.set_verbose = False

# ═══════════════════════════════════════
# PRICING CACHE (fetched from OpenRouter)
# ═══════════════════════════════════════

# Cache: model_id -> {"prompt": price_per_token, "completion": price_per_token}
_pricing_cache: dict[str, dict[str, float]] = {}
_cache_lock = asyncio.Lock()
_cache_loaded = False

# Markup multiplier (user pays 3x the actual cost)
MARKUP_MULTIPLIER = 3.0


async def fetch_openrouter_models() -> dict[str, dict]:
    """
    Fetch all models and their pricing from OpenRouter API.
    Returns dict: {model_id: {"name": str, "prompt": float, "completion": float, ...}}
    """
    global _pricing_cache, _cache_loaded

    url = "https://openrouter.ai/api/v1/models"
    headers = {}
    if settings.openrouter_api_key:
        headers["Authorization"] = f"Bearer {settings.openrouter_api_key}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    logger.error(f"OpenRouter models API returned {resp.status}")
                    return {}

                data = await resp.json()
                models = data.get("data", [])

                result = {}
                for model in models:
                    model_id = model.get("id", "")
                    pricing = model.get("pricing", {})

                    # pricing.prompt and pricing.completion are strings (price per token)
                    prompt_price = float(pricing.get("prompt", "0") or "0")
                    completion_price = float(pricing.get("completion", "0") or "0")

                    result[model_id] = {
                        "name": model.get("name", model_id),
                        "description": model.get("description", "")[:200],
                        "prompt": prompt_price,
                        "completion": completion_price,
                        "context_length": model.get("context_length", 4096),
                        "modality": model.get("architecture", {}).get("modality", "text->text"),
                    }

                async with _cache_lock:
                    _pricing_cache = result
                    _cache_loaded = True

                logger.info(f"Loaded pricing for {len(result)} models from OpenRouter")
                return result

    except Exception as e:
        logger.error(f"Failed to fetch OpenRouter models: {e}")
        return {}


def get_model_pricing(model_id: str) -> dict[str, float] | None:
    """Get cached pricing for a model. Returns None if not in cache."""
    # model_id format in our code: "openrouter/google/gemini-2.0-flash-001"
    # OpenRouter API format: "google/gemini-2.0-flash-001"
    clean_id = model_id.replace("openrouter/", "")
    return _pricing_cache.get(clean_id)


# ═══════════════════════════════════════
# AVAILABLE MODELS (user-facing selection)
# ═══════════════════════════════════════

# These are the curated models shown to users
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
    Send messages to an LLM and return the response.
    Uses OpenRouter API via LiteLLM.
    """
    try:
        response = await litellm.acompletion(
            model=model_id,
            messages=messages,
            api_key=settings.openrouter_api_key,
            extra_headers={
                "HTTP-Referer": "https://t.me/prsta_ai_bot",
                "X-Title": "PRSTA AI Bot",
            },
            extra_body={
                "provider": {
                    "allow_fallbacks": True,
                    "require_parameters": True,
                },
            },
        )

        content = response.choices[0].message.content or ""
        usage = response.usage

        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0
        cost_usd = estimate_cost(model_id, tokens_in, tokens_out)

        return AIResponse(
            content=content,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
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
            extra_body={
                "provider": {
                    "allow_fallbacks": True,
                    "require_parameters": True,
                },
            },
        )

        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    except Exception as e:
        logger.error(f"AI stream error: {e}")
        raise


def estimate_cost(model_id: str, tokens_input: int, tokens_output: int) -> float:
    """
    Estimate cost in USD using dynamic pricing from OpenRouter.
    Falls back to hardcoded prices if API data not available.
    """
    # 1. Try dynamic pricing from OpenRouter API
    pricing = get_model_pricing(model_id)
    if pricing and (pricing["prompt"] > 0 or pricing["completion"] > 0):
        cost_input = tokens_input * pricing["prompt"]
        cost_output = tokens_output * pricing["completion"]
        return cost_input + cost_output

    # 2. Fallback: hardcoded pricing (per 1M tokens, USD)
    FALLBACK_PRICING = {
        "openrouter/openai/gpt-4o": {"input": 2.50, "output": 10.00},
        "openrouter/openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "openrouter/anthropic/claude-3.5-sonnet": {"input": 3.00, "output": 15.00},
        "openrouter/google/gemini-2.0-flash-001": {"input": 0.10, "output": 0.40},
        "openrouter/meta-llama/llama-3.1-70b-instruct": {"input": 0.52, "output": 0.75},
        "openrouter/deepseek/deepseek-chat": {"input": 0.14, "output": 0.28},
    }

    fallback = FALLBACK_PRICING.get(model_id)
    if fallback:
        cost_input = (tokens_input / 1_000_000) * fallback["input"]
        cost_output = (tokens_output / 1_000_000) * fallback["output"]
        return cost_input + cost_output

    # 3. Last resort
    logger.warning(f"No pricing for {model_id}, using generic fallback")
    cost_input = (tokens_input / 1_000_000) * 0.50
    cost_output = (tokens_output / 1_000_000) * 1.50
    return max(cost_input + cost_output, 0.000005)
