# handlers/states.py
from aiogram.fsm.state import State, StatesGroup

class Form(StatesGroup):
    main = State()
    subject = State()
    subject_menu = State()
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
    gift_user_input = State()  # для ввода ID получателя подарка