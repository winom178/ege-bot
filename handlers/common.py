# handlers/common.py
import asyncio
import logging
import os
import random
import re
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import database as db
from data import TASKS
from keyboards import kb_main, kb_cancel, kb_answers
from .states import Form
from .utils import ai_text, get_video_links

logger = logging.getLogger(__name__)
router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    
    # Проверка на подарок в ссылке (например, gift_chemistry_30)
    args = message.text.split()
    gift_info = None
    if len(args) > 1 and args[1].startswith("gift_"):
        parts = args[1].split('_')
        if len(parts) == 3:
            subject = parts[1]
            days = int(parts[2])
            gift_info = (subject, days)
    
    user = db.get_user(message.from_user.id, message.from_user.username)
    
    # Если есть подарок в ссылке, выдаём подписку
    if gift_info:
        subject, days = gift_info
        db.set_subject_premium(message.from_user.id, subject, days)
        await message.answer(f"🎁 Вы получили в подарок премиум на {days} дней по предмету {subject}!")
    
    if not user.get('exam_date'):
        welcome_text = (
            f"✨ Репетитор ЕГЭ 2026 ✨\n\n"
            f"Привет, {message.from_user.first_name}! Твой уровень: {user['level']}, опыт: {user['exp']}.\n\n"
            f"📋 Для начала рекомендую пройти тест на определение уровня.\n"
            f"Это поможет мне составить персональный план подготовки.\n"
            f"Нажми кнопку «📸 Разбор по фото» или выбери предмет в меню."
        )
    else:
        welcome_text = (
            f"✨ Репетитор ЕГЭ 2026 ✨\n\n"
            f"С возвращением, {message.from_user.first_name}! Твой уровень: {user['level']}, опыт: {user['exp']}.\n"
            f"Дата экзамена: {user['exam_date']}\n\n"
            "Выбирай предмет, тему – и вперёд!"
        )
    
    await message.answer(welcome_text, reply_markup=kb_main())

@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "📚 Доступные команды:\n"
        "/start - перезапустить бота\n"
        "/help - показать эту справку\n"
        "/stats - моя статистика\n"
        "/topics - прогресс по темам\n"
        "/daily - ежедневная цель\n"
        "/remind HH:MM - установить напоминание\n"
        "/remind_off - отключить напоминание\n"
        "/favorites - избранные конспекты\n"
        "/feedback - отправить сообщение администратору\n"
        "/level_test - пройти тест на определение уровня\n\n"
        "📸 Отправь фото задания – я распознаю текст и помогу с решением! (доступно в Премиум)\n\n"
        "Используй кнопки главного меню."
    )
    await message.answer(text)

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    user = db.get_user(message.from_user.id)
    percent = (user['correct_answers'] / user['total_answers'] * 100) if user['total_answers'] > 0 else 0
    await message.answer(
        f"📊 **Твоя статистика:**\n"
        f"Уровень: {user['level']}\n"
        f"Опыт: {user['exp']}\n"
        f"Всего ответов: {user['total_answers']}\n"
        f"Правильных: {user['correct_answers']}\n"
        f"Процент: {percent:.1f}%\n"
        f"Дата экзамена: {user.get('exam_date', 'не указана')}",
        parse_mode="Markdown"
    )

@router.message(Command("topics"))
async def cmd_topics(message: Message):
    user_id = message.from_user.id
    stats = db.get_theme_stats(user_id)
    if not stats:
        await message.answer("📭 Ты ещё не решал задания. Начни тренировку!")
        return
    
    subject_names = {
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
    }
    
    lines = []
    for s in stats:
        percent = (s['correct'] / s['total'] * 100) if s['total'] > 0 else 0
        subject = subject_names.get(s['subject'], s['subject'].capitalize())
        theme_name = TASKS.get(s['subject'], {}).get(s['theme_id'], {}).get("name", s['theme_id'])
        if len(theme_name) > 30:
            theme_name = theme_name[:30] + "…"
        lines.append(f"• {subject}: {theme_name} – {s['correct']}/{s['total']} ({percent:.0f}%)")
    await message.answer("📈 **Прогресс по темам:**\n" + "\n".join(lines), parse_mode="Markdown")

@router.message(Command("daily"))
async def cmd_daily(message: Message):
    count, goal = db.get_daily_goal(message.from_user.id)
    await message.answer(f"📅 Сегодня ты выполнил(а) {count} заданий из {goal}.\n"
                         f"Чтобы изменить цель, используй кнопку в меню.")

@router.message(Command("remind"))
async def cmd_remind(message: Message, state: FSMContext):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Укажи время в формате HH:MM, например: /remind 19:00")
        return
    time_str = args[1].strip()
    if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
        await message.answer("Неверный формат. Используй HH:MM, например 09:30 или 19:00")
        return
    db.set_reminder(message.from_user.id, time_str)
    await message.answer(f"✅ Напоминание установлено на {time_str} каждый день.\n"
                         f"Чтобы отключить, используй /remind_off")

@router.message(Command("remind_off"))
async def cmd_remind_off(message: Message):
    db.disable_reminder(message.from_user.id)
    await message.answer("🔕 Напоминание отключено.")

@router.message(Command("favorites"))
async def cmd_favorites(message: Message):
    user_id = message.from_user.id
    favs = db.get_favorites(user_id)
    if not favs:
        await message.answer("📭 У тебя пока нет избранных конспектов. Сохраняй их звездочкой в меню темы.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for fav in favs:
        subject = fav['subject']
        theme_id = fav['theme_id']
        theme_name = TASKS.get(subject, {}).get(theme_id, {}).get("name", theme_id)
        if len(theme_name) > 40:
            theme_name = theme_name[:40] + "…"
        kb.inline_keyboard.append([InlineKeyboardButton(text=theme_name, callback_data=f"cons_{subject}_{theme_id}")])
    await message.answer("📌 **Твои избранные конспекты:**", reply_markup=kb, parse_mode="Markdown")

@router.message(Command("feedback"))
async def cmd_feedback(message: Message, state: FSMContext):
    await message.answer("✏️ Напиши своё сообщение (пожелание, ошибка, предложение). Оно будет отправлено администратору.", reply_markup=kb_cancel())
    await state.set_state(Form.feedback)

@router.message(Form.feedback)
async def process_feedback(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await message.answer("Возвращаемся в главное меню.", reply_markup=kb_main())
        await state.clear()
        return
    db.add_feedback(message.from_user.id, message.text)
    await message.answer("✅ Спасибо! Сообщение отправлено.", reply_markup=kb_main())
    await state.clear()

@router.message(Command("level_test"))
async def cmd_level_test(message: Message, state: FSMContext, subject: str = None):
    all_tasks = []
    subjects = [subject] if subject else list(TASKS.keys())
    for subj in subjects:
        for theme_id in TASKS[subj].keys():
            all_tasks.extend(db.get_tasks_by_theme(subj, theme_id))
    if len(all_tasks) < 5:
        await message.answer("Недостаточно заданий для теста.")
        return
    test_tasks = random.sample(all_tasks, 5)
    await state.update_data(level_test_tasks=test_tasks, level_test_index=0, level_test_correct=0)
    first = test_tasks[0]
    await message.answer(
        f"🧪 **Тест на определение уровня**\n\nВопрос 1 из 5:\n{first['text']}",
        reply_markup=kb_answers(first, hint_used=False),
        parse_mode="Markdown"
    )
    await state.set_state(Form.level_test)

@router.callback_query(F.data.startswith("subj_level_"))
async def subj_level_test(callback: CallbackQuery, state: FSMContext):
    subj = callback.data.split("_")[2]
    await callback.message.delete()
    await cmd_level_test(callback.message, state, subject=subj)

# ========== ОБРАБОТЧИКИ КНОПОК ГЛАВНОГО МЕНЮ ==========
@router.message(F.text == "📸 Разбор по фото")
async def photo_button(message: Message, state: FSMContext):
    await photo_instruction(message, state)

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

@router.message(F.text == "🌟 Купить премиум")
async def buy_premium_button(message: Message, state: FSMContext):
    # Прямая отправка меню выбора предмета для покупки премиума
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

@router.message(F.text == "ℹ️ Помощь")
async def help_button(message: Message):
    await cmd_help(message)

# ========== ФУНКЦИИ, ВЫЗЫВАЕМЫЕ ИЗ ДРУГИХ ОБРАБОТЧИКОВ ==========
async def photo_instruction(message: Message, state: FSMContext):
    await message.answer(
        "📸 **Отправь фото задания**\n\n"
        "Ты можешь сфотографировать любое задание по химии или биологии (из учебника, распечатки или с экрана) и отправить мне.\n"
        "Я распознаю текст с помощью OCR, а затем решу его и объясню решение.\n\n"
        "**Это премиум-функция.** Если у тебя есть подписка, просто отправь фото.",
        parse_mode="Markdown"
    )