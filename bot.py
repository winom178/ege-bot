import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from logger_config import setup_logging
import database as db
from handlers import router  # импортируем роутер из handlers.py

setup_logging()
logger = logging.getLogger(__name__)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

db.init_db()
dp.include_router(router)

async def reminder_worker():
    while True:
        now = datetime.now().strftime("%H:%M")
        reminders = db.get_active_reminders()
        for user_id, time_str in reminders:
            if time_str == now:
                try:
                    await bot.send_message(user_id, "🔔 Напоминание: пора позаниматься подготовкой к ЕГЭ!")
                except:
                    pass
        await asyncio.sleep(60)

async def main():
    asyncio.create_task(reminder_worker())
    logger.info("Бот запущен")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())