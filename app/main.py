"""
PRSTA AI Bot — Main entry point.
Combines all routers, middlewares, and starts polling.
"""

import asyncio
import logging
import datetime
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.core.config import settings
from app.database.base import Base
from app.database.session import engine

# Middlewares
from app.middlewares.auth import UserAuthMiddleware
from app.middlewares.throttling import ThrottlingMiddleware

# Routers
from app.handlers.base import router as base_router
from app.handlers.chat import router as chat_router
from app.handlers.models import router as models_router
from app.handlers.admin import router as admin_router
from app.handlers.payments import router as payments_router
from app.handlers.subscriptions import router as subscriptions_router
from app.handlers.images import router as images_router
from app.handlers.ai_chat import router as ai_chat_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Pricing refresh interval in minutes (on round numbers: :00, :05, :10, ...)
PRICING_REFRESH_MINUTES = 5


async def _pricing_refresh_loop():
    """
    Background task: refresh OpenRouter model pricing every 5 minutes
    on round time intervals (e.g., 12:00, 12:05, 12:10, ...).
    """
    from app.services.ai_service import fetch_openrouter_models

    while True:
        try:
            # Calculate seconds until next round 5-minute mark
            now = datetime.datetime.now()
            minute = now.minute
            next_minute = ((minute // PRICING_REFRESH_MINUTES) + 1) * PRICING_REFRESH_MINUTES
            if next_minute >= 60:
                next_time = now.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
            else:
                next_time = now.replace(minute=next_minute, second=0, microsecond=0)

            wait_seconds = (next_time - now).total_seconds()
            logger.debug(f"Next pricing refresh at {next_time.strftime('%H:%M:%S')} (in {wait_seconds:.0f}s)")
            await asyncio.sleep(wait_seconds)

            # Refresh pricing
            data = await fetch_openrouter_models()
            if data:
                logger.info(f"🔄 Pricing refreshed: {len(data)} models")
            else:
                logger.warning("Pricing refresh failed, keeping cached data")

        except asyncio.CancelledError:
            logger.info("Pricing refresh loop cancelled")
            break
        except Exception as e:
            logger.error(f"Pricing refresh error: {e}")
            await asyncio.sleep(60)  # retry in 1 minute on error


async def on_startup(bot: Bot):
    """Actions to perform on bot startup."""
    async with engine.begin() as conn:
        # Create new tables
        await conn.run_sync(Base.metadata.create_all)

        # Auto-add missing columns to existing tables
        migrations = [
            "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS topic_thread_id INTEGER",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_code VARCHAR(20) UNIQUE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by_id BIGINT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN DEFAULT FALSE",
            "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS real_cost_usd FLOAT DEFAULT 0",
            "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS tokens_input INTEGER DEFAULT 0",
            "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS tokens_output INTEGER DEFAULT 0",
        ]
        for sql in migrations:
            try:
                await conn.execute(__import__('sqlalchemy').text(sql))
            except Exception as e:
                logger.debug(f"Migration skip: {e}")

    logger.info("Database tables created/verified")

    # Fetch model pricing from OpenRouter API (initial load)
    from app.services.ai_service import fetch_openrouter_models
    pricing_data = await fetch_openrouter_models()
    if pricing_data:
        logger.info(f"Loaded pricing for {len(pricing_data)} models")
    else:
        logger.warning("Could not load OpenRouter pricing, using hardcoded fallback")

    # Start background pricing refresh task
    asyncio.create_task(_pricing_refresh_loop())
    logger.info(f"⏰ Pricing auto-refresh every {PRICING_REFRESH_MINUTES}min started")

    bot_info = await bot.get_me()
    logger.info(f"Bot started: @{bot_info.username}")


async def main():
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Register startup hook
    dp.startup.register(on_startup)

    # Register middlewares (order matters!)
    dp.message.middleware(ThrottlingMiddleware(rate_limit=0.5))
    dp.message.middleware(UserAuthMiddleware())
    dp.callback_query.middleware(UserAuthMiddleware())
    dp.pre_checkout_query.middleware(UserAuthMiddleware())

    # Register routers (order matters — ai_chat LAST, as it catches all text)
    dp.include_router(base_router)
    dp.include_router(admin_router)
    dp.include_router(payments_router)
    dp.include_router(subscriptions_router)
    dp.include_router(images_router)
    dp.include_router(chat_router)
    dp.include_router(models_router)
    dp.include_router(ai_chat_router)  # Must be last: catches F.text

    logger.info("Starting bot polling...")

    try:
        await dp.start_polling(
            bot,
            allowed_updates=[
                "message",
                "callback_query",
                "pre_checkout_query",
                "message_reaction",
            ],
        )
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

