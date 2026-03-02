"""Base command handlers: /start (with referral support), /help, /profile."""

from aiogram import Router
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User

router = Router(name="base_commands")


@router.message(CommandStart(deep_link=True))
async def cmd_start_deeplink(message: Message, db_user: User, session: AsyncSession, command: CommandObject):
    """Handle /start with referral deep link: /start ref_XXXXXXXX"""
    args = command.args or ""

    if args.startswith("ref_"):
        referral_code = args[4:]  # strip "ref_"
        if not db_user.referred_by_id:  # Only process if not already referred
            from app.handlers.subscriptions import process_referral
            await process_referral(session, db_user, referral_code, message.bot)

    # Show normal start menu
    await _show_main_menu(message, db_user)


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User):
    """Welcome message with main menu."""
    await _show_main_menu(message, db_user)


async def _show_main_menu(message: Message, db_user: User):
    """Render main menu keyboard."""
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
            InlineKeyboardButton(text="🎨 Генерация картинок", callback_data="image_gen"),
        ],
        [
            InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
            InlineKeyboardButton(text="💰 Пополнить", callback_data="topup"),
        ],
        [
            InlineKeyboardButton(text="👥 Рефералка", callback_data="referral"),
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


@router.callback_query(lambda c: c.data == "help")
async def cb_help(callback: CallbackQuery):
    """Help text via callback."""
    help_text = (
        "📚 <b>Доступные команды:</b>\n\n"
        "/start — Главное меню\n"
        "/help — Эта справка\n"
        "/profile — Твой профиль и баланс\n"
        "/newchat — Создать новый чат\n"
        "/balance — Проверить баланс\n"
        "/image — Генерация картинки\n"
        "/image_wide — Широкая картинка\n"
        "/image_tall — Высокая картинка\n"
        "/admin — Админ-панель\n\n"
        "💡 Просто напиши мне сообщение, и я отвечу через выбранную AI-модель!"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")],
    ])
    await callback.message.edit_text(help_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Help text."""
    help_text = (
        "📚 <b>Доступные команды:</b>\n\n"
        "/start — Главное меню\n"
        "/help — Эта справка\n"
        "/profile — Твой профиль и баланс\n"
        "/newchat — Создать новый чат\n"
        "/balance — Проверить баланс\n"
        "/image — Генерация картинки\n"
        "/image_wide — Широкая картинка\n"
        "/image_tall — Высокая картинка\n"
        "/admin — Админ-панель\n\n"
        "💡 Просто напиши мне сообщение, и я отвечу через выбранную AI-модель!"
    )
    await message.answer(help_text, parse_mode="HTML")


@router.callback_query(lambda c: c.data == "profile")
async def cb_profile(callback: CallbackQuery, db_user: User):
    """Profile via callback."""
    await _show_profile(callback.message, db_user, edit=True)
    await callback.answer()


@router.callback_query(lambda c: c.data == "balance")
async def cb_balance(callback: CallbackQuery, db_user: User):
    """Balance via callback."""
    await callback.message.edit_text(
        f"💎 Твой баланс: <b>{db_user.balance:.0f}</b> нейронов",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Пополнить", callback_data="topup")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")],
        ]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(Command("profile"))
async def cmd_profile(message: Message, db_user: User):
    """User profile with stats."""
    await _show_profile(message, db_user, edit=False)


@router.message(Command("balance"))
async def cmd_balance(message: Message, db_user: User):
    """Quick balance check."""
    await message.answer(
        f"💎 Твой баланс: <b>{db_user.balance:.0f}</b> нейронов",
        parse_mode="HTML",
    )


async def _show_profile(message, db_user: User, edit: bool = False):
    """Render user profile."""
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
            InlineKeyboardButton(text="👥 Рефералка", callback_data="referral"),
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu"),
        ],
    ])

    if edit:
        await message.edit_text(profile_text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(profile_text, reply_markup=keyboard, parse_mode="HTML")
