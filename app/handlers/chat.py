"""Chat session management handlers."""

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.models.chat import ChatSession, ChatMessage
from app.services.ai_service import AVAILABLE_MODELS

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

    model_name = chat_session.model_id.split("/")[-1]
    await callback.message.edit_text(
        f"💬 Чат <b>#{chat_session.id}</b> создан!\n\n"
        f"🧠 Модель: <code>{model_name}</code>\n\n"
        f"Просто отправь мне сообщение, и я отвечу! ✨",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(Command("newchat"))
async def cmd_new_chat(message: Message, db_user: User, session: AsyncSession):
    """Create new chat via command."""
    chat_session = ChatSession(
        user_id=db_user.id,
        title="Новый чат",
    )
    session.add(chat_session)
    await session.commit()
    await session.refresh(chat_session)

    model_name = chat_session.model_id.split("/")[-1]
    await message.answer(
        f"💬 Чат <b>#{chat_session.id}</b> создан!\n\n"
        f"🧠 Модель: <code>{model_name}</code>\n"
        f"Просто отправь сообщение! ✨",
        parse_mode="HTML",
    )


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
        model_name = s.model_id.split("/")[-1] if s.model_id else "—"
        buttons.append([
            InlineKeyboardButton(
                text=f"💬 {s.title} • {model_name}",
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


@router.callback_query(F.data.startswith("open_chat:"))
async def open_chat(callback: CallbackQuery, db_user: User, session: AsyncSession):
    """Switch to a specific chat session (make it the latest active)."""
    chat_id = int(callback.data.split(":")[1])

    result = await session.execute(
        select(ChatSession)
        .where(ChatSession.id == chat_id, ChatSession.user_id == db_user.id)
    )
    chat_session = result.scalar_one_or_none()
    if not chat_session:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    # Count messages
    msg_result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == chat_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(3)
    )
    last_msgs = msg_result.scalars().all()

    model_name = chat_session.model_id.split("/")[-1] if chat_session.model_id else "—"
    persona = "Без роли" if not chat_session.system_prompt else "Персоналия установлена"

    preview = ""
    if last_msgs:
        preview = "\n\n📝 <b>Последние сообщения:</b>\n"
        for m in reversed(last_msgs):
            role_icon = "👤" if m.role == "user" else "🤖"
            content_short = m.content[:80] + "..." if len(m.content) > 80 else m.content
            preview += f"{role_icon} {content_short}\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🧠 Сменить модель", callback_data="select_model"),
            InlineKeyboardButton(text="🎭 Персоналия", callback_data="personas"),
        ],
        [
            InlineKeyboardButton(text="🗑 Удалить чат", callback_data=f"delete_chat:{chat_id}"),
        ],
        [
            InlineKeyboardButton(text="🔙 К списку", callback_data="my_chats"),
        ],
    ])

    await callback.message.edit_text(
        f"💬 <b>Чат #{chat_session.id}</b> — {chat_session.title}\n\n"
        f"🧠 Модель: <code>{model_name}</code>\n"
        f"🎭 {persona}"
        f"{preview}\n\n"
        f"Просто отправь сообщение для продолжения!",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delete_chat:"))
async def delete_chat(callback: CallbackQuery, db_user: User, session: AsyncSession):
    """Deactivate a chat session."""
    chat_id = int(callback.data.split(":")[1])

    result = await session.execute(
        select(ChatSession)
        .where(ChatSession.id == chat_id, ChatSession.user_id == db_user.id)
    )
    chat_session = result.scalar_one_or_none()
    if not chat_session:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    chat_session.is_active = False
    await session.commit()

    await callback.answer("🗑 Чат удален", show_alert=False)
    # Redirect to chat list
    await my_chats(callback, db_user, session)


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
