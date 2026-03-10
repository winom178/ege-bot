# handlers/exam.py
import random
import re
from datetime import datetime, timedelta
from collections import Counter
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import database as db
from data import TASKS
from keyboards import (
    kb_exam_settings, kb_exam_confirm, kb_subjects,
    kb_answers, kb_main, kb_profile_menu
)
from .states import Form
from .utils import ai_text

router = Router()

async def process_exam_subject(callback: CallbackQuery, state: FSMContext, subj: str):
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

@router.callback_query(F.data == "exam_start")
async def cb_exam_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await exam_start(callback.message, state)
    await callback.answer()

async def exam_start(message: Message, state: FSMContext):
    await message.answer("Выбери количество вопросов для варианта:", reply_markup=kb_exam_settings())
    await state.set_state(Form.exam_settings)

@router.callback_query(F.data.startswith("exam_") and F.data[5].isdigit())
async def exam_select_count(callback: CallbackQuery, state: FSMContext):
    count = int(callback.data.split("_")[1])
    await state.update_data(exam_count=count)
    data = await state.get_data()
    subject = data.get("subject")
    if subject:
        # Если предмет уже выбран, переходим сразу к подтверждению
        await process_exam_subject(callback, state, subject)
    else:
        # Иначе предлагаем выбрать предмет
        await callback.message.edit_text("Выбери предмет для экзамена:", reply_markup=kb_subjects())
        await state.set_state(Form.exam_settings)

@router.callback_query(F.data.startswith("subj_exam_"))
async def subj_exam_start(callback: CallbackQuery, state: FSMContext):
    subj = callback.data.split("_")[2]
    await state.update_data(subject=subj)
    await callback.message.delete()
    await exam_start(callback.message, state)

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
@router.callback_query(F.data == "level_test")
async def cb_level_test(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await cmd_level_test(callback.message, state)
    await callback.answer()

# (cmd_level_test уже в common.py, но здесь мы импортируем её, если нужно)
# Однако чтобы избежать циклического импорта, лучше оставить её в common.py,
# а здесь использовать только вызов через callback.

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

# ========== ПРОГНОЗ БАЛЛОВ ==========
@router.callback_query(F.data == "predict_score")
async def cb_predict_score(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer(
        "🔮 **Прогноз баллов ЕГЭ**\n\n"
        "После прохождения варианта ты получишь прогноз на основе твоих результатов.\n"
        "Пока нет данных. Пройди вариант в разделе «Тренировка»."
    )
    await callback.answer()

# ========== АНАЛИЗ СЛАБЫХ ТЕМ ==========
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