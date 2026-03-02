"""
Billing service — converts real USD cost to virtual currency and manages user balance.
"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)

# === CONFIGURATION ===
# How many virtual currency units (e.g. "neurons") equal 1 USD
# Example: if RATE = 50000, then $0.01 = 500 neurons
NEURONS_PER_USD: float = 50_000.0

# Your margin percentage on top of the real cost
MARGIN_PERCENT: float = 30.0  # 30% margin


def usd_to_neurons(cost_usd: float) -> float:
    """Convert USD cost to virtual currency with margin included."""
    cost_with_margin = cost_usd * (1 + MARGIN_PERCENT / 100)
    return round(cost_with_margin * NEURONS_PER_USD, 2)


def neurons_to_usd(neurons: float) -> float:
    """Convert virtual currency back to USD (without margin, for admin stats)."""
    return round(neurons / NEURONS_PER_USD, 6)


async def charge_user(
    session: AsyncSession,
    user: User,
    cost_usd: float,
    category: str,
    model_used: str,
    tokens_input: int = 0,
    tokens_output: int = 0,
    description: str | None = None,
) -> tuple[bool, float]:
    """
    Charge user for AI usage.

    Returns:
        (success, neurons_charged) — False if insufficient balance.
    """
    neurons_cost = usd_to_neurons(cost_usd)

    if user.balance < neurons_cost:
        return False, neurons_cost

    # Deduct from balance
    user.balance -= neurons_cost

    # Record transaction
    tx = Transaction(
        user_id=user.id,
        amount=-neurons_cost,
        real_cost_usd=cost_usd,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        category=category,
        model_used=model_used,
        description=description,
    )
    session.add(tx)
    await session.commit()

    logger.info(
        f"Charged user {user.telegram_id}: {neurons_cost:.0f} neurons "
        f"(${cost_usd:.6f}) for {model_used}"
    )

    return True, neurons_cost


async def topup_balance(
    session: AsyncSession,
    user: User,
    neurons_amount: float,
    category: str = "topup",
    description: str | None = None,
) -> float:
    """
    Add virtual currency to user's balance.

    Returns:
        New balance.
    """
    user.balance += neurons_amount

    tx = Transaction(
        user_id=user.id,
        amount=neurons_amount,
        real_cost_usd=0.0,
        category=category,
        description=description,
    )
    session.add(tx)
    await session.commit()

    logger.info(f"Top-up user {user.telegram_id}: +{neurons_amount:.0f} neurons")

    return user.balance
