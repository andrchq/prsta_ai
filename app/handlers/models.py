"""Model selection and persona handlers — reads enabled models from DB."""

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.models.chat import ChatSession
from app.models.ai_model import AIModel

router = Router(name="model_selection")


async def _get_active_session(session: AsyncSession, user: User) -> ChatSession:
    """Get or create user's active chat session."""
    result = await session.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id, ChatSession.is_active == True)
        .order_by(ChatSession.created_at.desc())
        .limit(1)
    )
    chat_session = result.scalar_one_or_none()

    if chat_session is None:
        chat_session = ChatSession(user_id=user.id, title="Новый чат")
        session.add(chat_session)
        await session.commit()
        await session.refresh(chat_session)

    return chat_session


# ═══════════════════════════════════════
# MODEL SELECTION (from DB)
# ═══════════════════════════════════════

@router.callback_query(F.data == "select_model")
async def select_model(callback: CallbackQuery, db_user: User, session: AsyncSession):
    """Show enabled AI models from DB."""
    active = await _get_active_session(session, db_user)

    # Get enabled models from DB
    result = await session.execute(
        select(AIModel)
        .where(AIModel.is_enabled == True)
        .order_by(AIModel.sort_order, AIModel.name)
    )
    models = result.scalars().all()

    if not models:
        await callback.message.edit_text(
            "⚠️ Нет доступных моделей.\n\nАдминистратор ещё не включил ни одной модели.",
        )
        await callback.answer()
        return

    buttons = []
    for m in models:
        current = " ✓" if m.full_id == active.model_id else ""
        # Show modality + name + price indicator
        price_1m_out = m.price_completion * 1_000_000
        if price_1m_out < 1:
            price_tag = "💚"  # free/very cheap
        elif price_1m_out < 5:
            price_tag = "💛"  # cheap
        elif price_1m_out < 15:
            price_tag = "🧡"  # moderate
        else:
            price_tag = "❤️"   # expensive

        buttons.append([
            InlineKeyboardButton(
                text=f"{m.modality_emoji} {m.name} {price_tag}{current}",
                callback_data=f"set_model:{m.model_id[:60]}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        "🧠 <b>Выбери AI модель:</b>\n\n"
        "💚 дешёвая  💛 средняя  🧡 дорогая  ❤️ премиум",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_model:"))
async def set_model(callback: CallbackQuery, db_user: User, session: AsyncSession):
    """Save model selection to active chat session."""
    model_id = callback.data.split(":", 1)[1]

    # Find model in DB
    result = await session.execute(
        select(AIModel).where(AIModel.model_id == model_id, AIModel.is_enabled == True)
    )
    model = result.scalar_one_or_none()

    if not model:
        await callback.answer("❌ Модель не найдена или отключена", show_alert=True)
        return

    # Save to active session
    active = await _get_active_session(session, db_user)
    active.model_id = model.full_id  # "openrouter/..."
    await session.commit()

    await callback.message.edit_text(
        f"✅ Модель выбрана: <b>{model.modality_emoji} {model.name}</b>\n\n"
        f"📝 {(model.description or '')[:200]}\n"
        f"💰 {model.price_display}\n\n"
        f"Просто напиши мне сообщение! 💬",
        parse_mode="HTML",
    )
    await callback.answer(f"Выбрана: {model.name}")


# ═══════════════════════════════════════
# PERSONAS (Roles)
# ═══════════════════════════════════════

PERSONAS: dict[str, dict] = {
    "programmer": {
        "name": "👨‍💻 Программист Senior",
        "prompt": "Ты — опытный Senior программист с 15 летним опытом. Отвечай структурировано, с примерами кода. Объясняй архитектурные решения. Используй лучшие практики.",
    },
    "psychologist": {
        "name": "🧠 Психолог",
        "prompt": "Ты — профессиональный психолог. Слушай внимательно, задавай уточняющие вопросы, давай эмпатичные ответы. Не ставь диагнозов, но помогай разобраться в эмоциях и ситуациях.",
    },
    "english_teacher": {
        "name": "🇬🇧 Учитель Английского",
        "prompt": "Ты — дружелюбный учитель английского языка. Помогай с грамматикой, переводами и произношением. Давай объяснения на русском, но с примерами на английском.",
    },
    "copywriter": {
        "name": "✍️ Копирайтер",
        "prompt": "Ты — креативный копирайтер. Помогай создавать продающие тексты, заголовки, посты для соцсетей. Предлагай несколько вариантов.",
    },
    "translator": {
        "name": "🌐 Переводчик",
        "prompt": "Ты — профессиональный переводчик. Переводи тексты между русским и английским. Учитывай контекст и стилевые особенности.",
    },
    "creative": {
        "name": "🎨 Креативный Ассистент",
        "prompt": "Ты — креативный ассистент. Генерируй идеи, помогай с брейнштормом, предлагай необычные решения. Думай нестандартно.",
    },
}


@router.callback_query(F.data == "personas")
async def show_personas(callback: CallbackQuery):
    """Show available AI personas."""
    buttons = []
    for key, persona in PERSONAS.items():
        buttons.append([
            InlineKeyboardButton(
                text=persona["name"],
                callback_data=f"set_persona:{key}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="🚫 Без роли", callback_data="set_persona:none")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        "🎭 <b>Выбери персоналию:</b>\n\n"
        "Бот будет отвечать в стиле выбранной роли.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_persona:"))
async def set_persona(callback: CallbackQuery, db_user: User, session: AsyncSession):
    """Save persona to active chat session's system_prompt."""
    persona_key = callback.data.split(":")[1]
    active = await _get_active_session(session, db_user)

    if persona_key == "none":
        active.system_prompt = None
        await session.commit()
        await callback.message.edit_text(
            "🚫 Персоналия сброшена.\n\n"
            "Бот будет отвечать в стандартном режиме.",
        )
        await callback.answer("Роль сброшена")
        return

    persona = PERSONAS.get(persona_key)
    if not persona:
        await callback.answer("❌ Роль не найдена", show_alert=True)
        return

    active.system_prompt = persona["prompt"]
    await session.commit()

    await callback.message.edit_text(
        f"✅ Роль выбрана: <b>{persona['name']}</b>\n\n"
        f"Теперь бот будет отвечать в этом стиле. Просто напиши сообщение! 💬",
        parse_mode="HTML",
    )
    await callback.answer(f"Роль: {persona['name']}")
