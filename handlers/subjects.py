# handlers/subjects.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import database as db
from data import TASKS
from keyboards import kb_subjects, kb_subject_menu, kb_themes, kb_theme_menu
from .states import Form

router = Router()

@router.message(F.text == "📚 Предметы")
async def choose_subject(message: Message, state: FSMContext):
    await message.answer("Выбери предмет:", reply_markup=kb_subjects())
    await state.set_state(Form.subject)

@router.callback_query(F.data.startswith("subj_") & ~F.data.startswith("subj_random_") & ~F.data.startswith("subj_exam_") & ~F.data.startswith("subj_photo_") & ~F.data.startswith("subj_level_") & ~F.data.startswith("subj_cheat_") & ~F.data.startswith("subj_themes_") & ~F.data.startswith("subj_reactions_") & ~F.data.startswith("subj_mendeleev_"))
async def process_subject(callback: CallbackQuery, state: FSMContext):
    subj = callback.data.split("_")[1]
    await state.update_data(subject=subj)
    await callback.message.delete()
    
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
    }.get(subj, subj.capitalize())
    
    await callback.message.answer(
        f"🧪 **{display_name}**\n\nВыбери действие:",
        reply_markup=kb_subject_menu(subj),
        parse_mode="Markdown"
    )
    await state.set_state(Form.subject_menu)
    await callback.answer()

@router.callback_query(F.data.startswith("subj_themes_"))
async def go_to_themes(callback: CallbackQuery, state: FSMContext):
    subj = callback.data.split("_")[2]
    await state.update_data(subject=subj)
    await callback.message.delete()
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
    }.get(subj, subj.capitalize())
    await callback.message.answer(
        f"Предмет: **{display_name}** 🧠\nВыбери тему:", 
        reply_markup=kb_themes(subj), 
        parse_mode="Markdown"
    )
    await state.set_state(Form.theme)
    await callback.answer()

@router.callback_query(F.data.startswith("back_to_themes_"))
async def back_to_themes(callback: CallbackQuery, state: FSMContext):
    subj = callback.data.split("_")[3]
    await callback.message.delete()
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
    }.get(subj, subj.capitalize())
    await callback.message.answer(
        f"Предмет: **{display_name}** 🧠\nВыбери тему:", 
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