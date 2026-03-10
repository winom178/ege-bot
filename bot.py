import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from aiohttp import web

from logger_config import setup_logging
import database as db
from handlers import (
    common_router,
    subjects_router,
    tasks_router,
    exam_router,
    profile_router,
    elements_router,
    cheatsheets_router,
    photo_router,
    admin_router,
    achievements_router,
    repetition_router,
    referral_router,
    adaptive_router,
    daily_challenge_router,
    lava_router,
)

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
db.init_achievements()

dp.include_router(common_router)
dp.include_router(subjects_router)
dp.include_router(tasks_router)
dp.include_router(exam_router)
dp.include_router(profile_router)
dp.include_router(elements_router)
dp.include_router(cheatsheets_router)
dp.include_router(photo_router)
dp.include_router(admin_router)
dp.include_router(achievements_router)
dp.include_router(repetition_router)
dp.include_router(referral_router)
dp.include_router(adaptive_router)
dp.include_router(daily_challenge_router)
dp.include_router(lava_router)

async def handle_health(request):
    return web.Response(text="OK", status=200)

async def handle_root(request):
    return web.Response(text="Бот работает", status=200)

# Эндпоинт для верификации домена LAVA
async def handle_lava_verification(request):
    # Возвращаем текст, предоставленный LAVA для подтверждения домена
    return web.Response(text="lava-verify=bc80577c07a158d1", status=200)

async def handle_lava_webhook(request):
    try:
        data = await request.json()
        logger.info(f"LAVA webhook received: {data}")

        # Здесь должна быть проверка подписи (по документации LAVA)

        if data.get("status") == "success" or data.get("status") == "paid":
            order_id = data.get("order_id")
            payment = db.get_pending_payment(order_id)
            if payment:
                expires = db.set_subject_premium(
                    payment["user_id"],
                    payment["subject"],
                    payment["days"]
                )
                try:
                    await bot.send_message(
                        payment["user_id"],
                        f"✅ Оплата прошла успешно!\n"
                        f"Премиум на предмет {payment['subject']} активирован на {payment['days']} дней (до {expires})."
                    )
                except Exception as e:
                    logger.error(f"Не удалось уведомить пользователя {payment['user_id']}: {e}")
                db.delete_pending_payment(order_id)
        return web.Response(text="OK", status=200)
    except Exception as e:
        logger.exception(f"Webhook error: {e}")
        return web.Response(text="Error", status=500)

async def run_web_server():
    app = web.Application()
    app.router.add_get('/health', handle_health)
    app.router.add_get('/healthcheck', handle_health)
    app.router.add_get('/', handle_root)
    # Эндпоинты для LAVA
    app.router.add_get('/lava-verification.txt', handle_lava_verification)
    app.router.add_post('/lava-webhook', handle_lava_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    logger.info("✅ Web server started on port 10000")

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

async def main():
    asyncio.create_task(run_web_server())
    asyncio.create_task(reminder_worker())
    logger.info("🚀 Бот запущен")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
