"""
Billing service — converts real USD cost to virtual currency and manages user balance.

Pricing strategy:
- Markup: x3 (user pays 3x the actual API cost)
- Minimum charge: 10 neurons per request
- Currency: 1 USD = 50,000 neurons
"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)

# === CONFIGURATION ===
# How many virtual currency units ("neurons") equal 1 USD
NEURONS_PER_USD: float = 50_000.0

# Markup multiplier (user pays 3x the real cost)
MARKUP_MULTIPLIER: float = 2.5

# Minimum charge per request in neurons
MIN_CHARGE_NEURONS: float = 10.0


def usd_to_neurons(cost_usd: float) -> float:
    """Convert USD cost to neurons with x3 markup, minimum 10 neurons."""
    cost_with_markup = cost_usd * MARKUP_MULTIPLIER
    neurons = round(cost_with_markup * NEURONS_PER_USD, 2)
    return max(neurons, MIN_CHARGE_NEURONS)


def neurons_to_usd(neurons: float) -> float:
    """Convert neurons back to USD (without markup, for admin stats)."""
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
        f"(${cost_usd:.6f} x{MARKUP_MULTIPLIER:.0f}) for {model_used}"
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
