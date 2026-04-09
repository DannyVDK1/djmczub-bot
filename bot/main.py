import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from bot.handlers import start, payment, subscription, admin
from bot.database import init_db
from bot.scheduler import start_scheduler
from bot.config import BOT_TOKEN, WEB_SERVER_HOST, WEB_SERVER_PORT, WEBHOOK_URL

from aiohttp import web
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

dp.include_router(start.router)
dp.include_router(payment.router)
dp.include_router(subscription.router)
dp.include_router(admin.router)


async def ping_handler(request):
    return web.Response(text="OK")


async def serve_webapp(request):
    # Отдаём Mini App файлы
    filepath = os.path.join(os.path.dirname(__file__), '..', 'webapp', 'index.html')
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return web.Response(text=content, content_type='text/html')
    except FileNotFoundError:
        return web.Response(text="Mini App not found", status=404)


async def on_startup():
    await init_db()
    logger.info("Bot started in polling mode")


async def run_polling():
    await on_startup()
    start_scheduler(bot)
    await dp.start_polling(bot, skip_updates=True)


async def run_web():
    app = web.Application()
    app.router.add_get("/ping", ping_handler)
    app.router.add_get("/webapp/", serve_webapp)
    app.router.add_get("/webapp", serve_webapp)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_SERVER_HOST, WEB_SERVER_PORT)
    await site.start()
    logger.info(f"Web server started on port {WEB_SERVER_PORT}")
    return runner


async def main():
    runner = await run_web()
    try:
        await run_polling()
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
