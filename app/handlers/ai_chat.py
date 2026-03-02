"""
Handler for processing user messages with STREAMING AI responses.
Edits the Telegram message in real-time as tokens arrive.
"""

import logging
import asyncio
import tiktoken
from aiogram import Router, F
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.models.chat import ChatSession, ChatMessage
from app.services.ai_service import stream_chat_completion, estimate_cost
from app.services.billing import charge_user

logger = logging.getLogger(__name__)
router = Router(name="ai_chat")

# ─── Streaming display config ─────────────────
# Telegram allows ~30 edits/minute per chat. We use OR logic:
# edit if enough TIME passed OR enough CHARS accumulated.
EDIT_INTERVAL_SEC = 0.8   # edit at most every 0.8s
MIN_CHARS_DELTA = 20      # or when 20+ new characters ready
FIRST_EDIT_CHARS = 5      # show first edit after just 5 chars (fast first impression)


def _count_tokens(text: str) -> int:
    """Approximate token count using tiktoken (cl100k_base)."""
    try:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


@router.message(F.text.func(lambda text: not text.startswith("/")))
async def handle_ai_message(message: Message, db_user: User, session: AsyncSession):
    """
    Process incoming text messages with streaming AI response.
    Shows text appearing progressively via message editing.
    """
    # 1. Find the latest active chat session (or create one)
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
        .limit(20)
    )
    history = list(reversed(history_result.scalars().all()))

    messages = []
    if chat_session.system_prompt:
        messages.append({"role": "system", "content": chat_session.system_prompt})
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})

    # 4. Send placeholder and stream
    bot_msg = await message.answer("💭 ...")

    try:
        full_response = ""
        last_edit_time = 0.0
        last_edit_len = 0
        edit_count = 0

        async for chunk in stream_chat_completion(
            messages=messages,
            model_id=chat_session.model_id,
        ):
            full_response += chunk
            now = asyncio.get_event_loop().time()
            chars_delta = len(full_response) - last_edit_len

            # First edit: show text ASAP (after just a few chars)
            # Subsequent edits: respect rate limit
            should_edit = False
            if edit_count == 0 and chars_delta >= FIRST_EDIT_CHARS:
                should_edit = True
            elif (now - last_edit_time >= EDIT_INTERVAL_SEC) and (chars_delta >= MIN_CHARS_DELTA):
                should_edit = True

            if should_edit:
                try:
                    display = full_response[:4000] + "  ▌"
                    await bot_msg.edit_text(display)
                    edit_count += 1
                except TelegramBadRequest:
                    pass
                last_edit_time = asyncio.get_event_loop().time()
                last_edit_len = len(full_response)

        if not full_response:
            await bot_msg.edit_text("⚠️ AI вернул пустой ответ. Попробуй ещё раз.")
            return

        # 5. Calculate cost and charge
        tokens_in = _count_tokens(" ".join(m["content"] for m in messages))
        tokens_out = _count_tokens(full_response)
        cost_usd = estimate_cost(chat_session.model_id, tokens_in, tokens_out)

        success, neurons_cost = await charge_user(
            session=session,
            user=db_user,
            cost_usd=cost_usd,
            category="spend_text",
            model_used=chat_session.model_id,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
        )

        if not success:
            await bot_msg.edit_text(
                f"❌ Недостаточно нейронов!\n\n"
                f"Нужно: <b>{neurons_cost:.0f}</b> 💎\n"
                f"Баланс: <b>{db_user.balance:.0f}</b> 💎\n\n"
                f"Пополни баланс: /profile",
                parse_mode="HTML",
            )
            return

        # 6. Save assistant message
        assistant_msg = ChatMessage(
            session_id=chat_session.id,
            role="assistant",
            content=full_response,
            tokens_used=tokens_in + tokens_out,
        )
        session.add(assistant_msg)
        await session.commit()

        # 7. Final message with cost footer
        footer = f"\n\n<i>💎 -{neurons_cost:.0f} | Баланс: {db_user.balance:.0f}</i>"
        final_text = full_response + footer

        if len(final_text) <= 4096:
            try:
                await bot_msg.edit_text(final_text, parse_mode="HTML")
            except TelegramBadRequest:
                await bot_msg.edit_text(final_text)
        else:
            await bot_msg.delete()
            chunks = [full_response[i:i+4000] for i in range(0, len(full_response), 4000)]
            for i, chunk_text in enumerate(chunks):
                text = chunk_text + footer if i == len(chunks) - 1 else chunk_text
                try:
                    await message.answer(text, parse_mode="HTML")
                except TelegramBadRequest:
                    await message.answer(text)

    except Exception as e:
        logger.error(f"AI chat error: {e}", exc_info=True)
        try:
            await bot_msg.edit_text(
                "⚠️ Произошла ошибка при обработке запроса.\n"
                "Попробуй еще раз или смени модель."
            )
        except TelegramBadRequest:
            pass
