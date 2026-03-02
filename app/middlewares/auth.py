"""Middleware that auto-registers users on first interaction and injects User into handler data."""

from typing import Callable, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from sqlalchemy import select
from app.database.session import AsyncSessionLocal
from app.models.user import User


class UserAuthMiddleware(BaseMiddleware):
    """
    Checks if a user exists in the database. If not, creates a new record.
    Injects 'db_user' and 'session' into handler data for all downstream handlers.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Extract telegram user from the event
        event_user = data.get("event_from_user")
        if event_user is None:
            return await handler(event, data)

        async with AsyncSessionLocal() as session:
            # Try to find existing user
            result = await session.execute(
                select(User).where(User.telegram_id == event_user.id)
            )
            db_user = result.scalar_one_or_none()

            if db_user is None:
                # Auto-register new user
                db_user = User(
                    telegram_id=event_user.id,
                    username=event_user.username,
                    first_name=event_user.first_name,
                    last_name=event_user.last_name,
                    language_code=event_user.language_code,
                    balance=0.0,
                )
                session.add(db_user)
                await session.commit()
                await session.refresh(db_user)

            # Check if user is blocked
            if db_user.is_blocked:
                return  # Silently ignore blocked users

            # Inject into handler data
            data["db_user"] = db_user
            data["session"] = session

            return await handler(event, data)
