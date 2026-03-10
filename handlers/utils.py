# handlers/utils.py
import logging
import re
from functools import wraps
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import database as db
from data import VIDEO_LINKS
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

client = OpenAI(base_url="https://polza.ai/api/v1", api_key=os.getenv("POLZA_AI_API_KEY")) if os.getenv("POLZA_AI_API_KEY") else None

def clean_text(text: str) -> str:
    text = re.sub(r'\*\*|\*_|__|\[.*?\]\(.*?\)', '', text)
    text = text.replace('* ', '- ').replace('**', '').replace('__', '')
    return text.strip()

async def ai_text(prompt: str, max_tokens: int = 700) -> str:
    if not client:
        return "ИИ недоступен (добавьте POLZA_AI_API_KEY в .env)"
    try:
        resp = client.chat.completions.create(
            model="x-ai/grok-4-fast",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=max_tokens
        )
        text = resp.choices[0].message.content.strip()
        return clean_text(text)
    except Exception as e:
        logger.error(f"Ошибка ИИ: {e}")
        return f"Не удалось получить ответ от ИИ\n(ошибка: {str(e)})"

def get_video_links(subj: str, theme_id: str) -> list:
    try:
        if subj in VIDEO_LINKS and theme_id in VIDEO_LINKS[subj]:
            return VIDEO_LINKS[subj][theme_id]
    except Exception as e:
        logger.error(f"Ошибка получения видео: {e}")
    return []

# ===== НОВЫЙ ДЕКОРАТОР ДЛЯ ПРЕДМЕТНЫХ ПОДПИСОК =====
def subject_premium_required(handler):
    """Декоратор для проверки премиум-доступа к конкретному предмету.
       Предполагается, что subject передаётся в callback_data или в state.
    """
    @wraps(handler)
    async def wrapper(event, *args, **kwargs):
        # Определяем user_id и способ ответа
        if isinstance(event, Message):
            user_id = event.from_user.id
            answer_method = event.answer
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            answer_method = event.message.answer
        else:
            return await handler(event, *args, **kwargs)

        # Пытаемся извлечь subject из callback_data
        subject = None
        if isinstance(event, CallbackQuery):
            # Ищем subject в callback_data – обычно это последняя часть после подчёркивания
            # Например: "pdf_chemistry_1.1" → subject = "chemistry"
            parts = event.data.split('_')
            # Предполагаем, что subject – это либо часть после префикса, либо второй элемент
            # Для разных callback_data может быть по-разному. Упростим: ищем subject в известных ключах.
            # Если parts[1] есть в списке предметов – это subject.
            known_subjects = ["chemistry", "biology", "math", "physics", "informatics", "history", "geography", "social", "literature", "russian"]
            if len(parts) >= 2 and parts[1] in known_subjects:
                subject = parts[1]
            elif len(parts) >= 3 and parts[2] in known_subjects:
                subject = parts[2]
        # Если не нашли в callback_data, можно попробовать взять из state (но это сложнее)
        # Для упрощения будем считать, что subject передаётся в kwargs или мы его не используем.

        if subject is None:
            # Если subject не удалось определить, может быть, это общая функция без привязки к предмету?
            # В таком случае пропускаем проверку или считаем, что доступ есть.
            return await handler(event, *args, **kwargs)

        # Проверяем наличие подписки на этот предмет
        if db.has_subject_premium(user_id, subject):
            return await handler(event, *args, **kwargs)
        else:
            # Предлагаем купить премиум на этот предмет
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"🌟 Купить премиум по {subject}", callback_data=f"buy_subject_premium_{subject}")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
            ])
            await answer_method(
                f"🔒 **Это премиум-функция для предмета {subject}**\n\n"
                "Для доступа оформи подписку на этот предмет:",
                reply_markup=kb,
                parse_mode="Markdown"
            )
            if isinstance(event, CallbackQuery):
                await event.answer()
            return None
    return wrapper

# ===== СТАРЫЙ ДЕКОРАТОР (оставляем для совместимости, но теперь не используется) =====
def premium_required(handler):
    @wraps(handler)
    async def wrapper(event, *args, **kwargs):
        if isinstance(event, Message):
            user_id = event.from_user.id
            answer_method = event.answer
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            answer_method = event.message.answer
        else:
            return await handler(event, *args, **kwargs)

        if db.has_premium(user_id):
            return await handler(event, *args, **kwargs)
        else:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🌟 Купить премиум", callback_data="premium")]
            ])
            await answer_method(
                "🔒 **Это премиум-функция**\n\n"
                "Для доступа к этой функции оформи подписку:",
                reply_markup=kb,
                parse_mode="Markdown"
            )
            if isinstance(event, CallbackQuery):
                await event.answer()
            return None
    return wrapper