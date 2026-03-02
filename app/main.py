"""
PRSTA AI Bot — Main entry point.
Combines all routers, middlewares, and starts polling.
"""

import asyncio
import logging
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
from app.handlers.ai_chat import router as ai_chat_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    """Actions to perform on bot startup."""
    # Create all database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")

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

    # Register routers (order matters — ai_chat LAST, as it catches all text)
    dp.include_router(base_router)
    dp.include_router(admin_router)
    dp.include_router(payments_router)
    dp.include_router(subscriptions_router)
    dp.include_router(chat_router)
    dp.include_router(models_router)
    dp.include_router(ai_chat_router)  # Must be last: catches F.text

    logger.info("Starting bot polling...")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
