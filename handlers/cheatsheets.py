# handlers/cheatsheets.py
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from data import TASKS
from .utils import ai_text

router = Router()

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

@router.callback_query(F.data.startswith("subj_cheat_"))
async def subj_cheatsheets(callback: CallbackQuery, state: FSMContext):
    subj = callback.data.split("_")[2]
    # Пока просто вызываем общие шпаргалки, но можно модифицировать под предмет
    await cb_cheatsheets(callback, state)

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