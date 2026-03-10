# handlers/lava.py
import os
import uuid
import hmac
import hashlib
import json
import logging
import requests
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import database as db

router = Router()
logger = logging.getLogger(__name__)

# Загружаем настройки из окружения
LAVA_SHOP_ID = os.getenv("LAVA_SHOP_ID")
LAVA_SECRET_KEY = os.getenv("LAVA_SECRET_KEY")
LAVA_API_KEY = os.getenv("LAVA_API_KEY")
BOT_USERNAME = os.getenv("BOT_USERNAME")

# URL API LAVA (уточните актуальный в документации)
LAVA_API_URL = "https://api.lava.ru/v1/invoice"  # или другой эндпоинт

# Цены за подписку (как и раньше)
PRICES = {30: 300, 90: 750, 180: 1200}


def generate_signature(data: dict, secret_key: str) -> str:
    """Генерирует подпись для запроса к LAVA"""
    sorted_keys = sorted(data.keys())
    sorted_data = {key: data[key] for key in sorted_keys}
    data_string = json.dumps(sorted_data, separators=(',', ':'))
    return hmac.new(
        secret_key.encode(),
        data_string.encode(),
        hashlib.sha256
    ).hexdigest()


@router.callback_query(F.data.startswith("pay_subject_"))
async def pay_subject(callback: CallbackQuery, state: FSMContext):
    """Создаёт платёж в LAVA и отправляет ссылку"""
    parts = callback.data.split("_")
    subject = parts[2]
    days = int(parts[3])
    amount = PRICES[days]
    order_id = str(uuid.uuid4())  # уникальный ID заказа

    # Сохраняем платёж в БД (см. следующий шаг)
    db.save_pending_payment(order_id, callback.from_user.id, subject, days)

    # Данные для запроса к LAVA
    payment_data = {
        "order_id": order_id,
        "amount": amount,
        "currency": "RUB",
        "description": f"Премиум {subject} на {days} дней",
        "success_url": f"https://t.me/{BOT_USERNAME}",
        "fail_url": f"https://t.me/{BOT_USERNAME}",
        "hook_url": "https://ваш-сервис.onrender.com/lava-webhook",
        "custom_data": {
            "user_id": callback.from_user.id,
            "subject": subject,
            "days": days
        }
    }

    # Генерируем подпись
    signature = generate_signature(payment_data, LAVA_SECRET_KEY)

    headers = {
        "Authorization": f"Bearer {LAVA_API_KEY}",
        "Content-Type": "application/json",
        "Signature": signature
    }

    await callback.message.edit_text("⏳ Создаю ссылку для оплаты...")

    try:
        response = requests.post(LAVA_API_URL, json=payment_data, headers=headers)
        result = response.json()

        if response.status_code == 200 and result.get("url"):
            payment_url = result["url"]
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Перейти к оплате", url=payment_url)],
                [InlineKeyboardButton(text="✅ Я оплатил (проверить)", callback_data=f"check_lava_payment_{order_id}")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_profile")]
            ])
            await callback.message.edit_text(
                f"💰 **Оплата подписки**\n\n"
                f"Предмет: **{subject}**\n"
                f"Срок: **{days} дней**\n"
                f"Сумма: **{amount} ₽**\n\n"
                f"Нажмите кнопку для оплаты через LAVA.\n"
                f"После успешной оплаты подписка активируется автоматически.",
                reply_markup=kb,
                parse_mode="Markdown"
            )
        else:
            logger.error(f"LAVA error: {result}")
            await callback.message.edit_text("❌ Ошибка создания платежа. Попробуйте позже.")
    except Exception as e:
        logger.exception(f"Payment exception: {e}")
        await callback.message.edit_text("❌ Произошла ошибка. Попробуйте позже.")

    await callback.answer()


@router.callback_query(F.data.startswith("check_lava_payment_"))
async def check_lava_payment(callback: CallbackQuery, state: FSMContext):
    """Проверка статуса платежа вручную"""
    order_id = callback.data.replace("check_lava_payment_", "")

    payment = db.get_pending_payment(order_id)
    if not payment:
        await callback.message.edit_text("❌ Платёж не найден.")
        return

    # Здесь можно добавить запрос к LAVA для проверки статуса
    # Но проще подождать вебхука или просто активировать (небезопасно)
    # Для примера просто уведомим админа (как в варианте с Capusta)

    admin_id = os.getenv("ADMIN_ID")
    await callback.bot.send_message(
        admin_id,
        f"⚠️ Пользователь @{callback.from_user.username} (id: {callback.from_user.id}) сообщает об оплате подписки {payment['subject']} на {payment['days']} дней.\n"
        f"Проверьте в LAVA и выдайте вручную."
    )
    await callback.message.edit_text(
        "✅ Администратору отправлен запрос на активацию. Обычно это занимает несколько минут. Спасибо за ожидание!"
    )
    await callback.answer()
