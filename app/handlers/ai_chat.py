"""
Handler for processing user messages and sending them to AI.
This is the core handler that ties chat sessions, AI service, and billing together.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.models.chat import ChatSession, ChatMessage
from app.services.ai_service import chat_completion
from app.services.billing import charge_user

logger = logging.getLogger(__name__)
router = Router(name="ai_chat")


@router.message(F.text)
async def handle_ai_message(message: Message, db_user: User, session: AsyncSession):
    """
    Process incoming text messages:
    1. Find or create active chat session
    2. Build message history
    3. Call AI model
    4. Charge user
    5. Save response and reply
    """
    # 1. Find user's latest active chat session (or create one)
    result = await session.execute(
        select(ChatSession)
        .where(ChatSession.user_id == db_user.id, ChatSession.is_active == True)
        .order_by(ChatSession.created_at.desc())
        .limit(1)
    )
    chat_session = result.scalar_one_or_none()

    if chat_session is None:
        chat_session = ChatSession(user_id=db_user.id, title="Новый чат")
        session.add(chat_session)
        await session.commit()
        await session.refresh(chat_session)

    # 2. Save user message
    user_msg = ChatMessage(
        session_id=chat_session.id,
        role="user",
        content=message.text,
    )
    session.add(user_msg)
    await session.commit()

    # 3. Build context from recent messages
    history_result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == chat_session.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(20)  # Last 20 messages for context
    )
    history = list(reversed(history_result.scalars().all()))

    messages = []
    # Add system prompt if the session has one
    if chat_session.system_prompt:
        messages.append({"role": "system", "content": chat_session.system_prompt})

    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})

    # 4. Show "typing" indicator
    typing_msg = await message.answer("⏳ Думаю...")

    try:
        # 5. Call AI
        ai_response = await chat_completion(
            messages=messages,
            model_id=chat_session.model_id,
        )

        # 6. Charge user
        success, neurons_cost = await charge_user(
            session=session,
            user=db_user,
            cost_usd=ai_response.cost_usd,
            category="spend_text",
            model_used=ai_response.model_used,
            tokens_input=ai_response.tokens_input,
            tokens_output=ai_response.tokens_output,
        )

        if not success:
            await typing_msg.edit_text(
                f"❌ Недостаточно нейронов!\n\n"
                f"Нужно: <b>{neurons_cost:.0f}</b> 💎\n"
                f"Баланс: <b>{db_user.balance:.0f}</b> 💎\n\n"
                f"Пополни баланс: /profile",
                parse_mode="HTML",
            )
            return

        # 7. Save assistant response
        assistant_msg = ChatMessage(
            session_id=chat_session.id,
            role="assistant",
            content=ai_response.content,
            tokens_used=ai_response.tokens_input + ai_response.tokens_output,
        )
        session.add(assistant_msg)
        await session.commit()

        # 8. Reply to user
        # Split into chunks of 4000 chars if needed (Telegram limit)
        response_text = ai_response.content
        footer = f"\n\n<i>💎 -{neurons_cost:.0f} | Баланс: {db_user.balance:.0f}</i>"

        if len(response_text) + len(footer) <= 4096:
            await typing_msg.edit_text(
                response_text + footer,
                parse_mode="HTML",
            )
        else:
            # Long responses: send in chunks
            await typing_msg.delete()
            chunks = [response_text[i:i+4000] for i in range(0, len(response_text), 4000)]
            for i, chunk in enumerate(chunks):
                if i == len(chunks) - 1:
                    await message.answer(chunk + footer, parse_mode="HTML")
                else:
                    await message.answer(chunk)

    except Exception as e:
        logger.error(f"AI chat error: {e}")
        await typing_msg.edit_text(
            "⚠️ Произошла ошибка при обработке запроса.\n"
            "Попробуй еще раз или смени модель.",
        )
