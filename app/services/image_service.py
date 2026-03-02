"""
Image generation service via OpenAI DALL-E through LiteLLM.
"""

import logging
import aiohttp
from app.core.config import settings

logger = logging.getLogger(__name__)

# Image generation models and pricing
IMAGE_MODELS = {
    "dall-e-3": {
        "name": "🎨 DALL·E 3",
        "description": "Лучшее качество от OpenAI",
        "sizes": ["1024x1024", "1024x1792", "1792x1024"],
        "price_per_image": 0.04,  # USD for 1024x1024 standard
    },
    "dall-e-2": {
        "name": "🖼 DALL·E 2",
        "description": "Быстрая и дешёвая генерация",
        "sizes": ["256x256", "512x512", "1024x1024"],
        "price_per_image": 0.02,
    },
}

# Pricing by size for DALL-E 3
DALLE3_PRICING = {
    "1024x1024": 0.04,
    "1024x1792": 0.08,
    "1792x1024": 0.08,
}


async def generate_image(
    prompt: str,
    model: str = "dall-e-3",
    size: str = "1024x1024",
    quality: str = "standard",
) -> dict:
    """
    Generate an image using OpenAI's DALL-E via direct API call.

    Returns:
        {"url": str, "revised_prompt": str, "cost_usd": float}
    """
    import litellm

    try:
        response = await litellm.aimage_generation(
            model=model,
            prompt=prompt,
            size=size,
            quality=quality,
            n=1,
            api_key=settings.openai_api_key,
        )

        image_url = response.data[0].url
        revised_prompt = getattr(response.data[0], "revised_prompt", prompt)

        # Calculate cost
        if model == "dall-e-3":
            cost = DALLE3_PRICING.get(size, 0.04)
            if quality == "hd":
                cost *= 2
        else:
            cost = IMAGE_MODELS.get(model, {}).get("price_per_image", 0.02)

        return {
            "url": image_url,
            "revised_prompt": revised_prompt,
            "cost_usd": cost,
        }

    except Exception as e:
        logger.error(f"Image generation error: {e}")
        raise


async def download_image(url: str) -> bytes:
    """Download image from URL and return bytes."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.read()
            raise Exception(f"Failed to download image: HTTP {resp.status}")
