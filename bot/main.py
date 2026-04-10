import asyncio
import logging
import json
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from bot.handlers import start, payment, subscription, admin
from bot.database import init_db
from bot.scheduler import start_scheduler
from bot.config import BOT_TOKEN, WEB_SERVER_HOST, WEB_SERVER_PORT, WEBHOOK_URL, CHANNEL_ID, YOOMONEY_WALLET

from aiohttp import web

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WEBHOOK_PATH = "/bot/webhook"
WEBHOOK_FULL_URL = f"{WEBHOOK_URL}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

dp.include_router(start.router)
dp.include_router(payment.router)
dp.include_router(subscription.router)
dp.include_router(admin.router)


async def ping_handler(request):
    return web.Response(text="OK")


async def config_handler(request):
    """Конфиг для Mini App — номер кошелька ЮМани"""
    return web.Response(
        text=json.dumps({"wallet": YOOMONEY_WALLET}),
        content_type="application/json",
        headers={"Access-Control-Allow-Origin": "*"}
    )


async def stats_handler(request):
    """Реальная статистика канала"""
    try:
        count = await bot.get_chat_member_count(chat_id=CHANNEL_ID)
        logger.info(f"Channel {CHANNEL_ID} members: {count}")
    except Exception as e:
        logger.error(f"Stats error for channel {CHANNEL_ID}: {e}")
        count = 0
    return web.Response(
        text=json.dumps({"members": count}),
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
        return web.Response(text="Not found", status=404)


async def on_startup(app):
    await init_db()
    start_scheduler(bot)
    await bot.set_webhook(
        url=WEBHOOK_FULL_URL,
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query", "web_app_data"]
    )
    logger.info(f"Webhook set: {WEBHOOK_FULL_URL}")


async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("Bot stopped")


def main():
    app = web.Application()

    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    app.router.add_get("/ping", ping_handler)
    app.router.add_get("/webapp/config", config_handler)
    app.router.add_get("/webapp/stats", stats_handler)
    app.router.add_get("/webapp/", serve_webapp)
    app.router.add_get("/webapp", serve_webapp)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    web.run_app(app, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)


if __name__ == "__main__":
    main()
