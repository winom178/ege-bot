# handlers/profile.py
import re
import os
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import database as db
from data import TASKS
from keyboards import kb_profile_menu, kb_cancel, kb_main
from .states import Form

router = Router()

ADMIN_IDS = [int(id) for id in os.getenv("ADMIN_IDS", "").split(",") if id]
PREMIUM_PRICE = 300  # Telegram Stars за месяц для одного предмета (можно изменить)

# ========== МЕНЮ ПРОФИЛЯ ==========
@router.message(F.text == "📊 Профиль")
async def profile_menu(message: Message, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Моя статистика", callback_data="my_stats")],
        [InlineKeyboardButton(text="📅 Цель / Напоминание", callback_data="goal_reminder")],
        [InlineKeyboardButton(text="📌 Избранное", callback_data="my_favorites")],
        [InlineKeyboardButton(text="🔮 Прогноз баллов", callback_data="predict_score")],
        [InlineKeyboardButton(text="📉 Анализ слабых тем", callback_data="weak_analysis")],
        [InlineKeyboardButton(text="🌟 Мои подписки", callback_data="my_premiums")],
        [InlineKeyboardButton(text="🎁 Подарить подписку", callback_data="gift_menu")]
    ])
    await message.answer("Твой профиль:", reply_markup=kb)

# ========== МОИ ПОДПИСКИ ==========
@router.callback_query(F.data == "my_premiums")
async def my_premiums(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    premiums = db.get_user_premiums(user_id)
    if not premiums:
        text = "У тебя нет активных подписок на предметы."
    else:
        lines = ["**Твои активные подписки:**"]
        for p in premiums:
            lines.append(f"• {p['subject']} – до {p['expires_at']}")
        text = "\n".join(lines)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад в профиль", callback_data="back_to_profile")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

# ========== МЕНЮ ПОДАРКА ==========
@router.callback_query(F.data == "gift_menu")
async def gift_menu(callback: CallbackQuery, state: FSMContext):
    buttons = []
    for subject_key in TASKS.keys():
        display_name = {
            "chemistry": "Химия",
            "biology": "Биология",
            "math": "Математика",
            "physics": "Физика",
            "informatics": "Информатика",
            "history": "История",
            "geography": "География",
            "social": "Обществознание",
            "literature": "Литература",
            "russian": "Русский язык"
        }.get(subject_key, subject_key.capitalize())
        buttons.append([InlineKeyboardButton(text=display_name, callback_data=f"gift_subject_{subject_key}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")])
    await callback.message.edit_text(
        "Выбери предмет, подписку на который хочешь подарить:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("gift_subject_"))
async def gift_subject(callback: CallbackQuery, state: FSMContext):
    subject = callback.data.split("_")[2]
    await state.update_data(gift_subject=subject)
    await callback.message.edit_text(
        f"Введи Telegram ID пользователя, которому хочешь подарить подписку на {subject}.\n\n"
        "Он может узнать свой ID у бота @userinfobot."
    )
    await state.set_state(Form.gift_user_input)

@router.message(Form.gift_user_input)
async def gift_user_input(message: Message, state: FSMContext):
    try:
        target_id = int(message.text.strip())
    except:
        await message.answer("❌ Неверный формат ID. Попробуй ещё раз или отправь /cancel.")
        return
    data = await state.get_data()
    subject = data.get("gift_subject")
    await state.update_data(gift_target=target_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="7 дней - 100 ⭐", callback_data=f"gift_pay_{subject}_{target_id}_7")],
        [InlineKeyboardButton(text="30 дней - 300 ⭐", callback_data=f"gift_pay_{subject}_{target_id}_30")],
        [InlineKeyboardButton(text="90 дней - 750 ⭐", callback_data=f"gift_pay_{subject}_{target_id}_90")],
        [InlineKeyboardButton(text="← Отмена", callback_data="back_to_profile")]
    ])
    await message.answer(f"Выбери срок подписки для пользователя {target_id} по предмету {subject}:", reply_markup=kb)
    await state.clear()

@router.callback_query(F.data.startswith("gift_pay_"))
async def gift_pay(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    subject = parts[2]
    target_id = int(parts[3])
    days = int(parts[4])
    expires = db.gift_subject_premium(callback.from_user.id, target_id, subject, days)
    await callback.message.edit_text(
        f"✅ Подарок отправлен!\n"
        f"Пользователь {target_id} получил {days} дней премиума по предмету {subject} (до {expires})."
    )
    await callback.answer()

# ========== СТАТИСТИКА ==========
@router.callback_query(F.data == "my_stats")
async def cb_my_stats(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    user = db.get_user(callback.from_user.id)
    percent = (user['correct_answers'] / user['total_answers'] * 100) if user['total_answers'] > 0 else 0
    await callback.message.answer(
        f"📊 **Твоя статистика:**\n"
        f"Уровень: {user['level']}\n"
        f"Опыт: {user['exp']}\n"
        f"Всего ответов: {user['total_answers']}\n"
        f"Правильных: {user['correct_answers']}\n"
        f"Процент: {percent:.1f}%\n"
        f"Дата экзамена: {user.get('exam_date', 'не указана')}",
        parse_mode="Markdown"
    )
    await callback.answer()

# ========== ИЗБРАННОЕ ==========
@router.callback_query(F.data == "my_favorites")
async def cb_my_favorites(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    user_id = callback.from_user.id
    favs = db.get_favorites(user_id)
    if not favs:
        await callback.message.answer("📭 У тебя пока нет избранных конспектов. Сохраняй их звездочкой в меню темы.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for fav in favs:
        subject = fav['subject']
        theme_id = fav['theme_id']
        theme_name = TASKS.get(subject, {}).get(theme_id, {}).get("name", theme_id)
        if len(theme_name) > 40:
            theme_name = theme_name[:40] + "…"
        kb.inline_keyboard.append([InlineKeyboardButton(text=theme_name, callback_data=f"cons_{subject}_{theme_id}")])
    await callback.message.answer("📌 **Твои избранные конспекты:**", reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

# ========== ЦЕЛЬ И НАПОМИНАНИЯ ==========
@router.callback_query(F.data == "goal_reminder")
async def cb_goal_reminder(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    count, goal = db.get_daily_goal(callback.from_user.id)
    text = f"📅 Ежедневная цель: {count}/{goal} заданий.\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить цель", callback_data="set_goal")],
        [InlineKeyboardButton(text="Установить напоминание", callback_data="set_reminder")]
    ])
    await callback.message.answer(text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "set_goal")
async def set_goal_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введи новую ежедневную цель (число заданий в день):")
    await state.set_state(Form.reminder_set)
    await callback.answer()

@router.message(Form.reminder_set)
async def process_new_goal(message: Message, state: FSMContext):
    try:
        goal = int(message.text.strip())
        if goal < 1 or goal > 50:
            raise ValueError
        db.set_daily_goal(message.from_user.id, goal)
        await message.answer(f"✅ Ежедневная цель изменена на {goal} заданий.", reply_markup=kb_main())
        await state.clear()
    except:
        await message.answer("❌ Некорректное число. Введи число от 1 до 50.", reply_markup=kb_cancel())

@router.callback_query(F.data == "set_reminder")
async def set_reminder_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введи время для напоминания в формате HH:MM (например, 19:00):")
    await state.set_state(Form.reminder_set)
    await callback.answer()

@router.message(Form.reminder_set)
async def process_reminder_time(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await message.answer("Установка отменена.", reply_markup=kb_main())
        await state.clear()
        return
    time_str = message.text.strip()
    if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
        await message.answer("Неверный формат. Используй HH:MM, например 09:30 или 19:00", reply_markup=kb_cancel())
        return
    db.set_reminder(message.from_user.id, time_str)
    await message.answer(f"✅ Напоминание установлено на {time_str} каждый день.", reply_markup=kb_main())
    await state.clear()

# ========== ПРОГНОЗ БАЛЛОВ И АНАЛИЗ ==========
@router.callback_query(F.data == "predict_score")
async def cb_predict_score(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer(
        "🔮 **Прогноз баллов ЕГЭ**\n\n"
        "После прохождения варианта ты получишь прогноз на основе твоих результатов.\n"
        "Пока нет данных. Пройди вариант в разделе «Тренировка»."
    )
    await callback.answer()

@router.callback_query(F.data == "weak_analysis")
async def cb_weak_analysis(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    stats = db.get_theme_stats(user_id)
    weak_themes = []
    for s in stats:
        if s['total'] >= 3 and (s['correct'] / s['total']) < 0.6:
            theme_name = TASKS.get(s['subject'], {}).get(s['theme_id'], {}).get("name", s['theme_id'])
            percent = (s['correct'] / s['total']) * 100
            weak_themes.append(f"• {theme_name} – {percent:.0f}% правильных")

    if weak_themes:
        text = "📉 **Темы, требующие внимания:**\n" + "\n".join(weak_themes)
    else:
        text = "✅ У тебя нет слабых тем! Так держать!"

    await callback.message.delete()
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

# ========== КУПЛЯ ПРЕМИУМА (ОБЩИЙ РАЗДЕЛ) ==========
@router.message(F.text == "🌟 Купить премиум")
async def show_premium_menu_message(message: Message, state: FSMContext):
    # Для текстовой кнопки не удаляем сообщение пользователя, просто отвечаем
    text = "🌟 **Премиум-доступ** 🌟\n\nВыбери предмет, на который хочешь оформить подписку:"
    buttons = []
    for subject_key in TASKS.keys():
        display_name = {
            "chemistry": "Химия 🧪",
            "biology": "Биология 🌿",
            "math": "Математика 📐",
            "physics": "Физика ⚡",
            "informatics": "Информатика 💻",
            "history": "История 📜",
            "geography": "География 🌍",
            "social": "Обществознание 🏛️",
            "literature": "Литература 📖",
            "russian": "Русский язык 🇷🇺"
        }.get(subject_key, subject_key.capitalize())
        buttons.append([InlineKeyboardButton(text=display_name, callback_data=f"buy_subject_premium_{subject_key}")])
    buttons.append([InlineKeyboardButton(text="← Назад в профиль", callback_data="back_to_profile")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="Markdown")

@router.callback_query(F.data == "premium")
async def show_premium_menu_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    text = "🌟 **Премиум-доступ** 🌟\n\nВыбери предмет, на который хочешь оформить подписку:"
    buttons = []
    for subject_key in TASKS.keys():
        display_name = {
            "chemistry": "Химия 🧪",
            "biology": "Биология 🌿",
            "math": "Математика 📐",
            "physics": "Физика ⚡",
            "informatics": "Информатика 💻",
            "history": "История 📜",
            "geography": "География 🌍",
            "social": "Обществознание 🏛️",
            "literature": "Литература 📖",
            "russian": "Русский язык 🇷🇺"
        }.get(subject_key, subject_key.capitalize())
        buttons.append([InlineKeyboardButton(text=display_name, callback_data=f"buy_subject_premium_{subject_key}")])
    buttons.append([InlineKeyboardButton(text="← Назад в профиль", callback_data="back_to_profile")])
    await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("buy_subject_premium_"))
async def buy_subject_premium(callback: CallbackQuery, state: FSMContext):
    subject = callback.data.split("_")[3]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 месяц - 300 ⭐", callback_data=f"pay_subject_{subject}_30")],
        [InlineKeyboardButton(text="3 месяца - 750 ⭐", callback_data=f"pay_subject_{subject}_90")],
        [InlineKeyboardButton(text="6 месяцев - 1200 ⭐", callback_data=f"pay_subject_{subject}_180")],
        [InlineKeyboardButton(text="← Назад", callback_data="premium")]
    ])
    await callback.message.edit_text(
        f"🌟 **Покупка премиума по предмету {subject}**\n\nВыбери срок подписки:",
        reply_markup=kb
    )
    await callback.answer()

@router.callback_query(F.data.startswith("pay_subject_"))
async def pay_subject(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    subject = parts[2]
    days = int(parts[3])
    # Здесь должна быть логика оплаты через Telegram Stars
    expires = db.set_subject_premium(callback.from_user.id, subject, days)
    await callback.message.edit_text(f"✅ Премиум на предмет {subject} активирован на {days} дней! (до {expires})")
    await callback.answer()

# ========== ОБРАБОТЧИК ВОЗВРАТА ==========
@router.callback_query(F.data == "back_to_profile")
async def back_to_profile(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await profile_menu(callback.message, state)