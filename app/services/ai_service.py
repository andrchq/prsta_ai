"""
AI Service — unified interface to LLMs through LiteLLM.
All models and pricing come from OpenRouter API + database.
Zero hardcoded models or prices.
"""

import logging
import asyncio
from dataclasses import dataclass
import aiohttp
import litellm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings

logger = logging.getLogger(__name__)
litellm.set_verbose = False

# ═══════════════════════════════════════════
# PRICING CACHE (from OpenRouter API)
# ═══════════════════════════════════════════

# model_id (e.g. "google/gemini-2.0-flash-001") -> pricing dict
_pricing_cache: dict[str, dict] = {}


async def fetch_openrouter_models() -> dict[str, dict]:
    """
    Fetch ALL models from OpenRouter API and cache pricing.
    Returns dict: {model_id: {name, description, prompt, completion, ...}}
    """
    global _pricing_cache

    url = "https://openrouter.ai/api/v1/models"
    headers = {}
    if settings.openrouter_api_key:
        headers["Authorization"] = f"Bearer {settings.openrouter_api_key}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    logger.error(f"OpenRouter API returned {resp.status}")
                    return {}

                data = await resp.json()
                models = data.get("data", [])

                result = {}
                for model in models:
                    model_id = model.get("id", "")
                    if not model_id:
                        continue

                    pricing = model.get("pricing", {})
                    prompt_price = float(pricing.get("prompt", "0") or "0")
                    completion_price = float(pricing.get("completion", "0") or "0")

                    arch = model.get("architecture", {})
                    input_mods = arch.get("input_modalities", ["text"])
                    output_mods = arch.get("output_modalities", ["text"])

                    result[model_id] = {
                        "name": model.get("name", model_id),
                        "description": (model.get("description", "") or "")[:300],
                        "prompt": prompt_price,
                        "completion": completion_price,
                        "context_length": model.get("context_length") or 4096,
                        "input_modalities": ",".join(input_mods) if input_mods else "text",
                        "output_modalities": ",".join(output_mods) if output_mods else "text",
                    }

                _pricing_cache = result
                logger.info(f"Cached pricing for {len(result)} OpenRouter models")
                return result

    except Exception as e:
        logger.error(f"Failed to fetch OpenRouter models: {e}")
        return {}


async def sync_models_to_db(db_session: AsyncSession):
    """
    Sync OpenRouter models to DB. Updates pricing for existing models,
    inserts new ones (disabled by default).
    """
    from app.models.ai_model import AIModel

    if not _pricing_cache:
        logger.warning("No pricing cache to sync")
        return 0

    new_count = 0
    updated_count = 0

    for model_id, data in _pricing_cache.items():
        result = await db_session.execute(
            select(AIModel).where(AIModel.model_id == model_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update pricing and metadata
            existing.price_prompt = data["prompt"]
            existing.price_completion = data["completion"]
            existing.context_length = data["context_length"]
            existing.input_modalities = data["input_modalities"]
            existing.output_modalities = data["output_modalities"]
            existing.name = data["name"]
            updated_count += 1
        else:
            # New model — disabled by default
            new_model = AIModel(
                model_id=model_id,
                name=data["name"],
                description=data["description"],
                price_prompt=data["prompt"],
                price_completion=data["completion"],
                context_length=data["context_length"],
                input_modalities=data["input_modalities"],
                output_modalities=data["output_modalities"],
                is_enabled=False,
            )
            db_session.add(new_model)
            new_count += 1

    await db_session.commit()
    logger.info(f"Models sync: {new_count} new, {updated_count} updated")
    return new_count


def get_model_pricing(model_id: str) -> dict[str, float] | None:
    """Get cached pricing for a model. model_id can be openrouter/ prefixed or not."""
    clean_id = model_id.replace("openrouter/", "")
    return _pricing_cache.get(clean_id)


async def get_enabled_models(db_session: AsyncSession) -> list:
    """Get all enabled models from DB, sorted by sort_order."""
    from app.models.ai_model import AIModel
    result = await db_session.execute(
        select(AIModel)
        .where(AIModel.is_enabled == True)
        .order_by(AIModel.sort_order, AIModel.name)
    )
    return list(result.scalars().all())


# ═══════════════════════════════════════════
# AI COMPLETION
# ═══════════════════════════════════════════

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
    """Send messages to an LLM and return the response."""
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
    """Stream messages from an LLM. Yields partial content chunks."""
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
    Estimate cost in USD using ONLY dynamic pricing from OpenRouter.
    No hardcoded prices — if model not in cache, uses generic rate.
    """
    pricing = get_model_pricing(model_id)
    if pricing and (pricing["prompt"] > 0 or pricing["completion"] > 0):
        cost_input = tokens_input * pricing["prompt"]
        cost_output = tokens_output * pricing["completion"]
        return cost_input + cost_output

    # Generic fallback if model pricing not cached (should be rare)
    logger.warning(f"No OpenRouter pricing for {model_id}, using $0.50/$1.50 per 1M")
    cost_input = (tokens_input / 1_000_000) * 0.50
    cost_output = (tokens_output / 1_000_000) * 1.50
    return max(cost_input + cost_output, 0.000005)
