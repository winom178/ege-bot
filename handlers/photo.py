# handlers/photo.py
import os
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from ocr_helper import ocr_from_photo, download_photo
from .utils import ai_text, premium_required

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data.startswith("subj_photo_"))
async def subj_photo_instruction(callback: CallbackQuery, state: FSMContext):
    subj = callback.data.split("_")[2]
    await callback.message.delete()
    await photo_instruction(callback.message, state)

async def photo_instruction(message: Message, state: FSMContext):
    await message.answer(
        "📸 **Отправь фото задания**\n\n"
        "Ты можешь сфотографировать любое задание по химии или биологии (из учебника, распечатки или с экрана) и отправить мне.\n"
        "Я распознаю текст с помощью OCR, а затем решу его и объясню решение.\n\n"
        "**Это премиум-функция.** Если у тебя есть подписка, просто отправь фото.",
        parse_mode="Markdown"
    )

@router.message(F.photo)
@premium_required
async def handle_photo(message: Message, state: FSMContext):
    logger.info(f"Photo received from user {message.from_user.id}")
    try:
        await message.answer("⏳ Обрабатываю фото, распознаю текст...")
        photo = message.photo[-1]
        file_path = await download_photo(message.bot, photo.file_id)
        logger.info(f"Photo downloaded to {file_path}")

        text = await ocr_from_photo(file_path)
        logger.info(f"OCR result: {text[:100]}...")

        try:
            os.remove(file_path)
        except:
            pass

        if not text or text.startswith("Ошибка"):
            await message.answer("Не удалось распознать текст на фото. Попробуй отправить более чёткое изображение.")
            return

        await message.answer(f"📝 Распознанный текст:\n{text}\n\n⏳ Анализирую задание...")

        prompt = (
            f"Реши задание ЕГЭ по химии или биологии, которое приведено ниже. "
            f"Объясни решение подробно, шаг за шагом, как для ученика. Если это тест с выбором ответа, укажи правильный вариант и почему.\n\n"
            f"Текст задания:\n{text}"
        )
        answer = await ai_text(prompt, max_tokens=1000)
        await message.answer(f"🧠 **Решение:**\n\n{answer}", parse_mode="Markdown")
    except Exception as e:
        logger.exception(f"Error in handle_photo: {e}")
        await message.answer("❌ Произошла внутренняя ошибка при обработке фото.")