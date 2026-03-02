"""Simple throttling middleware to prevent spam."""

from typing import Callable, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
import time


class ThrottlingMiddleware(BaseMiddleware):
    """
    Limits the rate of messages per user.
    Default: 1 message per second.
    """

    def __init__(self, rate_limit: float = 1.0):
        self.rate_limit = rate_limit
        self._user_timestamps: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        event_user = data.get("event_from_user")
        if event_user is None:
            return await handler(event, data)

        user_id = event_user.id
        current_time = time.monotonic()
        last_time = self._user_timestamps.get(user_id, 0)

        if current_time - last_time < self.rate_limit:
            # Throttled — silently skip
            return

        self._user_timestamps[user_id] = current_time
        return await handler(event, data)
