"""Subscription management and referral system handlers."""

import logging
import secrets
import string
from datetime import datetime, timedelta, timezone
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.services.billing import topup_balance

logger = logging.getLogger(__name__)
router = Router(name="subscriptions")

# ═══════════════════════════════════════
# SUBSCRIPTION PLANS
# ═══════════════════════════════════════

PLANS = {
    "pro": {
        "name": "⭐ Pro",
        "price_stars": 200,
        "monthly_neurons": 50_000,
        "description": "50 000 💎 нейронов ежемесячно\nПриоритетная поддержка",
        "duration_days": 30,
    },
    "premium": {
        "name": "👑 Premium",
        "price_stars": 500,
        "monthly_neurons": 150_000,
        "description": "150 000 💎 нейронов ежемесячно\nВсе модели без ограничений\nПриоритетная поддержка",
        "duration_days": 30,
    },
    "ultimate": {
        "name": "💎 Ultimate",
        "price_stars": 1000,
        "monthly_neurons": 400_000,
        "description": "400 000 💎 нейронов ежемесячно\nВсе модели + ранний доступ\nПерсональная поддержка",
        "duration_days": 30,
    },
}

# ═══════════════════════════════════════
# REFERRAL SYSTEM
# ═══════════════════════════════════════

REFERRAL_BONUS_NEW_USER = 500.0       # Neurons for new user
REFERRAL_BONUS_REFERRER = 1000.0      # Neurons for referrer
REFERRAL_PERCENT_TOPUP = 5.0          # % of referral's top-ups goes to referrer


def _generate_referral_code() -> str:
    """Generate a short unique referral code."""
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(8))


# ─── Subscription Menu ───────────────────────────

@router.callback_query(F.data == "subscription")
async def subscription_menu(callback: CallbackQuery, db_user: User, session: AsyncSession):
    """Show subscription plans."""
    # Check current subscription
    result = await session.execute(
        select(Subscription)
        .where(
            Subscription.user_id == db_user.id,
            Subscription.is_active == True,
            Subscription.expires_at > datetime.now(timezone.utc),
        )
        .order_by(Subscription.expires_at.desc())
        .limit(1)
    )
    active_sub = result.scalar_one_or_none()

    if active_sub:
        days_left = (active_sub.expires_at - datetime.now(timezone.utc)).days
        current_plan = PLANS.get(active_sub.plan, {})
        current_text = (
            f"📦 <b>Текущая подписка:</b> {current_plan.get('name', active_sub.plan)}\n"
            f"⏳ Осталось: <b>{days_left}</b> дней\n\n"
        )
    else:
        current_text = "📦 <b>Текущая подписка:</b> Free\n\n"

    buttons = []
    for key, plan in PLANS.items():
        is_current = active_sub and active_sub.plan == key
        label = f"{plan['name']} — {plan['price_stars']}⭐/мес"
        if is_current:
            label += " ✓"
        buttons.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"sub_info:{key}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        f"⭐ <b>Подписки</b>\n\n"
        f"{current_text}"
        f"Выбери план для подробностей:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sub_info:"))
async def subscription_info(callback: CallbackQuery):
    """Show detailed info about a subscription plan."""
    plan_key = callback.data.split(":")[1]
    plan = PLANS.get(plan_key)
    if not plan:
        await callback.answer("❌ План не найден", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"💳 Купить за {plan['price_stars']}⭐",
            callback_data=f"buy_sub:{plan_key}",
        )],
        [InlineKeyboardButton(text="🔙 К планам", callback_data="subscription")],
    ])

    await callback.message.edit_text(
        f"{plan['name']}\n\n"
        f"💰 Цена: <b>{plan['price_stars']}</b> ⭐ Stars / месяц\n\n"
        f"📋 Включено:\n{plan['description']}\n\n"
        f"Нейроны начисляются сразу при покупке.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("buy_sub:"))
async def buy_subscription(callback: CallbackQuery, db_user: User, session: AsyncSession):
    """Process subscription purchase via Telegram Stars invoice."""
    from aiogram.types import LabeledPrice

    plan_key = callback.data.split(":")[1]
    plan = PLANS.get(plan_key)
    if not plan:
        await callback.answer("❌ План не найден", show_alert=True)
        return

    await callback.message.answer_invoice(
        title=f"Подписка {plan['name']}",
        description=f"{plan['description']}\n\n{plan['monthly_neurons']} нейронов на 30 дней",
        payload=f"sub_{plan_key}_{plan['monthly_neurons']}",
        currency="XTR",
        prices=[LabeledPrice(label=plan["name"], amount=plan["price_stars"])],
    )
    await callback.answer()


# ─── Referral System ─────────────────────────────

@router.callback_query(F.data == "referral")
async def referral_menu(callback: CallbackQuery, db_user: User, session: AsyncSession):
    """Show referral system info and user's referral link."""
    # Generate referral code if doesn't exist
    if not db_user.referral_code:
        db_user.referral_code = _generate_referral_code()
        await session.commit()

    # Count referrals
    referral_count = await session.scalar(
        select(func.count(User.id))
        .where(User.referred_by_id == db_user.telegram_id)
    ) or 0

    # Total referral earnings
    referral_earnings = await session.scalar(
        select(func.sum(Transaction.amount))
        .where(
            Transaction.user_id == db_user.id,
            Transaction.category == "referral_bonus",
        )
    ) or 0

    bot_info = await callback.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{db_user.referral_code}"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📤 Поделиться ссылкой",
            switch_inline_query=f"Попробуй AI-бота! 🤖 {ref_link}",
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")],
    ])

    await callback.message.edit_text(
        f"👥 <b>Реферальная программа</b>\n\n"
        f"🔗 Твоя ссылка:\n<code>{ref_link}</code>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"├ Приглашено: <b>{referral_count}</b> друзей\n"
        f"└ Заработано: <b>{referral_earnings:.0f}</b> 💎\n\n"
        f"🎁 <b>Бонусы:</b>\n"
        f"├ Новый юзер получит: <b>{REFERRAL_BONUS_NEW_USER:.0f}</b> 💎\n"
        f"├ Ты получишь: <b>{REFERRAL_BONUS_REFERRER:.0f}</b> 💎\n"
        f"└ + <b>{REFERRAL_PERCENT_TOPUP}%</b> от пополнений друга",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


async def process_referral(session: AsyncSession, new_user: User, referral_code: str, bot) -> None:
    """Process a referral when a new user joins with a referral code."""
    # Find referrer
    result = await session.execute(
        select(User).where(User.referral_code == referral_code)
    )
    referrer = result.scalar_one_or_none()

    if not referrer or referrer.id == new_user.id:
        return

    # Mark who referred this user
    new_user.referred_by_id = referrer.telegram_id
    await session.commit()

    # Bonus to new user
    await topup_balance(
        session=session,
        user=new_user,
        neurons_amount=REFERRAL_BONUS_NEW_USER,
        category="referral_bonus",
        description=f"Welcome bonus (ref by {referrer.telegram_id})",
    )

    # Bonus to referrer
    await topup_balance(
        session=session,
        user=referrer,
        neurons_amount=REFERRAL_BONUS_REFERRER,
        category="referral_bonus",
        description=f"Referral bonus for inviting {new_user.telegram_id}",
    )

    # Notify referrer
    try:
        await bot.send_message(
            referrer.telegram_id,
            f"🎉 Твой друг присоединился по реферальной ссылке!\n"
            f"💎 +{REFERRAL_BONUS_REFERRER:.0f} нейронов начислено!",
        )
    except Exception:
        pass

    logger.info(f"Referral: {new_user.telegram_id} referred by {referrer.telegram_id}")
