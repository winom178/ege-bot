import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from aiohttp import web  # для веб-сервера

from logger_config import setup_logging
import database as db
from handlers import router

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

# ========== ВЕБ-СЕРВЕР ДЛЯ HEALTHCHECK ==========
async def handle_health(request):
    """Ответ на запрос /health (и /healthcheck)"""
    return web.Response(text="OK", status=200)

async def handle_root(request):
    """Ответ на корневой URL (например, для проверки в браузере)"""
    return web.Response(text="Бот работает", status=200)

async def run_web_server():
    """Запускает HTTP-сервер на порту 10000"""
    app = web.Application()
    app.router.add_get('/health', handle_health)
    app.router.add_get('/healthcheck', handle_health)
    app.router.add_get('/', handle_root)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    logger.info("✅ Web server started on port 10000")

# ========== ФОНОВЫЙ ПРОЦЕСС ДЛЯ НАПОМИНАНИЙ ==========
async def reminder_worker():
    while True:
        now = datetime.now().strftime("%H:%M")
        reminders = db.get_active_reminders()
        for user_id, time_str in reminders:
            if time_str == now:
                try:
                    await bot.send_message(user_id, "🔔 Напоминание: пора позаниматься подготовкой к ЕГЭ!")
                except Exception as e:
                    logger.error(f"Не удалось отправить напоминание пользователю {user_id}: {e}")
        await asyncio.sleep(60)

# ========== ГЛАВНАЯ ФУНКЦИЯ ==========
async def main():
    # Запускаем веб-сервер параллельно с ботом
    asyncio.create_task(run_web_server())
    asyncio.create_task(reminder_worker())
    logger.info("🚀 Бот запущен")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())    """Ответ на корневой URL (например, для проверки в браузере)"""
    return web.Response(text="Бот работает", status=200)

async def run_web_server():
    """Запускает HTTP-сервер на порту 10000"""
    app = web.Application()
    app.router.add_get('/health', handle_health)
    app.router.add_get('/healthcheck', handle_health)
    app.router.add_get('/', handle_root)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    logger.info("✅ Web server started on port 10000")

# ========== ФОНОВЫЙ ПРОЦЕСС ДЛЯ НАПОМИНАНИЙ ==========
async def reminder_worker():
    while True:
        now = datetime.now().strftime("%H:%M")
        reminders = db.get_active_reminders()
        for user_id, time_str in reminders:
            if time_str == now:
                try:
                    await bot.send_message(user_id, "🔔 Напоминание: пора позаниматься подготовкой к ЕГЭ!")
                except Exception as e:
                    logger.error(f"Не удалось отправить напоминание пользователю {user_id}: {e}")
        await asyncio.sleep(60)

# ========== ГЛАВНАЯ ФУНКЦИЯ ==========
async def main():
    # Запускаем веб-сервер параллельно с ботом
    asyncio.create_task(run_web_server())
    asyncio.create_task(reminder_worker())
    logger.info("🚀 Бот запущен")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())    """Ответ на корневой URL (например, для проверки в браузере)"""
    return web.Response(text="Бот работает", status=200)

async def run_web_server():
    """Запускает HTTP-сервер на порту 10000"""
    app = web.Application()
    app.router.add_get('/health', handle_health)
    app.router.add_get('/healthcheck', handle_health)
    app.router.add_get('/', handle_root)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    logger.info("✅ Web server started on port 10000")

# ========== ФОНОВЫЙ ПРОЦЕСС ДЛЯ НАПОМИНАНИЙ ==========
async def reminder_worker():
    while True:
        now = datetime.now().strftime("%H:%M")
        reminders = db.get_active_reminders()
        for user_id, time_str in reminders:
            if time_str == now:
                try:
                    await bot.send_message(user_id, "🔔 Напоминание: пора позаниматься подготовкой к ЕГЭ!")
                except Exception as e:
                    logger.error(f"Не удалось отправить напоминание пользователю {user_id}: {e}")
        await asyncio.sleep(60)

# ========== ГЛАВНАЯ ФУНКЦИЯ ==========
async def main():
    # Запускаем веб-сервер параллельно с ботом
    asyncio.create_task(run_web_server())
    asyncio.create_task(reminder_worker())
    logger.info("🚀 Бот запущен")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())    """Обработчик для корневого URL"""
    return web.Response(text="Бот работает", status=200)

async def run_web_server():
    """Запускает HTTP-сервер на порту 10000"""
    app = web.Application()
    app.router.add_get('/health', handle_health)
    app.router.add_get('/', handle_root)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)  # слушаем все интерфейсы на порту 10000
    await site.start()
    logger.info("Web server started on port 10000")

# ========== ФОНОВЫЙ ПРОЦЕСС ДЛЯ НАПОМИНАНИЙ ==========
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
    # Запускаем веб-сервер параллельно
    asyncio.create_task(run_web_server())
    asyncio.create_task(reminder_worker())
    logger.info("Бот запущен")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())                    await bot.send_message(user_id, "🔔 Напоминание: пора позаниматься подготовкой к ЕГЭ!")
                except:
                    pass
        await asyncio.sleep(60)

async def main():
    asyncio.create_task(reminder_worker())
    logger.info("Бот запущен")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
