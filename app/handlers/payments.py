"""Payment handler — top-up balance via Telegram Stars."""

import logging
from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery,
)
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.services.billing import topup_balance

logger = logging.getLogger(__name__)
router = Router(name="payments")

# ─── Price Tiers (Telegram Stars → Neurons) ──────
# Telegram Stars: 1 Star ≈ $0.02 USD
# We sell neurons at markup. Example tiers:
PAYMENT_TIERS = [
    {"stars": 50, "neurons": 5000, "label": "5 000 💎"},
    {"stars": 100, "neurons": 12000, "label": "12 000 💎 (+20%)"},
    {"stars": 250, "neurons": 35000, "label": "35 000 💎 (+40%)"},
    {"stars": 500, "neurons": 80000, "label": "80 000 💎 (+60%)"},
    {"stars": 1000, "neurons": 180000, "label": "180 000 💎 (+80%)"},
]


# ─── Top-up Menu ─────────────────────────────────

@router.callback_query(F.data == "topup")
async def topup_menu(callback: CallbackQuery, db_user: User):
    """Show top-up options."""
    buttons = []
    for tier in PAYMENT_TIERS:
        buttons.append([
            InlineKeyboardButton(
                text=f"⭐ {tier['stars']} Stars → {tier['label']}",
                callback_data=f"buy:{tier['stars']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        f"💰 <b>Пополнение баланса</b>\n\n"
        f"Текущий баланс: <b>{db_user.balance:.0f}</b> 💎\n\n"
        f"Оплата через Telegram Stars ⭐\n"
        f"Выбери пакет:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("buy:"))
async def send_invoice(callback: CallbackQuery):
    """Send Telegram Stars invoice."""
    stars = int(callback.data.split(":")[1])

    # Find matching tier
    tier = next((t for t in PAYMENT_TIERS if t["stars"] == stars), None)
    if not tier:
        await callback.answer("❌ Пакет не найден", show_alert=True)
        return

    await callback.message.answer_invoice(
        title=f"Пополнение {tier['label']}",
        description=f"Пополнение баланса на {tier['neurons']} нейронов",
        payload=f"topup_{stars}_{tier['neurons']}",
        currency="XTR",  # Telegram Stars currency code
        prices=[LabeledPrice(label=tier["label"], amount=stars)],
    )
    await callback.answer()


# ─── Pre-checkout ────────────────────────────────

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout: PreCheckoutQuery):
    """Always approve pre-checkout (validation happens here if needed)."""
    await pre_checkout.answer(ok=True)


# ─── Successful Payment ─────────────────────────

@router.message(F.successful_payment)
async def process_payment(message: Message, db_user: User, session: AsyncSession):
    """Process successful Telegram Stars payment (top-ups and subscriptions)."""
    payment = message.successful_payment
    payload = payment.invoice_payload

    try:
        parts = payload.split("_")
        payment_type = parts[0]  # "topup" or "sub"

        if payment_type == "topup":
            # topup_100_12000
            stars = int(parts[1])
            neurons = float(parts[2])

            new_balance = await topup_balance(
                session=session,
                user=db_user,
                neurons_amount=neurons,
                category="topup_stars",
                description=f"Telegram Stars: {stars} stars → {neurons:.0f} neurons",
            )

            await message.answer(
                f"🎉 <b>Оплата прошла!</b>\n\n"
                f"⭐ Оплачено: {stars} Stars\n"
                f"💎 Начислено: <b>{neurons:.0f}</b> нейронов\n"
                f"💰 Новый баланс: <b>{new_balance:.0f}</b> 💎",
                parse_mode="HTML",
            )

        elif payment_type == "sub":
            # sub_pro_50000
            from datetime import datetime, timedelta, timezone
            from app.models.subscription import Subscription

            plan_key = parts[1]
            neurons = float(parts[2])

            # Create subscription record
            sub = Subscription(
                user_id=db_user.id,
                plan=plan_key,
                is_active=True,
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            )
            session.add(sub)

            # Update user tier
            db_user.subscription_tier = plan_key

            # Credit neurons
            new_balance = await topup_balance(
                session=session,
                user=db_user,
                neurons_amount=neurons,
                category="subscription",
                description=f"Subscription {plan_key}: {neurons:.0f} neurons",
            )

            plan_names = {"pro": "⭐ Pro", "premium": "👑 Premium", "ultimate": "💎 Ultimate"}
            plan_name = plan_names.get(plan_key, plan_key)

            await message.answer(
                f"🎉 <b>Подписка {plan_name} активирована!</b>\n\n"
                f"💎 Начислено: <b>{neurons:.0f}</b> нейронов\n"
                f"💰 Новый баланс: <b>{new_balance:.0f}</b> 💎\n"
                f"⏳ Действует: 30 дней",
                parse_mode="HTML",
            )
        else:
            logger.error(f"Unknown payment type: {payload}")
            await message.answer("⚠️ Неизвестный тип платежа.")
            return

    except (IndexError, ValueError) as e:
        logger.error(f"Invalid payment payload: {payload} — {e}")
        await message.answer("⚠️ Ошибка обработки. Обратись в поддержку.")
        return

    logger.info(f"Payment: user {db_user.telegram_id}, payload={payload}")

