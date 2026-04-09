import asyncio
import logging
import json
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from bot.handlers import start, payment, subscription, admin
from bot.database import init_db
from bot.scheduler import start_scheduler
from bot.config import BOT_TOKEN, WEB_SERVER_HOST, WEB_SERVER_PORT, WEBHOOK_URL, CHANNEL_ID

from aiohttp import web

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


async def stats_handler(request):
    """Реальная статистика канала для Mini App"""
    try:
        count = await bot.get_chat_member_count(chat_id=CHANNEL_ID)
    except Exception:
        count = 0
    data = {"members": count}
    return web.Response(
        text=json.dumps(data),
        content_type="application/json",
        headers={"Access-Control-Allow-Origin": "*"}
    )


async def serve_webapp(request):
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
    app.router.add_get("/webapp/stats", stats_handler)
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
