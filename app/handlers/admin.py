"""Admin panel handler — statistics, user management, bot configuration."""

import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.models.transaction import Transaction
from app.models.chat import ChatSession
from app.models.ai_model import AIModel
from app.core.config import get_admin_ids
from app.services.billing import neurons_to_usd

logger = logging.getLogger(__name__)
router = Router(name="admin")


def is_admin(telegram_id: int) -> bool:
    return telegram_id in get_admin_ids()


# ─── Admin Command ───────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message, db_user: User, session: AsyncSession):
    """Admin panel entry point."""
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats"),
            InlineKeyboardButton(text="👥 Пользователи", callback_data="admin:users"),
        ],
        [
            InlineKeyboardButton(text="💰 Финансы", callback_data="admin:finance"),
            InlineKeyboardButton(text="🔧 Настройки", callback_data="admin:settings"),
        ],
        [
            InlineKeyboardButton(text="🤖 AI Модели", callback_data="admin:models:0"),
            InlineKeyboardButton(text="📢 Рассылка", callback_data="admin:broadcast"),
        ],
    ])

    await message.answer(
        "🔐 <b>Админ-панель</b>\n\n"
        "Выбери раздел:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


# ─── Statistics ──────────────────────────────────

@router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery, session: AsyncSession):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    # Total users
    total_users = await session.scalar(select(func.count(User.id)))

    # Active users (have at least 1 chat session)
    active_users = await session.scalar(
        select(func.count(func.distinct(ChatSession.user_id)))
    )

    # Total transactions
    total_txn = await session.scalar(select(func.count(Transaction.id)))

    # Total revenue in USD
    total_revenue_usd = await session.scalar(
        select(func.sum(Transaction.real_cost_usd))
        .where(Transaction.category.like("spend_%"))
    ) or 0.0

    # Total neurons spent
    total_neurons_spent = await session.scalar(
        select(func.sum(func.abs(Transaction.amount)))
        .where(Transaction.amount < 0)
    ) or 0.0

    # Total neurons topped up
    total_neurons_topup = await session.scalar(
        select(func.sum(Transaction.amount))
        .where(Transaction.amount > 0)
    ) or 0.0

    text = (
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: <b>{total_users}</b>\n"
        f"💬 Активных пользователей: <b>{active_users}</b>\n"
        f"📝 Всего транзакций: <b>{total_txn}</b>\n\n"
        f"💰 <b>Финансы:</b>\n"
        f"├ Потрачено на API (USD): <b>${total_revenue_usd:.4f}</b>\n"
        f"├ Нейронов списано: <b>{total_neurons_spent:.0f}</b>\n"
        f"└ Нейронов пополнено: <b>{total_neurons_topup:.0f}</b>\n"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin:back")],
    ])

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ─── Users List ──────────────────────────────────

@router.callback_query(F.data == "admin:users")
async def admin_users(callback: CallbackQuery, session: AsyncSession):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    result = await session.execute(
        select(User).order_by(User.created_at.desc()).limit(20)
    )
    users = result.scalars().all()

    lines = ["👥 <b>Последние пользователи:</b>\n"]
    for u in users:
        status = "🚫" if u.is_blocked else "✅"
        lines.append(
            f"{status} <code>{u.telegram_id}</code> | "
            f"@{u.username or '—'} | "
            f"💎 {u.balance:.0f} | "
            f"{u.subscription_tier}"
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin:back")],
    ])

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


# ─── Finance ─────────────────────────────────────

@router.callback_query(F.data == "admin:finance")
async def admin_finance(callback: CallbackQuery, session: AsyncSession):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    # Top spending models
    result = await session.execute(
        select(
            Transaction.model_used,
            func.count(Transaction.id).label("count"),
            func.sum(Transaction.real_cost_usd).label("total_usd"),
            func.sum(func.abs(Transaction.amount)).label("total_neurons"),
        )
        .where(Transaction.category.like("spend_%"))
        .group_by(Transaction.model_used)
        .order_by(func.sum(Transaction.real_cost_usd).desc())
        .limit(10)
    )
    models = result.all()

    lines = ["💰 <b>Расходы по моделям:</b>\n"]
    for m in models:
        model_name = (m.model_used or "unknown").split("/")[-1]
        lines.append(
            f"• <b>{model_name}</b>: {m.count} запр. | "
            f"${m.total_usd:.4f} | 💎 {m.total_neurons:.0f}"
        )

    if not models:
        lines.append("Пока нет данных")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin:back")],
    ])

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


# ─── Give Neurons (Admin) ────────────────────────

@router.callback_query(F.data == "admin:settings")
async def admin_settings(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Выдать нейроны", callback_data="admin:give_neurons")],
        [InlineKeyboardButton(text="🚫 Заблокировать юзера", callback_data="admin:block_user")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin:back")],
    ])

    await callback.message.edit_text(
        "🔧 <b>Настройки</b>\n\n"
        "Для выдачи нейронов используй:\n"
        "<code>/give TELEGRAM_ID AMOUNT</code>\n\n"
        "Для блокировки:\n"
        "<code>/block TELEGRAM_ID</code>\n"
        "<code>/unblock TELEGRAM_ID</code>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(Command("give"))
async def cmd_give_neurons(message: Message, session: AsyncSession):
    """Give neurons to a user: /give TELEGRAM_ID AMOUNT"""
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("Формат: <code>/give TELEGRAM_ID AMOUNT</code>", parse_mode="HTML")
        return

    try:
        target_tg_id = int(parts[1])
        amount = float(parts[2])
    except ValueError:
        await message.answer("❌ Неверный формат чисел")
        return

    result = await session.execute(
        select(User).where(User.telegram_id == target_tg_id)
    )
    target_user = result.scalar_one_or_none()
    if not target_user:
        await message.answer(f"❌ Пользователь {target_tg_id} не найден")
        return

    from app.services.billing import topup_balance
    new_balance = await topup_balance(
        session=session,
        user=target_user,
        neurons_amount=amount,
        category="admin_topup",
        description=f"Admin give by {message.from_user.id}",
    )

    await message.answer(
        f"✅ Выдано <b>{amount:.0f}</b> 💎 пользователю <code>{target_tg_id}</code>\n"
        f"Новый баланс: <b>{new_balance:.0f}</b> 💎",
        parse_mode="HTML",
    )


@router.message(Command("block"))
async def cmd_block(message: Message, session: AsyncSession):
    """Block a user: /block TELEGRAM_ID"""
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Формат: <code>/block TELEGRAM_ID</code>", parse_mode="HTML")
        return

    try:
        target_tg_id = int(parts[1])
    except ValueError:
        await message.answer("❌ Неверный формат ID")
        return

    result = await session.execute(
        select(User).where(User.telegram_id == target_tg_id)
    )
    target_user = result.scalar_one_or_none()
    if not target_user:
        await message.answer(f"❌ Пользователь {target_tg_id} не найден")
        return

    target_user.is_blocked = True
    await session.commit()
    await message.answer(f"🚫 Пользователь <code>{target_tg_id}</code> заблокирован", parse_mode="HTML")


@router.message(Command("unblock"))
async def cmd_unblock(message: Message, session: AsyncSession):
    """Unblock a user: /unblock TELEGRAM_ID"""
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Формат: <code>/unblock TELEGRAM_ID</code>", parse_mode="HTML")
        return

    try:
        target_tg_id = int(parts[1])
    except ValueError:
        await message.answer("❌ Неверный формат ID")
        return

    result = await session.execute(
        select(User).where(User.telegram_id == target_tg_id)
    )
    target_user = result.scalar_one_or_none()
    if not target_user:
        await message.answer(f"❌ Пользователь {target_tg_id} не найден")
        return

    target_user.is_blocked = False
    await session.commit()
    await message.answer(f"✅ Пользователь <code>{target_tg_id}</code> разблокирован", parse_mode="HTML")


# ─── Broadcast ───────────────────────────────────

@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.message.edit_text(
        "📢 <b>Рассылка</b>\n\n"
        "Для рассылки используй:\n"
        "<code>/broadcast Текст сообщения</code>\n\n"
        "Сообщение будет отправлено всем пользователям.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, session: AsyncSession):
    """Broadcast message to all users: /broadcast TEXT"""
    if not is_admin(message.from_user.id):
        return

    text = message.text.replace("/broadcast", "", 1).strip()
    if not text:
        await message.answer("Формат: <code>/broadcast Текст сообщения</code>", parse_mode="HTML")
        return

    result = await session.execute(
        select(User.telegram_id).where(User.is_blocked == False)
    )
    user_ids = [r[0] for r in result.all()]

    sent = 0
    failed = 0
    status_msg = await message.answer(f"📢 Рассылка: 0/{len(user_ids)}...")

    for tg_id in user_ids:
        try:
            await message.bot.send_message(tg_id, text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

        if (sent + failed) % 25 == 0:
            try:
                await status_msg.edit_text(f"📢 Рассылка: {sent + failed}/{len(user_ids)}...")
            except Exception:
                pass

    await status_msg.edit_text(
        f"📢 Рассылка завершена!\n\n"
        f"✅ Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}",
    )


# ─── Back to Admin ───────────────────────────────

@router.callback_query(F.data == "admin:back")
async def admin_back(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats"),
            InlineKeyboardButton(text="👥 Пользователи", callback_data="admin:users"),
        ],
        [
            InlineKeyboardButton(text="💰 Финансы", callback_data="admin:finance"),
            InlineKeyboardButton(text="🔧 Настройки", callback_data="admin:settings"),
        ],
        [
            InlineKeyboardButton(text="🤖 AI Модели", callback_data="admin:models:0"),
            InlineKeyboardButton(text="📢 Рассылка", callback_data="admin:broadcast"),
        ],
    ])

    await callback.message.edit_text(
        "🔐 <b>Админ-панель</b>\n\n"
        "Выбери раздел:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


# ─── AI Models Management ────────────────────────

MODELS_PER_PAGE = 8


@router.callback_query(F.data.startswith("admin:models:"))
async def admin_models_list(callback: CallbackQuery, session: AsyncSession):
    """Browse all AI models with pagination."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    page = int(callback.data.split(":")[2])

    # Count total models in DB
    total = await session.scalar(select(func.count(AIModel.id))) or 0
    enabled_count = await session.scalar(
        select(func.count(AIModel.id)).where(AIModel.is_enabled == True)
    ) or 0

    if total == 0:
        await callback.message.edit_text(
            "🤖 <b>AI Модели</b>\n\n"
            "В базе нет моделей. Нажми «Синхронизировать» для загрузки из OpenRouter.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Синхронизировать", callback_data="admin:sync_models")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin:back")],
            ]),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    # Fetch page
    result = await session.execute(
        select(AIModel)
        .order_by(AIModel.is_enabled.desc(), AIModel.sort_order, AIModel.name)
        .offset(page * MODELS_PER_PAGE)
        .limit(MODELS_PER_PAGE)
    )
    models = result.scalars().all()

    total_pages = (total + MODELS_PER_PAGE - 1) // MODELS_PER_PAGE

    buttons = []
    for m in models:
        status = "✅" if m.is_enabled else "⬜"
        # Truncate name for button (max ~40 chars)
        short_name = m.name[:35] if len(m.name) > 35 else m.name
        buttons.append([
            InlineKeyboardButton(
                text=f"{status} {short_name}",
                callback_data=f"admin:model:{m.id}",
            )
        ])

    # Navigation
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"admin:models:{page - 1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"admin:models:{page + 1}"))
    buttons.append(nav_buttons)

    buttons.append([
        InlineKeyboardButton(text="🔄 Синхронизировать", callback_data="admin:sync_models"),
    ])
    buttons.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin:back"),
    ])

    await callback.message.edit_text(
        f"🤖 <b>AI Модели</b> ({enabled_count} вкл. / {total} всего)\n\n"
        f"✅ = включена для пользователей\n"
        f"⬜ = выключена",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:model:"))
async def admin_model_detail(callback: CallbackQuery, session: AsyncSession):
    """Show model details and toggle."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    model_id = int(callback.data.split(":")[2])
    result = await session.execute(select(AIModel).where(AIModel.id == model_id))
    model = result.scalar_one_or_none()

    if not model:
        await callback.answer("❌ Модель не найдена", show_alert=True)
        return

    status = "✅ Включена" if model.is_enabled else "⬜ Выключена"
    toggle_text = "⬜ Выключить" if model.is_enabled else "✅ Включить"

    # Price per 1M tokens
    p_in = model.price_prompt * 1_000_000
    p_out = model.price_completion * 1_000_000

    text = (
        f"🤖 <b>{model.name}</b>\n\n"
        f"📋 <b>ID:</b> <code>{model.model_id}</code>\n"
        f"📊 <b>Статус:</b> {status}\n\n"
        f"💰 <b>Цены (за 1M токенов):</b>\n"
        f"├ Input: <b>${p_in:.4f}</b>\n"
        f"└ Output: <b>${p_out:.4f}</b>\n\n"
        f"📥 <b>Вход:</b> {model.input_modalities}\n"
        f"📤 <b>Выход:</b> {model.output_modalities}\n"
        f"📏 <b>Контекст:</b> {model.context_length:,} токенов\n"
    )

    if model.description:
        desc = model.description[:200]
        text += f"\n📝 {desc}"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data=f"admin:toggle:{model.id}")],
        [InlineKeyboardButton(text="🔙 К списку", callback_data="admin:models:0")],
    ])

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin:toggle:"))
async def admin_toggle_model(callback: CallbackQuery, session: AsyncSession):
    """Toggle model enabled/disabled."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    model_id = int(callback.data.split(":")[2])
    result = await session.execute(select(AIModel).where(AIModel.id == model_id))
    model = result.scalar_one_or_none()

    if not model:
        await callback.answer("❌ Модель не найдена", show_alert=True)
        return

    model.is_enabled = not model.is_enabled
    await session.commit()

    status = "✅ Включена" if model.is_enabled else "⬜ Выключена"
    await callback.answer(f"{model.name}: {status}", show_alert=True)

    # Refresh detail view
    await admin_model_detail(callback, session)


@router.callback_query(F.data == "admin:sync_models")
async def admin_sync_models(callback: CallbackQuery, session: AsyncSession):
    """Force sync models from OpenRouter API."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.answer("🔄 Синхронизация...", show_alert=False)

    from app.services.ai_service import fetch_openrouter_models, sync_models_to_db
    data = await fetch_openrouter_models()
    if not data:
        await callback.message.edit_text(
            "❌ Не удалось получить данные от OpenRouter",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin:models:0")],
            ]),
        )
        return

    new_count = await sync_models_to_db(session)

    await callback.message.edit_text(
        f"✅ Синхронизация завершена!\n\n"
        f"📦 Всего моделей: <b>{len(data)}</b>\n"
        f"🆕 Новых добавлено: <b>{new_count}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤖 К моделям", callback_data="admin:models:0")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin:back")],
        ]),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()

