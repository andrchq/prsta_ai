"""Model selection and persona handlers."""

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from app.services.ai_service import AVAILABLE_MODELS

router = Router(name="model_selection")


@router.callback_query(F.data == "select_model")
async def select_model(callback: CallbackQuery):
    """Show available AI models for selection."""
    buttons = []
    for key, model in AVAILABLE_MODELS.items():
        buttons.append([
            InlineKeyboardButton(
                text=f"{model['emoji']} {model['name']}",
                callback_data=f"set_model:{key}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        "🧠 <b>Выбери AI модель:</b>\n\n"
        "Модель будет использоваться для текущего чата.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_model:"))
async def set_model(callback: CallbackQuery):
    """Confirm model selection."""
    model_key = callback.data.split(":")[1]
    model = AVAILABLE_MODELS.get(model_key)

    if not model:
        await callback.answer("❌ Модель не найдена", show_alert=True)
        return

    # TODO: Save selected model to user's active chat session
    await callback.message.edit_text(
        f"✅ Модель выбрана: <b>{model['emoji']} {model['name']}</b>\n\n"
        f"📝 {model['description']}\n\n"
        f"Теперь просто напиши мне сообщение! 💬",
        parse_mode="HTML",
    )
    await callback.answer(f"Выбрана модель: {model['name']}")


# === PERSONAS (Roles) ===

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
        "prompt": "Ты — дружелюбный учитель английского языка. Помогай с грамматикой, переводами и произношением. Давай объяснения на русском, но с примерами на английском. Исправляй ошибки мягко.",
    },
    "copywriter": {
        "name": "✍️ Копирайтер",
        "prompt": "Ты — креативный копирайтер. Помогай создавать продающие тексты, заголовки, посты для соцсетей. Предлагай несколько вариантов. Учитывай целевую аудиторию.",
    },
    "translator": {
        "name": "🌐 Переводчик",
        "prompt": "Ты — профессиональный переводчик. Переводи тексты между русским и английским (или другими языками). Учитывай контекст и стилевые особенности.",
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
async def set_persona(callback: CallbackQuery):
    """Confirm persona selection."""
    persona_key = callback.data.split(":")[1]

    if persona_key == "none":
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

    # TODO: Save persona to user's active chat session system_prompt
    await callback.message.edit_text(
        f"✅ Роль выбрана: <b>{persona['name']}</b>\n\n"
        f"Теперь бот будет отвечать в этом стиле. Просто напиши сообщение! 💬",
        parse_mode="HTML",
    )
    await callback.answer(f"Роль: {persona['name']}")
