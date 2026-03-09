# handlers.py
import asyncio
import logging
import os
import random
import re
import tempfile
from datetime import datetime, timedelta
from collections import Counter
from functools import wraps

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile, LabeledPrice, PreCheckoutQuery
)

from openai import OpenAI
from dotenv import load_dotenv

import database as db
from data import TASKS, VIDEO_LINKS
from elements import ELEMENTS
from keyboards import *
from pdf_generator import generate_pdf
from ocr_helper import ocr_from_photo, download_photo

load_dotenv()
logger = logging.getLogger(__name__)

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
POLZA_API_KEY = os.getenv("POLZA_AI_API_KEY")
ADMIN_IDS = [int(id) for id in os.getenv("ADMIN_IDS", "").split(",") if id]
PREMIUM_PRICE = 300  # Telegram Stars

client = OpenAI(base_url="https://polza.ai/api/v1", api_key=POLZA_API_KEY) if POLZA_API_KEY else None

# ========== СОСТОЯНИЯ FSM ==========
class Form(StatesGroup):
    main = State()
    subject = State()
    theme = State()
    menu = State()
    answering = State()
    free_question = State()
    feedback = State()
    exam_settings = State()
    exam_question = State()
    hint_used = State()
    reminder_set = State()
    generate_task_confirm = State()
    exam_date_input = State()
    level_test = State()
    reaction_query = State()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
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

# ========== ДЕКОРАТОР ДЛЯ ПРОВЕРКИ ПРЕМИУМА ==========
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

# ========== СОЗДАНИЕ РОУТЕРА ==========
router = Router()

# ========== ОБЩИЕ КОМАНДЫ ==========
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = db.get_user(message.from_user.id, message.from_user.username)
    if not user.get('exam_date'):
        welcome_text = (
            f"✨ Репетитор ЕГЭ 2026 ✨\n\n"
            f"Привет, {message.from_user.first_name}! Твой уровень: {user['level']}, опыт: {user['exp']}.\n\n"
            f"📋 Для начала рекомендую пройти тест на определение уровня.\n"
            f"Это поможет мне составить персональный план подготовки.\n"
            f"Нажми кнопку «🎯 Тренировка» → «🧪 Тест на уровень»."
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
    lines = []
    for s in stats:
        percent = (s['correct'] / s['total'] * 100) if s['total'] > 0 else 0
        subject = "Химия" if s['subject'] == "chemistry" else "Биология"
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
async def cmd_level_test(message: Message, state: FSMContext):
    all_tasks = []
    for subject in ["chemistry", "biology"]:
        for theme_id in TASKS[subject].keys():
            all_tasks.extend(db.get_tasks_by_theme(subject, theme_id))
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

# ========== ОБРАБОТЧИКИ КНОПОК ГЛАВНОГО МЕНЮ ==========
@router.message(F.text == "📚 Предметы")
async def choose_subject(message: Message, state: FSMContext):
    await message.answer("Выбери предмет:", reply_markup=kb_subjects())
    await state.set_state(Form.subject)

@router.message(F.text == "🎯 Тренировка")
async def training_menu(message: Message, state: FSMContext):
    await message.answer("Выбери режим тренировки:", reply_markup=kb_training_menu())

@router.message(F.text == "📊 Профиль")
async def profile_menu(message: Message, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Моя статистика", callback_data="my_stats")],
        [InlineKeyboardButton(text="📅 Цель / Напоминание", callback_data="goal_reminder")],
        [InlineKeyboardButton(text="📌 Избранное", callback_data="my_favorites")],
        [InlineKeyboardButton(text="🔮 Прогноз баллов", callback_data="predict_score")],
        [InlineKeyboardButton(text="📉 Анализ слабых тем", callback_data="weak_analysis")],
        [InlineKeyboardButton(text="🌟 Премиум", callback_data="premium")]
    ])
    await message.answer("Твой профиль:", reply_markup=kb)

@router.message(F.text == "ℹ️ Помощь")
async def help_button(message: Message):
    await cmd_help(message)

# ========== ОБРАБОТЧИКИ ДЛЯ КНОПОК МЕНЮ ТРЕНИРОВКИ ==========
@router.callback_query(F.data == "random_task")
async def cb_random_task(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await random_task(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "exam_start")
async def cb_exam_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await exam_start(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "photo_instruction")
async def cb_photo_instruction(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await photo_instruction(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "level_test")
async def cb_level_test(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await cmd_level_test(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "reactions")
async def cb_reactions(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer(
        "⚗️ **Справочник реакций**\n\n"
        "Напиши название реакции, тип или реагенты (например, «горение метана», «нейтрализация», «KMnO4 + H2O2»), и я объясню.\n\n"
        "Или отправь символ элемента (например, Na), и я покажу типичные реакции с ним.",
        parse_mode="Markdown"
    )
    await state.set_state(Form.reaction_query)
    await callback.answer()

@router.callback_query(F.data == "cheatsheets")
async def cb_cheatsheets(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    buttons = []
    for subject, themes in TASKS.items():
        subj_name = "Химия" if subject == "chemistry" else "Биология"
        for theme_id, theme_data in themes.items():
            name = theme_data["name"]
            if len(name) > 35:
                name = name[:35] + "…"
            buttons.append([InlineKeyboardButton(text=f"{subj_name}: {name}", callback_data=f"cheat_{subject}_{theme_id}")])
    buttons.append([InlineKeyboardButton(text="← Назад", callback_data="back_to_training")])
    
    await callback.message.answer(
        "📋 Выбери тему для шпаргалки:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@router.callback_query(F.data == "mendeleev")
async def cb_mendeleev(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer(
        "🧪 **Периодическая таблица Менделеева**\n\nВыбери период (ряд):",
        reply_markup=kb_periods(),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_training")
async def cb_back_to_training(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await training_menu(callback.message, state)
    await callback.answer()

# ========== ФУНКЦИИ, ВЫЗЫВАЕМЫЕ ИЗ CALLBACK-ОБРАБОТЧИКОВ ==========
async def random_task(message: Message, state: FSMContext):
    all_tasks = []
    for subject in ["chemistry", "biology"]:
        for theme_id in TASKS[subject].keys():
            all_tasks.extend(db.get_tasks_by_theme(subject, theme_id))
    if not all_tasks:
        await message.answer("Нет доступных заданий.")
        return
    task = random.choice(all_tasks)
    await message.answer(
        f"🎲 **Случайное задание:**\n\n{task['text']}",
        reply_markup=kb_answers(task, hint_used=False),
        parse_mode="Markdown"
    )
    await state.update_data(
        task=task,
        correct=task["correct"],
        hint_used=False,
        subject=task["subject"],
        theme=task["theme_id"]
    )
    await state.set_state(Form.answering)

async def exam_start(message: Message, state: FSMContext):
    await message.answer("Выбери количество вопросов для варианта:", reply_markup=kb_exam_settings())
    await state.set_state(Form.exam_settings)

async def photo_instruction(message: Message, state: FSMContext):
    await message.answer(
        "📸 **Отправь фото задания**\n\n"
        "Ты можешь сфотографировать любое задание по химии или биологии (из учебника, распечатки или с экрана) и отправить мне.\n"
        "Я распознаю текст с помощью OCR, а затем решу его и объясню решение.\n\n"
        "**Это премиум-функция.** Если у тебя есть подписка, просто отправь фото.",
        parse_mode="Markdown"
    )

# ========== ВЫБОР ПРЕДМЕТА И ТЕМЫ ==========
@router.callback_query(F.data.startswith("subj_"))
async def process_subject(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    subj = callback.data.split("_")[1]
    
    if current_state == Form.exam_settings.state:
        data = await state.get_data()
        count = data.get("exam_count")
        if not count:
            await callback.message.edit_text("Ошибка: не указано количество вопросов. Начните заново.")
            return
        
        all_tasks = []
        for theme_id in TASKS[subj].keys():
            all_tasks.extend(db.get_tasks_by_theme(subj, theme_id))
        
        if len(all_tasks) < count:
            await callback.message.edit_text(
                f"❌ Недостаточно заданий в выбранном предмете. Всего доступно {len(all_tasks)}. Попробуйте меньшее количество."
            )
            return
        
        random.shuffle(all_tasks)
        exam_tasks = all_tasks[:count]
        
        await state.update_data(
            exam_tasks=exam_tasks,
            exam_total=count,
            exam_index=0,
            exam_correct=0,
            exam_mode=True,
            missed_themes=[]
        )
        
        subject_name = "химии" if subj == "chemistry" else "биологии"
        await callback.message.edit_text(
            f"🎯 Экзамен: {count} вопросов по {subject_name}.\n\nГотов начать?",
            reply_markup=kb_exam_confirm(subj)
        )
        await callback.answer()
        return

    await state.update_data(subject=subj)
    await callback.message.delete()
    subj_name = "Химия" if subj == "chemistry" else "Биология"
    await callback.message.answer(
        f"Предмет: **{subj_name}** 🧠\nВыбери тему:", 
        reply_markup=kb_themes(subj), 
        parse_mode="Markdown"
    )
    await state.set_state(Form.theme)
    await callback.answer()

@router.callback_query(F.data.startswith("back_to_themes_"))
async def back_to_themes(callback: CallbackQuery, state: FSMContext):
    subj = callback.data.split("_")[3]
    await callback.message.delete()
    subj_name = "Химия" if subj == "chemistry" else "Биология"
    await callback.message.answer(
        f"Предмет: **{subj_name}** 🧠\nВыбери тему:", 
        reply_markup=kb_themes(subj), 
        parse_mode="Markdown"
    )
    await state.set_state(Form.theme)
    await callback.answer()

@router.callback_query(F.data.startswith("theme_"))
async def process_theme(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    subj = parts[1]
    tid = parts[2]
    td = TASKS.get(subj, {}).get(tid, {})
    if not td:
        await callback.message.answer("Тема не найдена")
        return
    await callback.message.delete()
    await callback.message.answer(
        f"**Тема:** {td['name']}\n\nЧто хочешь сделать?", 
        reply_markup=kb_theme_menu(callback.from_user.id, subj, tid), 
        parse_mode="Markdown"
    )
    await state.update_data(subject=subj, theme=tid)
    await state.set_state(Form.menu)
    await callback.answer()

# ========== КОНСПЕКТЫ (КРАТКИЕ) ==========
@router.callback_query(F.data.startswith("cons_"))
async def show_conspect(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    subj = parts[1]
    tid = parts[2]
    td = TASKS.get(subj, {}).get(tid, {})
    if not td:
        await callback.message.answer("Тема не найдена")
        return
    await callback.message.delete()
    subj_name = "Химии" if subj == "chemistry" else "Биологии"
    theory_prompt = (
        f"Напиши понятный конспект для ЕГЭ 2026 по предмету {subj_name} на тему '{td['name']}'. "
        "Пиши простым школьным языком, без воды, без эмодзи, без выделений жирным/курсивом. "
        "Объём 300–500 слов. Не используй Markdown."
    )
    theory = await ai_text(theory_prompt)
    await callback.message.answer(f"**Конспект: {td['name']}**\n\n{theory}", parse_mode="Markdown")
    videos = get_video_links(subj, tid)
    if videos:
        await callback.message.answer("🎥 Полезные видео по теме (на русском):")
        for video in videos:
            if " — " in video:
                parts = video.split(" — ", 1)
                await callback.message.answer(f"• [{parts[1]}]({parts[0]})", parse_mode="Markdown")
            else:
                await callback.message.answer(f"• {video}")
    await callback.message.answer(
        "Что дальше?", 
        reply_markup=kb_theme_menu(callback.from_user.id, subj, tid)
    )
    await callback.answer()

# ========== PDF-КОНСПЕКТЫ (ПРЕМИУМ) ==========
@router.callback_query(F.data.startswith("pdf_"))
@premium_required
async def show_pdf_conspect(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    subj = parts[1]
    tid = parts[2]
    td = TASKS.get(subj, {}).get(tid, {})
    if not td:
        await callback.message.answer("Тема не найдена")
        return
    
    await callback.message.edit_text("⏳ Генерирую расширенный конспект в PDF... Это может занять до минуты.")
    
    subj_name = "Химии" if subj == "chemistry" else "Биологии"
    prompt = (
        f"Напиши подробный расширенный конспект для ЕГЭ 2026 по предмету {subj_name} на тему '{td['name']}'. "
        f"Включи все ключевые определения, формулы, примеры, а также типичные ошибки. "
        f"Объём: 1000–1500 слов. Пиши понятным языком, структурируй текст с помощью заголовков и списков. "
        f"Не используй Markdown, только обычный текст."
    )
    content = await ai_text(prompt, max_tokens=2000)
    
    try:
        pdf_path = generate_pdf(td['name'], content)
    except Exception as e:
        logger.error(f"Ошибка генерации PDF: {e}")
        await callback.message.delete()
        await callback.message.answer(
            "❌ Не удалось создать PDF. Возможно, отсутствуют шрифты для кириллицы.\n"
            "Пожалуйста, скачайте шрифты DejaVu и поместите их в папку 'fonts' проекта.\n"
            "Подробности: https://github.com/dompdf/utils/tree/master/fonts"
        )
        await callback.message.answer(
            "Что дальше?",
            reply_markup=kb_theme_menu(callback.from_user.id, subj, tid)
        )
        await callback.answer()
        return
    
    await callback.message.delete()
    await callback.message.answer_document(
        FSInputFile(pdf_path),
        caption=f"📕 **Расширенный конспект:** {td['name']}",
        parse_mode="Markdown"
    )
    
    try:
        os.remove(pdf_path)
    except:
        pass
    
    await callback.message.answer(
        "Что дальше?",
        reply_markup=kb_theme_menu(callback.from_user.id, subj, tid)
    )
    await callback.answer()

# ========== ТЕСТОВЫЕ ЗАДАНИЯ ==========
@router.callback_query(F.data.startswith("test_"))
async def show_test(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    subj = parts[1]
    tid = parts[2]
    tasks = db.get_tasks_by_theme(subj, tid)
    if not tasks:
        await callback.message.answer("В этой теме пока нет заданий")
        return
    await callback.message.delete()
    task = random.choice(tasks)
    await callback.message.answer(
        f"🔍 **Задание:** {task['text']}\n\nВыбери ответ:", 
        reply_markup=kb_answers(task, hint_used=False), 
        parse_mode="Markdown"
    )
    await state.update_data(subject=subj, theme=tid, task=task, correct=task["correct"], hint_used=False)
    await state.set_state(Form.answering)
    await callback.answer()

# ========== ПОДСКАЗКИ ==========
@router.callback_query(F.data.startswith("hint_"))
async def give_hint(callback: CallbackQuery, state: FSMContext):
    task_id = callback.data.split("_")[1]
    data = await state.get_data()
    task = data.get("task")
    if not task or task['id'] != task_id:
        await callback.answer("Задание устарело, попробуй заново.")
        return
    await callback.message.edit_text("💡 Генерирую подсказку...")
    prompt = f"Дай краткую подсказку (1-2 предложения) к заданию ЕГЭ: {task['text']}. Не давай полный ответ."
    hint = await ai_text(prompt, max_tokens=100)
    await state.update_data(hint_used=True)
    await callback.message.edit_text(
        f"🔍 **Задание:** {task['text']}\n\n💡 **Подсказка:** {hint}\n\nВыбери ответ:",
        reply_markup=kb_answers(task, hint_used=True),
        parse_mode="Markdown"
    )
    await callback.answer()

# ========== ПРОВЕРКА ОТВЕТА ==========
@router.callback_query(F.data.startswith("ans_"))
async def check_answer(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    task_id = parts[1]
    let = parts[2]
    data = await state.get_data()
    task = data.get("task")
    correct = data.get("correct")
    subj = data.get("subject")
    theme_id = data.get("theme")
    hint_used = data.get("hint_used", False)
    from_exam = data.get("exam_mode", False)

    if not task or not correct:
        await callback.message.answer("Ошибка данных. Выбери тему заново.")
        await state.clear()
        await callback.answer()
        return

    is_correct = (let == correct)
    if from_exam:
        if not is_correct:
            missed_themes = data.get("missed_themes", [])
            missed_themes.append(theme_id)
            await state.update_data(missed_themes=missed_themes)
    else:
        db.update_user_stats(callback.from_user.id, correct=is_correct)
        db.update_daily(callback.from_user.id)
        db.update_theme_stats(callback.from_user.id, subj, theme_id, is_correct)

    await callback.message.delete()

    if len(correct) == 1:
        correct_answer = f"{correct}) {task['options'][ord(correct) - ord(task['letters'][0])]}"
    else:
        correct_options = []
        for ch in correct:
            if ch in task['letters']:
                idx = task['letters'].index(ch)
                correct_options.append(f"{ch}) {task['options'][idx]}")
            else:
                correct_options.append(f"{ch}?")
        correct_answer = ", ".join(correct_options)

    if is_correct:
        if hint_used:
            reply = "🎉 Правильно (с подсказкой)! Опыт: +5"
        else:
            reply = "🎉 Правильно! Опыт: +10"
    else:
        reply = f"❌ Неправильно. Правильный ответ: {correct_answer}"

    if not from_exam:
        subj_name = "химии" if subj == "chemistry" else "биологии"
        expl_prompt = (
            f"Разбор ошибки ЕГЭ по {subj_name}. Задание: {task['text']}. "
            f"Ответ ученика: {let}. Правильный ответ: {correct}. "
            "Пиши просто, понятно, без Markdown."
        )
        expl = await ai_text(expl_prompt)
        await callback.message.answer(f"{reply}\n\n{expl}", parse_mode="Markdown")
    else:
        await callback.message.answer(reply, parse_mode="Markdown")

    if from_exam:
        exam_index = data.get("exam_index", 0) + 1
        exam_total = data.get("exam_total")
        exam_correct = data.get("exam_correct", 0) + (1 if is_correct else 0)
        await state.update_data(exam_index=exam_index, exam_correct=exam_correct)
        if exam_index < exam_total:
            exam_tasks = data.get("exam_tasks")
            next_task = exam_tasks[exam_index]
            await state.update_data(task=next_task, correct=next_task["correct"], hint_used=False)
            await callback.message.answer(
                f"📝 Вопрос {exam_index+1}/{exam_total}:\n\n{next_task['text']}",
                reply_markup=kb_answers(next_task, hint_used=False),
                parse_mode="Markdown"
            )
        else:
            percent = (exam_correct / exam_total * 100)
            predicted_score = round(percent)
            missed_themes = data.get("missed_themes", [])
            weak_analysis = ""
            if missed_themes:
                theme_counter = Counter(missed_themes)
                weak_list = []
                for theme_id, count in theme_counter.most_common(3):
                    theme_name = None
                    for subj, themes in TASKS.items():
                        if theme_id in themes:
                            theme_name = themes[theme_id]['name']
                            break
                    if theme_name:
                        weak_list.append(f"• {theme_name} – ошибок: {count}")
                if weak_list:
                    weak_analysis = "\n\n📉 **Слабые темы:**\n" + "\n".join(weak_list)
            await callback.message.answer(
                f"🏁 **Вариант завершён!**\n\n"
                f"Правильных ответов: {exam_correct}/{exam_total} ({percent:.0f}%)\n"
                f"🔮 Прогнозируемый балл ЕГЭ: {predicted_score}\n"
                f"{weak_analysis}\n\n"
                f"Ты получил(а) {exam_correct*10} опыта.",
                reply_markup=kb_main()
            )
            for _ in range(exam_correct):
                db.update_user_stats(callback.from_user.id, correct=True)
            await state.clear()
    else:
        user = db.get_user(callback.from_user.id)
        daily_count, daily_goal = db.get_daily_goal(callback.from_user.id)
        await callback.message.answer(
            f"📊 Уровень: {user['level']} | Опыт: {user['exp']}\n"
            f"📅 Ежедневная цель: {daily_count}/{daily_goal}",
            reply_markup=kb_after_answer(subj, theme_id)
        )
        await state.update_data(task=None, correct=None)
        await state.set_state(Form.menu)

    await callback.answer()

# ========== ИЗБРАННОЕ ==========
@router.callback_query(F.data.startswith("fav_"))
async def toggle_favorite(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    subj = parts[1]
    tid = parts[2]
    user_id = callback.from_user.id
    if db.is_favorite(user_id, subj, tid):
        db.remove_favorite(user_id, subj, tid)
        await callback.answer("⭐ Удалено из избранного")
    else:
        db.add_favorite(user_id, subj, tid)
        await callback.answer("⭐ Добавлено в избранное")
    await callback.message.edit_reply_markup(reply_markup=kb_theme_menu(user_id, subj, tid))

# ========== ГЕНЕРАЦИЯ ЗАДАНИЙ (ПРЕМИУМ) ==========
@router.callback_query(F.data.startswith("gen_"))
@premium_required
async def generate_task_prompt(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    subj = parts[1]
    tid = parts[2]
    theme_name = TASKS.get(subj, {}).get(tid, {}).get("name", tid)
    
    await callback.message.edit_text(
        f"✨ **Генерация задания**\n\n"
        f"Тема: {theme_name}\n"
        f"Бот создаст новое задание с помощью ИИ. Оно будет добавлено в базу и сразу показано тебе.\n\n"
        f"Продолжить?",
        reply_markup=kb_generate_confirm(subj, tid)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("generate_yes_"))
async def generate_task(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    subj = parts[2]
    tid = parts[3]
    
    theme_data = TASKS.get(subj, {}).get(tid, {})
    theme_name = theme_data.get("name", tid)
    subject_name = "химии" if subj == "chemistry" else "биологии"
    
    await callback.message.edit_text("⏳ Генерирую задание... Это займёт несколько секунд.")
    
    prompt = (
        f"Создай задание в стиле ЕГЭ по {subject_name} на тему '{theme_name}'. "
        f"Формат: вопрос и 4 варианта ответа, обозначенных буквами A, B, C, D. "
        f"Укажи правильный ответ буквой. "
        f"Пример:\n\n"
        f"Вопрос: Какой элемент имеет электронную конфигурацию 1s²2s²2p⁶3s²3p³?\n"
        f"A) Si\nB) P\nC) S\nD) Cl\n\n"
        f"Правильный ответ: B\n\n"
        f"Теперь создай своё уникальное задание. Не используй Markdown, просто текст."
    )
    
    generated = await ai_text(prompt, max_tokens=500)
    
    lines = generated.strip().split('\n')
    question = ""
    options = []
    correct = ""
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.match(r'^[A-D]\)', line):
            option_text = line[2:].strip()
            options.append(option_text)
        elif re.match(r'^[Пп]равильный ответ:\s*([A-D])', line):
            match = re.match(r'^[Пп]равильный ответ:\s*([A-D])', line)
            if match:
                correct = match.group(1)
        elif not question:
            question = line
    
    if len(options) != 4:
        options = []
        for line in lines:
            if re.match(r'^[A-D]\)', line.strip()):
                options.append(line[2:].strip())
        while len(options) < 4:
            options.append(f"Вариант {len(options)+1}")
    
    if not correct:
        correct = "A"
    if not question:
        question = generated[:200]
    
    task_id = f"gen_{subj}_{tid}_{int(datetime.now().timestamp())}"
    
    db.add_task(
        task_id=task_id,
        subject=subj,
        theme_id=tid,
        text=question,
        options=options[:4],
        correct=correct,
        letters="ABCD"
    )
    
    task = {
        "id": task_id,
        "subject": subj,
        "theme_id": tid,
        "text": question,
        "options": options[:4],
        "correct": correct,
        "letters": "ABCD"
    }
    
    await callback.message.delete()
    await callback.message.answer(
        f"✨ **Сгенерированное задание:**\n\n{question}",
        reply_markup=kb_answers(task, hint_used=False),
        parse_mode="Markdown"
    )
    await state.update_data(
        task=task,
        correct=correct,
        hint_used=False,
        subject=subj,
        theme=tid
    )
    await state.set_state(Form.answering)
    await callback.answer()

# ========== ЭКЗАМЕН: ВЫБОР КОЛИЧЕСТВА ==========
@router.callback_query(F.data.startswith("exam_") and F.data[5].isdigit())
async def exam_select_count(callback: CallbackQuery, state: FSMContext):
    count = int(callback.data.split("_")[1])
    await state.update_data(exam_count=count)
    await callback.message.edit_text("Выбери предмет для экзамена:", reply_markup=kb_subjects())
    await state.set_state(Form.exam_settings)

@router.callback_query(F.data.startswith("exam_start_"))
async def exam_start_confirmed(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    exam_tasks = data.get("exam_tasks")
    if not exam_tasks:
        await callback.message.edit_text("Ошибка подготовки экзамена. Начни заново.")
        return
    first_task = exam_tasks[0]
    await state.update_data(task=first_task, correct=first_task["correct"], hint_used=False)
    await callback.message.delete()
    await callback.message.answer(
        f"📝 Вопрос 1/{data['exam_total']}:\n\n{first_task['text']}",
        reply_markup=kb_answers(first_task, hint_used=False),
        parse_mode="Markdown"
    )
    await state.set_state(Form.answering)
    await callback.answer()

@router.callback_query(F.data == "exam_cancel")
async def exam_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer("Экзамен отменён.", reply_markup=kb_main())
    await state.clear()
    await callback.answer()

# ========== ТЕСТ НА УРОВЕНЬ ==========
@router.callback_query(Form.level_test, F.data.startswith("ans_"))
async def level_test_answer(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    tasks = data.get("level_test_tasks")
    index = data.get("level_test_index", 0)
    correct_count = data.get("level_test_correct", 0)
    
    if not tasks or index >= len(tasks):
        await callback.message.delete()
        await callback.message.answer(
            "❌ Ошибка: данные теста утеряны. Пожалуйста, начните тест заново командой /level_test.",
            reply_markup=kb_main()
        )
        await state.clear()
        await callback.answer()
        return
    
    let = callback.data.split("_")[2]
    task = tasks[index]
    is_correct = (let == task["correct"])
    if is_correct:
        correct_count += 1
    
    await callback.message.delete()
    
    if is_correct:
        await callback.message.answer("✅ Верно!")
    else:
        if len(task["correct"]) == 1:
            correct_idx = ord(task["correct"]) - ord(task["letters"][0])
            correct_answer = f"{task['correct']}) {task['options'][correct_idx]}"
        else:
            correct_answer = task["correct"]
        await callback.message.answer(f"❌ Неверно. Правильный ответ: {correct_answer}")
    
    index += 1
    if index < len(tasks):
        await state.update_data(level_test_index=index, level_test_correct=correct_count)
        next_task = tasks[index]
        await callback.message.answer(
            f"Вопрос {index+1} из {len(tasks)}:\n{next_task['text']}",
            reply_markup=kb_answers(next_task, hint_used=False),
            parse_mode="Markdown"
        )
    else:
        percent = (correct_count / len(tasks)) * 100
        if percent < 40:
            level = "beginner"
            level_text = "Начальный"
            plan = "Рекомендуется начать с основных тем: строение атома, химическая связь, базовые понятия биологии."
        elif percent < 70:
            level = "intermediate"
            level_text = "Средний"
            plan = "Хороший уровень. Рекомендуется углублённое изучение тем, где были ошибки, и решение большего количества заданий."
        else:
            level = "advanced"
            level_text = "Продвинутый"
            plan = "Отличный результат! Сосредоточься на сложных темах и решении вариантов ЕГЭ целиком."
        
        db.set_user_level(callback.from_user.id, level)
        
        await callback.message.answer(
            f"🏁 **Тест завершён!**\n\n"
            f"Правильных ответов: {correct_count} из {len(tasks)} ({percent:.0f}%)\n"
            f"Твой уровень: {level_text}\n\n"
            f"**Персональный план подготовки:**\n{plan}\n\n"
            f"Теперь укажи дату твоего экзамена (в формате ДД.ММ.ГГГГ), чтобы я мог рассчитать оставшееся время.",
            parse_mode="Markdown"
        )
        await state.set_state(Form.exam_date_input)
    
    await callback.answer()

@router.message(Form.exam_date_input)
async def process_exam_date(message: Message, state: FSMContext):
    date_str = message.text.strip()
    if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', date_str):
        await message.answer("Неверный формат. Пожалуйста, введи дату в формате ДД.ММ.ГГГГ (например, 30.05.2026).")
        return
    db.set_exam_date(message.from_user.id, date_str)
    await message.answer(
        f"✅ Дата экзамена сохранена: {date_str}\n"
        f"Я буду учитывать её при составлении рекомендаций. Удачи в подготовке!",
        reply_markup=kb_main()
    )
    await state.clear()

# ========== ЦЕЛЬ И НАПОМИНАНИЯ (ИНЛАЙН) ==========
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

# ========== ТАБЛИЦА МЕНДЕЛЕЕВА ==========
@router.callback_query(F.data.startswith("period_"))
async def cb_period(callback: CallbackQuery, state: FSMContext):
    period = int(callback.data.split("_")[1])
    await callback.message.delete()
    await callback.message.answer(
        f"🧪 **{period} период**\n\nНажми на символ элемента, чтобы узнать подробности:",
        reply_markup=kb_elements_for_period(period),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("element_"))
async def cb_element(callback: CallbackQuery, state: FSMContext):
    symbol = callback.data.split("_")[1]
    element = ELEMENTS.get(symbol)
    if not element:
        await callback.message.answer("Элемент не найден")
        return
    
    text = (
        f"🧪 **{element['name']} ({symbol})**\n"
        f"• Атомный номер: {element['number']}\n"
        f"• Атомная масса: {element['mass']}\n"
        f"• Группа: {element['group']}\n"
        f"• Период: {element['period']}\n"
        f"• Электронная конфигурация: `{element['config']}`"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Найти в реакциях", callback_data=f"find_reaction_{symbol}")],
        [InlineKeyboardButton(text="← Назад к периоду", callback_data=f"period_{element['period']}")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")]
    ])
    
    await callback.message.delete()
    await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def cb_back_to_main(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer("Главное меню:", reply_markup=kb_main())
    await state.clear()
    await callback.answer()

# ========== СПРАВОЧНИК РЕАКЦИЙ ==========
@router.message(Form.reaction_query)
async def handle_reaction_query(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await message.answer("Возвращаемся в меню.", reply_markup=kb_main())
        await state.clear()
        return
    
    await message.answer("⏳ Ищу информацию...")
    
    symbol = message.text.strip().capitalize()
    if symbol in ELEMENTS:
        element = ELEMENTS[symbol]
        prompt = (
            f"Опиши химический элемент {element['name']} ({symbol}) для ЕГЭ. "
            f"Укажи его положение в таблице, основные химические свойства, "
            f"типичные реакции (с кем реагирует, продукты), применение. "
            f"Если есть особые факты, добавь их."
        )
    else:
        prompt = (
            f"Ты – справочник химических реакций для ЕГЭ. Пользователь спрашивает: '{message.text}'. "
            f"Опиши эту реакцию (если она существует), приведи уравнение, условия протекания, признаки и применение. "
            f"Если запрос не связан с реакцией, скажи, что это не найдено, и предложи уточнить."
        )
    
    answer = await ai_text(prompt, max_tokens=1000)
    await message.answer(answer, reply_markup=kb_main())
    await state.clear()

@router.callback_query(F.data.startswith("find_reaction_"))
async def find_reaction_from_element(callback: CallbackQuery, state: FSMContext):
    symbol = callback.data.split("_")[2]
    element = ELEMENTS.get(symbol)
    if not element:
        await callback.answer("Элемент не найден")
        return
    await callback.message.delete()
    await callback.message.answer(
        f"⚗️ **Реакции с участием {element['name']} ({symbol})**\n\n"
        f"Напиши конкретный запрос, например: «{symbol} + O2» или «реакции {element['name']} с водой».",
        parse_mode="Markdown"
    )
    await state.set_state(Form.reaction_query)
    await callback.answer()

# ========== ШПАРГАЛКИ ==========
@router.callback_query(F.data.startswith("cheat_"))
async def show_cheatsheet(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    subj = parts[1]
    tid = parts[2]
    theme_data = TASKS[subj][tid]
    
    await callback.message.edit_text("⏳ Генерирую шпаргалку...")
    
    prompt = (
        f"Составь краткую шпаргалку по теме '{theme_data['name']}' для ЕГЭ. "
        f"Выдели самое главное: определения, формулы, ключевые факты. "
        f"Объём: 10-15 предложений. Без Markdown."
    )
    cheatsheet = await ai_text(prompt, max_tokens=800)
    
    await callback.message.delete()
    await callback.message.answer(
        f"📋 **Шпаргалка: {theme_data['name']}**\n\n{cheatsheet}",
        parse_mode="Markdown"
    )
    await callback.answer()

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

# ========== ПЛАТЕЖИ (TELEGRAM STARS) ==========
@router.callback_query(F.data == "premium")
async def show_premium_menu(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    
    user_id = callback.from_user.id
    has_premium = db.has_premium(user_id)
    sub_info = db.get_subscription(user_id)
    
    text = "🌟 **Премиум-доступ** 🌟\n\n"
    
    if has_premium:
        text += f"✅ У вас уже есть активная подписка до {sub_info['expires_at']}\n\n"
        text += "Хотите продлить?"
    else:
        text += (
            "С премиумом ты получаешь:\n"
            "✅ Полный доступ ко всем темам\n"
            "✅ Неограниченное количество заданий\n"
            "✅ PDF-конспекты\n"
            "✅ Генерацию заданий через ИИ\n"
            "✅ Анализ заданий по фото\n"
            "✅ Приоритетную поддержку\n\n"
        )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Купить на месяц ({PREMIUM_PRICE} ⭐)", callback_data="buy_premium_month")],
        [InlineKeyboardButton(text="← Назад в профиль", callback_data="back_to_profile")]
    ])
    
    await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "buy_premium_month")
async def buy_premium_month(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    
    prices = [LabeledPrice(label="Премиум на 1 месяц", amount=PREMIUM_PRICE)]
    
    await callback.message.answer_invoice(
        title="🌟 Премиум-доступ на 1 месяц",
        description="Полный доступ ко всем функциям бота на 30 дней",
        payload="premium_month",
        provider_token="",
        currency="XTR",
        prices=prices,
        start_parameter="premium_month",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"Оплатить {PREMIUM_PRICE} ⭐", pay=True)],
            [InlineKeyboardButton(text="← Отмена", callback_data="premium")]
        ])
    )
    await callback.answer()

@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_q: PreCheckoutQuery):
    await pre_checkout_q.answer(ok=True)

@router.message(F.successful_payment)
async def successful_payment(message: Message):
    user_id = message.from_user.id
    payment = message.successful_payment
    payload = payment.invoice_payload
    
    if payload != "premium_month":
        return
    
    expires = (datetime.now() + timedelta(days=30)).date()
    db.set_subscription(user_id, "premium", expires.isoformat())
    
    await message.answer(
        "✅ **Оплата прошла успешно!**\n\n"
        f"Премиум-доступ активирован до {expires.strftime('%d.%m.%Y')}.\n"
        "Спасибо за поддержку проекта! 🌟",
        parse_mode="Markdown"
    )
    
    if ADMIN_IDS:
        for admin_id in ADMIN_IDS:
            try:
                await message.bot.send_message(
                    admin_id,
                    f"💰 Новый платёж!\n"
                    f"Пользователь: @{message.from_user.username} (ID: {user_id})\n"
                    f"Сумма: {payment.total_amount} ⭐\n"
                    f"Действует до: {expires.strftime('%d.%m.%Y')}"
                )
            except:
                pass

@router.callback_query(F.data == "back_to_profile")
async def back_to_profile(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer("Твой профиль:", reply_markup=kb_profile_menu())
    await callback.answer()

# ========== АДМИНСКИЕ КОМАНДЫ ==========
@router.message(Command("givepremium"))
async def cmd_give_premium(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет прав на выполнение этой команды.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "❌ Использование: /givepremium <user_id> [дней]\n"
            "Пример: /givepremium 123456789 30"
        )
        return

    try:
        target_id = int(args[1])
        days = 30
        if len(args) >= 3:
            days = int(args[2])
            if days <= 0:
                raise ValueError
    except ValueError:
        await message.answer("❌ Неверный формат. Укажите корректный user_id и количество дней (целое положительное число).")
        return

    user_data = db.get_user(target_id)
    expires = (datetime.now() + timedelta(days=days)).date()
    db.set_subscription(target_id, "premium", expires.isoformat())

    await message.answer(
        f"✅ Премиум выдан пользователю {target_id} на {days} дн. (до {expires.strftime('%d.%m.%Y')})"
    )

    try:
        await message.bot.send_message(
            target_id,
            f"🎉 Вам выдан премиум-доступ на {days} дн. (до {expires.strftime('%d.%m.%Y')})\n"
            "Спасибо за использование бота!"
        )
    except:
        pass

@router.message(Command("removepremium"))
async def cmd_remove_premium(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет прав на выполнение этой команды.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /removepremium <user_id>")
        return

    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("❌ Неверный формат user_id.")
        return

    db.set_subscription(target_id, "free", None)
    await message.answer(f"✅ Премиум отключён у пользователя {target_id}.")

    try:
        await message.bot.send_message(
            target_id,
            "🔕 Ваш премиум-доступ был отключён администратором."
        )
    except:
        pass

@router.message(Command("checkpremium"))
async def cmd_check_premium(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет прав на выполнение этой команды.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /checkpremium <user_id>")
        return

    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("❌ Неверный формат user_id.")
        return

    sub = db.get_subscription(target_id)
    if sub["type"] == "premium" and sub["expires_at"]:
        expires = datetime.strptime(sub["expires_at"], "%Y-%m-%d").date()
        if expires >= datetime.now().date():
            status = f"✅ Активна до {expires.strftime('%d.%m.%Y')}"
        else:
            status = f"❌ Истекла {expires.strftime('%d.%m.%Y')}"
    elif sub["type"] == "premium":
        status = "✅ Активна (бессрочно?)"
    else:
        status = "⛔ Нет премиума"

    await message.answer(f"Статус пользователя {target_id}: {status}")

# ========== ОБРАБОТЧИК ФОТО (ПРЕМИУМ) ==========
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

# ========== ОБРАБОТЧИК НЕИЗВЕСТНЫХ СООБЩЕНИЙ ==========
@router.message()
async def unknown_message(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state in (Form.answering.state, Form.exam_question.state):
        await message.answer("⚠️ Сейчас ты отвечаешь на задание. Пожалуйста, выбери ответ, используя кнопки.")
    elif current_state in (Form.feedback.state, Form.reminder_set.state, Form.free_question.state, Form.exam_date_input.state, Form.reaction_query.state):
        await message.answer("✏️ Пожалуйста, следуй инструкциям или нажми «❌ Отмена».", reply_markup=kb_cancel())
    else:
        await message.answer("🤔 Я не понимаю эту команду. Используй кнопки или /help.", reply_markup=kb_main())
