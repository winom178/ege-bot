# handlers/elements.py
import os
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, URLInputFile
from aiogram.fsm.context import FSMContext

from elements import ELEMENTS
from keyboards import kb_periods, kb_elements_for_period, kb_main
from .states import Form
from .utils import ai_text

router = Router()

TABLE_IMAGE_PATH = "images/mendeleev_table.jpg"
TABLE_IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Periodic_table_large.svg/2000px-Periodic_table_large.svg.png"

async def send_table_image(chat_id, bot: Bot, caption: str, reply_markup):
    if os.path.exists(TABLE_IMAGE_PATH):
        photo = FSInputFile(TABLE_IMAGE_PATH)
        await bot.send_photo(chat_id, photo, caption=caption, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        try:
            photo = URLInputFile(TABLE_IMAGE_URL)
            await bot.send_photo(chat_id, photo, caption=caption, reply_markup=reply_markup, parse_mode="Markdown")
        except Exception as e:
            await bot.send_message(
                chat_id,
                f"{caption}\n\n[Скачать таблицу]({TABLE_IMAGE_URL})",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )

@router.callback_query(F.data == "mendeleev")
async def cb_mendeleev(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.delete()
    except:
        pass
    await send_table_image(
        callback.message.chat.id,
        callback.bot,
        "🧪 **Периодическая таблица Менделеева**\nВыбери период (ряд):",
        kb_periods()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("period_"))
async def cb_period(callback: CallbackQuery, state: FSMContext):
    period = int(callback.data.split("_")[1])
    try:
        await callback.message.delete()
    except:
        pass
    kb = kb_elements_for_period(period)
    kb.inline_keyboard.append([InlineKeyboardButton(text="← Назад к периодам", callback_data="back_to_periods")])

    await callback.message.answer(
        f"🧪 **{period} период**\n\nНажми на символ элемента, чтобы узнать подробности:",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_periods")
async def back_to_periods(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.delete()
    except:
        pass
    await send_table_image(
        callback.message.chat.id,
        callback.bot,
        "🧪 **Периодическая таблица Менделеева**\nВыбери период (ряд):",
        kb_periods()
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

    try:
        await callback.message.delete()
    except:
        pass
    await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def cb_back_to_main(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.delete()
    except:
        pass
    await callback.message.answer("Главное меню:", reply_markup=kb_main())
    await state.clear()
    await callback.answer()

# ========== СПРАВОЧНИК РЕАКЦИЙ ==========
@router.callback_query(F.data == "reactions")
async def cb_reactions(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.delete()
    except:
        pass
    await callback.message.answer(
        "⚗️ **Справочник реакций**\n\n"
        "Напиши название реакции, тип или реагенты (например, «горение метана», «нейтрализация», «KMnO4 + H2O2»), и я объясню.\n\n"
        "Или отправь символ элемента (например, Na), и я покажу типичные реакции с ним.",
        parse_mode="Markdown"
    )
    await state.set_state(Form.reaction_query)
    await callback.answer()

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
    try:
        await callback.message.delete()
    except:
        pass
    await callback.message.answer(
        f"⚗️ **Реакции с участием {element['name']} ({symbol})**\n\n"
        f"Напиши конкретный запрос, например: «{symbol} + O2» или «реакции {element['name']} с водой».",
        parse_mode="Markdown"
    )
    await state.set_state(Form.reaction_query)
    await callback.answer()

# ========== ОБРАБОТЧИКИ ДЛЯ ПРЕДМЕТНОГО МЕНЮ ==========
@router.callback_query(F.data.startswith("subj_reactions_"))
async def subj_reactions(callback: CallbackQuery, state: FSMContext):
    subj = callback.data.split("_")[2]
    if subj != "chemistry":
        await callback.answer("Эта функция доступна только для химии.")
        return
    await cb_reactions(callback, state)

@router.callback_query(F.data.startswith("subj_mendeleev_"))
async def subj_mendeleev(callback: CallbackQuery, state: FSMContext):
    subj = callback.data.split("_")[2]
    if subj != "chemistry":
        await callback.answer("Эта функция доступна только для химии.")
        return
    await cb_mendeleev(callback, state)