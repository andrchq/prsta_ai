"""Chat session management handlers."""

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.models.chat import ChatSession

router = Router(name="chat_sessions")


@router.callback_query(F.data == "new_chat")
async def new_chat(callback: CallbackQuery, db_user: User, session: AsyncSession):
    """Create a new chat session."""
    chat_session = ChatSession(
        user_id=db_user.id,
        title="Новый чат",
    )
    session.add(chat_session)
    await session.commit()
    await session.refresh(chat_session)

    await callback.message.edit_text(
        f"💬 Чат <b>#{chat_session.id}</b> создан!\n\n"
        f"🧠 Модель: <code>{chat_session.model_id}</code>\n\n"
        f"Просто отправь мне сообщение, и я отвечу! ✨",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "my_chats")
async def my_chats(callback: CallbackQuery, db_user: User, session: AsyncSession):
    """List user's chat sessions."""
    result = await session.execute(
        select(ChatSession)
        .where(ChatSession.user_id == db_user.id, ChatSession.is_active == True)
        .order_by(ChatSession.created_at.desc())
        .limit(10)
    )
    sessions = result.scalars().all()

    if not sessions:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать чат", callback_data="new_chat")],
        ])
        await callback.message.edit_text(
            "📂 У тебя пока нет чатов.\nСоздай новый!",
            reply_markup=keyboard,
        )
        await callback.answer()
        return

    buttons = []
    for s in sessions:
        buttons.append([
            InlineKeyboardButton(
                text=f"💬 {s.title} (#{s.id})",
                callback_data=f"open_chat:{s.id}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="➕ Новый чат", callback_data="new_chat")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        "📂 <b>Твои чаты:</b>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, db_user: User):
    """Return to main menu."""
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
    ])
    await callback.message.edit_text(
        f"👋 <b>{db_user.first_name or 'Главное меню'}</b>\n\n"
        f"💎 Баланс: <b>{db_user.balance:.0f}</b> нейронов",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()
