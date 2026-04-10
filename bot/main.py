import asyncio
import logging
import json
import os
import signal
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from bot.handlers import start, payment, subscription, admin
from bot.database import init_db
from bot.scheduler import start_scheduler
from bot.config import BOT_TOKEN, WEB_SERVER_HOST, WEB_SERVER_PORT, CHANNEL_ID

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
    try:
        count = await bot.get_chat_member_count(chat_id=CHANNEL_ID)
        logger.info(f"Channel members: {count}")
    except Exception as e:
        logger.error(f"Failed to get member count for {CHANNEL_ID}: {e}")
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
        return web.Response(text="Mini App not found", status=404)


async def main():
    await init_db()
    start_scheduler(bot)

    # Сначала удаляем вебхук если был установлен ранее
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Webhook deleted, starting polling...")

    # Веб-сервер
    app = web.Application()
    app.router.add_get("/ping", ping_handler)
    app.router.add_get("/webapp/stats", stats_handler)
    app.router.add_get("/webapp/", serve_webapp)
    app.router.add_get("/webapp", serve_webapp)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_SERVER_HOST, WEB_SERVER_PORT)
    await site.start()
    logger.info(f"Web server on port {WEB_SERVER_PORT}")

    # Polling — с явной остановкой при SIGTERM
    polling_task = asyncio.create_task(
        dp.start_polling(
            bot,
            skip_updates=True,
            handle_signals=False
        )
    )

    # Обработка сигнала остановки
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def handle_sigterm():
        logger.info("SIGTERM received, stopping...")
        stop_event.set()

    loop.add_signal_handler(signal.SIGTERM, handle_sigterm)
    loop.add_signal_handler(signal.SIGINT, handle_sigterm)

    await stop_event.wait()

    # Грациозная остановка
    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass

    await dp.stop_polling()
    await runner.cleanup()
    await bot.session.close()
    logger.info("Bot stopped gracefully")


if __name__ == "__main__":
    asyncio.run(main())
