"""Base command handlers: /start, /help, /profile."""

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from app.models.user import User

router = Router(name="base_commands")


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User):
    """Welcome message with main menu."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💬 Новый чат", callback_data="new_chat"),
            InlineKeyboardButton(text="📂 Мои чаты", callback_data="my_chats"),
        ],
        [
            InlineKeyboardButton(text="🧠 Выбрать модель", callback_data="select_model"),
            InlineKeyboardButton(text="🎭 Персоналии", callback_data="personas"),
        ],
        [
            InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
            InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
        ],
        [
            InlineKeyboardButton(text="❓ Помощь", callback_data="help"),
        ],
    ])

    await message.answer(
        f"👋 Привет, <b>{db_user.first_name or 'друг'}</b>!\n\n"
        f"Я — твой AI-ассистент. Выбери модель, задай вопрос — и поехали! 🚀\n\n"
        f"💎 Твой баланс: <b>{db_user.balance:.0f}</b> нейронов",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Help text."""
    help_text = (
        "📚 <b>Доступные команды:</b>\n\n"
        "/start — Главное меню\n"
        "/help — Эта справка\n"
        "/profile — Твой профиль и баланс\n"
        "/newchat — Создать новый чат\n"
        "/models — Список доступных моделей\n"
        "/balance — Проверить баланс\n\n"
        "💡 Просто напиши мне сообщение, и я отвечу через выбранную AI-модель!"
    )
    await message.answer(help_text, parse_mode="HTML")


@router.message(Command("profile"))
async def cmd_profile(message: Message, db_user: User):
    """User profile with stats."""
    profile_text = (
        f"👤 <b>Профиль</b>\n\n"
        f"🆔 ID: <code>{db_user.telegram_id}</code>\n"
        f"📛 Имя: {db_user.first_name or '—'} {db_user.last_name or ''}\n"
        f"👤 Username: @{db_user.username or '—'}\n"
        f"💎 Баланс: <b>{db_user.balance:.0f}</b> нейронов\n"
        f"📦 Подписка: <b>{db_user.subscription_tier.upper()}</b>\n"
        f"📅 Зарегистрирован: {db_user.created_at.strftime('%d.%m.%Y')}"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💰 Пополнить", callback_data="topup"),
            InlineKeyboardButton(text="⭐ Подписка", callback_data="subscription"),
        ],
        [
            InlineKeyboardButton(text="📊 История расходов", callback_data="spending_history"),
        ],
    ])

    await message.answer(profile_text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("balance"))
async def cmd_balance(message: Message, db_user: User):
    """Quick balance check."""
    await message.answer(
        f"💎 Твой баланс: <b>{db_user.balance:.0f}</b> нейронов",
        parse_mode="HTML",
    )
