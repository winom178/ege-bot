# handlers/tasks.py
import random
import re
import os
from datetime import datetime
from collections import Counter
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext

import database as db
from data import TASKS
from keyboards import (
    kb_answers, kb_after_answer, kb_theme_menu, kb_generate_confirm,
    kb_main
)
from .states import Form
from .utils import ai_text, get_video_links, subject_premium_required
from pdf_generator import generate_pdf

router = Router()

# ========== КОНСПЕКТЫ ==========
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

# ========== PDF-КОНСПЕКТЫ (ПРЕМИУМ) ==========
@router.callback_query(F.data.startswith("pdf_"))
@subject_premium_required
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
        await callback.message.delete()
        await callback.message.answer(
            "❌ Не удалось создать PDF. Возможно, отсутствуют шрифты для кириллицы.\n"
            "Пожалуйста, скачайте шрифты DejaVu и поместите их в папку 'fonts' проекта."
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

# ========== ГЕНЕРАЦИЯ ЗАДАНИЙ (ПРЕМИУМ) ==========
@router.callback_query(F.data.startswith("gen_"))
@subject_premium_required
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

# ========== ОБРАБОТЧИКИ ДЛЯ КНОПОК МЕНЮ ТРЕНИРОВКИ ==========
@router.callback_query(F.data == "random_task")
async def cb_random_task(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await random_task(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "photo_instruction")
async def cb_photo_instruction(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await photo_instruction(callback.message, state)
    await callback.answer()

# ========== НОВЫЕ ОБРАБОТЧИКИ ДЛЯ ПРЕДМЕТНОГО МЕНЮ ==========
@router.callback_query(F.data.startswith("subj_random_"))
async def subj_random_task(callback: CallbackQuery, state: FSMContext):
    subj = callback.data.split("_")[2]
    await callback.message.delete()
    await random_task_for_subject(callback.message, state, subj)

async def random_task_for_subject(message: Message, state: FSMContext, subject: str):
    all_tasks = []
    for theme_id in TASKS[subject].keys():
        all_tasks.extend(db.get_tasks_by_theme(subject, theme_id))
    if not all_tasks:
        await message.answer("Нет доступных заданий по этому предмету.")
        return
    task = random.choice(all_tasks)
    await message.answer(
        f"🎲 **Случайное задание по {subject}:**\n\n{task['text']}",
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

# ========== ФУНКЦИИ, ВЫЗЫВАЕМЫЕ ИЗ ДРУГИХ ОБРАБОТЧИКОВ ==========
async def random_task(message: Message, state: FSMContext):
    all_tasks = []
    for subject in TASKS.keys():
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

async def photo_instruction(message: Message, state: FSMContext):
    await message.answer(
        "📸 **Отправь фото задания**\n\n"
        "Ты можешь сфотографировать любое задание по химии или биологии (из учебника, распечатки или с экрана) и отправить мне.\n"
        "Я распознаю текст с помощью OCR, а затем решу его и объясню решение.\n\n"
        "**Это премиум-функция.** Если у тебя есть подписка, просто отправь фото.",
        parse_mode="Markdown"
    )