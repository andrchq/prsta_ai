"""
Image generation handler — /image command and inline menu.
"""

import io
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile,
)
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.services.image_service import generate_image, download_image, IMAGE_MODELS
from app.services.billing import charge_user, usd_to_neurons

logger = logging.getLogger(__name__)
router = Router(name="image_generation")


# ─── /image command ──────────────────────────────

@router.message(Command("image"))
async def cmd_image(message: Message, db_user: User, session: AsyncSession):
    """Generate an image from text prompt: /image <prompt>"""
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer(
            "🎨 <b>Генерация изображений</b>\n\n"
            "Использование: <code>/image описание картинки</code>\n\n"
            "Примеры:\n"
            "• <code>/image Космический котёнок в скафандре</code>\n"
            "• <code>/image Пейзаж горного озера на закате</code>\n"
            "• <code>/image Минималистичный логотип для IT-стартапа</code>\n\n"
            f"💎 Стоимость: ~{usd_to_neurons(0.04):.0f} нейронов (1024x1024)",
            parse_mode="HTML",
        )
        return

    prompt = args[1].strip()
    await _generate_and_send(message, db_user, session, prompt)


@router.callback_query(F.data == "image_gen")
async def image_gen_menu(callback: CallbackQuery):
    """Show image generation info."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")],
    ])
    await callback.message.edit_text(
        "🎨 <b>Генерация изображений</b>\n\n"
        "Отправь команду:\n"
        "<code>/image твой промпт</code>\n\n"
        "Размеры через команду:\n"
        "• <code>/image_wide промпт</code> — широкое (1792×1024)\n"
        "• <code>/image_tall промпт</code> — высокое (1024×1792)\n\n"
        f"💎 Стоимость: ~{usd_to_neurons(0.04):.0f}-{usd_to_neurons(0.08):.0f} нейронов",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(Command("image_wide"))
async def cmd_image_wide(message: Message, db_user: User, session: AsyncSession):
    """Generate a wide landscape image."""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: <code>/image_wide промпт</code>", parse_mode="HTML")
        return
    await _generate_and_send(message, db_user, session, args[1].strip(), size="1792x1024")


@router.message(Command("image_tall"))
async def cmd_image_tall(message: Message, db_user: User, session: AsyncSession):
    """Generate a tall portrait image."""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: <code>/image_tall промпт</code>", parse_mode="HTML")
        return
    await _generate_and_send(message, db_user, session, args[1].strip(), size="1024x1792")


# ─── Core generation logic ──────────────────────

async def _generate_and_send(
    message: Message,
    db_user: User,
    session: AsyncSession,
    prompt: str,
    size: str = "1024x1024",
    model: str = "dall-e-3",
):
    """Generate image, charge user, send result."""
    from app.services.image_service import DALLE3_PRICING

    # Pre-check balance
    estimated_cost = DALLE3_PRICING.get(size, 0.04)
    estimated_neurons = usd_to_neurons(estimated_cost)

    if db_user.balance < estimated_neurons:
        await message.answer(
            f"❌ Недостаточно нейронов!\n\n"
            f"Нужно: <b>{estimated_neurons:.0f}</b> 💎\n"
            f"Баланс: <b>{db_user.balance:.0f}</b> 💎\n\n"
            f"Пополни: /profile",
            parse_mode="HTML",
        )
        return

    # Show progress
    progress_msg = await message.answer(
        f"🎨 Генерирую изображение...\n\n"
        f"📝 <i>{prompt[:200]}</i>\n"
        f"📐 Размер: {size}",
        parse_mode="HTML",
    )

    try:
        # Generate
        result = generate_image(
            prompt=prompt,
            model=model,
            size=size,
        )
        result = await result

        # Download image bytes
        image_bytes = await download_image(result["url"])

        # Charge user
        success, neurons_cost = await charge_user(
            session=session,
            user=db_user,
            cost_usd=result["cost_usd"],
            category="spend_image",
            model_used=model,
            description=f"Image: {prompt[:100]}",
        )

        if not success:
            await progress_msg.edit_text(
                f"❌ Недостаточно нейронов! Нужно: {neurons_cost:.0f} 💎",
            )
            return

        # Delete progress message
        try:
            await progress_msg.delete()
        except Exception:
            pass

        # Send image
        photo = BufferedInputFile(image_bytes, filename="generated.png")
        revised = result.get("revised_prompt", "")
        caption = (
            f"🎨 <b>Сгенерировано!</b>\n\n"
            f"📝 {prompt[:500]}\n"
        )
        if revised and revised != prompt:
            caption += f"\n🔄 <i>DALL·E: {revised[:300]}</i>\n"
        caption += f"\n💎 <i>-{neurons_cost:.0f} | Баланс: {db_user.balance:.0f}</i>"

        if len(caption) > 1024:
            caption = caption[:1020] + "..."

        await message.answer_photo(
            photo=photo,
            caption=caption,
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"Image generation failed: {e}", exc_info=True)
        await progress_msg.edit_text(
            "⚠️ Ошибка при генерации изображения.\n"
            "Попробуй изменить промпт или попробуй позже."
        )
