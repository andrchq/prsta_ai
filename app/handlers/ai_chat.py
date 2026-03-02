"""
Handler for processing user messages with STREAMING AI responses.
Uses sendMessageDraft (Bot API 9.3+) for real-time letter-by-letter display
when forum topic mode is enabled, with fallback to message editing.
"""

import logging
import asyncio
import tiktoken
from aiogram import Router, F, Bot
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

# Streaming config
DRAFT_INTERVAL = 0.3        # seconds between sendMessageDraft calls
EDIT_INTERVAL = 1.5          # seconds between editMessageText calls (fallback)
MIN_CHARS_DELTA = 40         # min new chars before sending draft update


def _count_tokens(text: str) -> int:
    """Approximate token count using tiktoken (cl100k_base)."""
    try:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


async def _send_message_draft(
    bot: Bot,
    chat_id: int,
    draft_id: int,
    text: str,
    message_thread_id: int | None = None,
) -> bool:
    """
    Send a message draft for real-time streaming display.
    Uses Bot API sendMessageDraft method (Bot API 9.3+).
    Returns True on success, False if not supported.
    """
    try:
        params = {
            "chat_id": chat_id,
            "draft_id": draft_id,
            "text": text[:4096],
        }
        if message_thread_id:
            params["message_thread_id"] = message_thread_id

        await bot.session.make_request(
            bot,
            "sendMessageDraft",
            params,
        )
        return True
    except Exception as e:
        logger.debug(f"sendMessageDraft not available: {e}")
        return False


async def _find_or_create_session(
    session: AsyncSession, db_user: User, message_thread_id: int | None = None
) -> ChatSession:
    """Find chat session by topic thread ID or get latest active one."""
    # If message is from a topic, find session by topic_thread_id
    if message_thread_id:
        result = await session.execute(
            select(ChatSession)
            .where(
                ChatSession.user_id == db_user.id,
                ChatSession.topic_thread_id == message_thread_id,
                ChatSession.is_active == True,
            )
            .limit(1)
        )
        chat_session = result.scalar_one_or_none()
        if chat_session:
            return chat_session

    # Fallback: get latest active session
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

    return chat_session


@router.message(F.text.func(lambda text: not text.startswith("/")))
async def handle_ai_message(message: Message, db_user: User, session: AsyncSession):
    """
    Process incoming text messages with streaming AI response.
    Uses sendMessageDraft for real-time display, falls back to editMessageText.
    Routes messages to correct chat session based on topic_thread_id.
    """
    # Determine which topic this message came from
    thread_id = getattr(message, "message_thread_id", None)

    # 1. Find the right chat session
    chat_session = await _find_or_create_session(session, db_user, thread_id)

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

    # 4. Try sendMessageDraft first (real-time streaming)
    draft_id = message.message_id  # Use original message ID as draft ID
    use_drafts = await _send_message_draft(
        bot=message.bot,
        chat_id=message.chat.id,
        draft_id=draft_id,
        text="💭 ...",
        message_thread_id=chat_session.topic_thread_id,
    )

    # Fallback: send a placeholder message to edit later
    bot_msg = None
    if not use_drafts:
        bot_msg = await message.answer(
            "💭 ...",
            message_thread_id=chat_session.topic_thread_id,
        )

    try:
        # 5. Stream AI response
        full_response = ""
        last_update_time = 0.0
        last_update_len = 0
        interval = DRAFT_INTERVAL if use_drafts else EDIT_INTERVAL

        async for chunk in stream_chat_completion(
            messages=messages,
            model_id=chat_session.model_id,
        ):
            full_response += chunk
            now = asyncio.get_event_loop().time()
            chars_since_update = len(full_response) - last_update_len

            if (now - last_update_time >= interval) and (chars_since_update >= MIN_CHARS_DELTA):
                try:
                    if use_drafts:
                        await _send_message_draft(
                            bot=message.bot,
                            chat_id=message.chat.id,
                            draft_id=draft_id,
                            text=full_response[:4096],
                            message_thread_id=chat_session.topic_thread_id,
                        )
                    elif bot_msg:
                        display = full_response[:4000] + "  ▌"
                        await bot_msg.edit_text(display)
                except TelegramBadRequest:
                    pass
                last_update_time = now
                last_update_len = len(full_response)

        if not full_response:
            error_text = "⚠️ AI вернул пустой ответ. Попробуй ещё раз."
            if use_drafts:
                await message.answer(
                    error_text,
                    message_thread_id=chat_session.topic_thread_id,
                )
            elif bot_msg:
                await bot_msg.edit_text(error_text)
            return

        # 6. Calculate cost and charge
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
            error_text = (
                f"❌ Недостаточно нейронов!\n\n"
                f"Нужно: <b>{neurons_cost:.0f}</b> 💎\n"
                f"Баланс: <b>{db_user.balance:.0f}</b> 💎\n\n"
                f"Пополни баланс: /profile"
            )
            if use_drafts:
                await message.answer(
                    error_text,
                    parse_mode="HTML",
                    message_thread_id=chat_session.topic_thread_id,
                )
            elif bot_msg:
                await bot_msg.edit_text(error_text, parse_mode="HTML")
            return

        # 7. Save assistant message
        assistant_msg = ChatMessage(
            session_id=chat_session.id,
            role="assistant",
            content=full_response,
            tokens_used=tokens_in + tokens_out,
        )
        session.add(assistant_msg)
        await session.commit()

        # 8. Send final message
        footer = f"\n\n<i>💎 -{neurons_cost:.0f} | Баланс: {db_user.balance:.0f}</i>"
        final_text = full_response + footer

        if use_drafts:
            # With drafts, send final message as regular message
            if len(final_text) <= 4096:
                try:
                    await message.answer(
                        final_text,
                        parse_mode="HTML",
                        message_thread_id=chat_session.topic_thread_id,
                    )
                except TelegramBadRequest:
                    await message.answer(
                        final_text,
                        message_thread_id=chat_session.topic_thread_id,
                    )
            else:
                chunks = [full_response[i:i+4000] for i in range(0, len(full_response), 4000)]
                for i, chunk in enumerate(chunks):
                    text = chunk + footer if i == len(chunks) - 1 else chunk
                    await message.answer(
                        text,
                        message_thread_id=chat_session.topic_thread_id,
                    )
        else:
            # With editing, update the placeholder message
            if len(final_text) <= 4096:
                try:
                    await bot_msg.edit_text(final_text, parse_mode="HTML")
                except TelegramBadRequest:
                    await bot_msg.edit_text(final_text)
            else:
                await bot_msg.delete()
                chunks = [full_response[i:i+4000] for i in range(0, len(full_response), 4000)]
                for i, chunk in enumerate(chunks):
                    text = chunk + footer if i == len(chunks) - 1 else chunk
                    try:
                        await message.answer(text, parse_mode="HTML")
                    except TelegramBadRequest:
                        await message.answer(text)

    except Exception as e:
        logger.error(f"AI chat error: {e}", exc_info=True)
        error_text = (
            "⚠️ Произошла ошибка при обработке запроса.\n"
            "Попробуй еще раз или смени модель."
        )
        try:
            if use_drafts:
                await message.answer(
                    error_text,
                    message_thread_id=chat_session.topic_thread_id,
                )
            elif bot_msg:
                await bot_msg.edit_text(error_text)
        except TelegramBadRequest:
            pass
