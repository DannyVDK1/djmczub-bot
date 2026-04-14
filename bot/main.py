import asyncio
import logging
import json
import os
import hashlib
import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from bot.handlers import start, payment, subscription, admin, moderation
from bot.database import init_db
from bot.scheduler import start_scheduler
from bot.config import BOT_TOKEN, WEB_SERVER_HOST, WEB_SERVER_PORT, WEBHOOK_URL, CHANNEL_ID, YOOMONEY_WALLET, YOOMONEY_TOKEN
from aiohttp import web

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WEBHOOK_PATH = "/bot/webhook"
WEBHOOK_FULL_URL = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
YOOMONEY_SECRET = "M7xbx4k8GIPAeBvJvpoBF0ok"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
dp.include_router(start.router)
dp.include_router(payment.router)
dp.include_router(subscription.router)
dp.include_router(admin.router)
dp.include_router(moderation.router)


async def ping_handler(request):
    return web.Response(text="OK")


async def config_handler(request):
    return web.Response(
        text=json.dumps({"wallet": YOOMONEY_WALLET}),
        content_type="application/json",
        headers={"Access-Control-Allow-Origin": "*"}
    )


async def stats_handler(request):
    try:
        count = await bot.get_chat_member_count(chat_id=CHANNEL_ID)
        logger.info(f"Channel {CHANNEL_ID} members: {count}")
    except Exception as e:
        logger.error(f"Stats error: {e}")
        count = 0
    return web.Response(
        text=json.dumps({"members": count}),
        content_type="application/json",
        headers={"Access-Control-Allow-Origin": "*"}
    )


async def yoomoney_notify_handler(request):
    """
    Обработчик HTTP-уведомлений от ЮМани.
    ЮМани присылает POST когда деньги поступают на кошелёк.
    Документация: https://yoomoney.ru/docs/payment-buttons/using-api/notifications
    """
    try:
        data = await request.post()
        logger.info(f"YooMoney notification received: {dict(data)}")

        # Проверяем подпись (SHA1)
        notification_type = data.get("notification_type", "")
        operation_id = data.get("operation_id", "")
        amount = data.get("amount", "")
        currency = data.get("currency", "643")
        datetime_str = data.get("datetime", "")
        sender = data.get("sender", "")
        codepro = data.get("codepro", "false")
        label = data.get("label", "")
        sha1_hash = data.get("sha1_hash", "")

        # Верифицируем подпись
        check_str = "&".join([
            notification_type, operation_id, amount, currency,
            datetime_str, sender, codepro, YOOMONEY_SECRET, label
        ])
        expected_hash = hashlib.sha1(check_str.encode("utf-8")).hexdigest()

        if sha1_hash != expected_hash:
            logger.error(f"YooMoney: invalid signature! expected={expected_hash}, got={sha1_hash}")
            return web.Response(text="invalid signature", status=400)

        logger.info(f"YooMoney payment confirmed: label={label} amount={amount}")

        # Разбираем label: userId_plan
        if "_" not in label:
            logger.warning(f"Unknown label format: {label}")
            return web.Response(text="ok")

        parts = label.split("_")
        if len(parts) < 2:
            return web.Response(text="ok")

        user_id = int(parts[0])
        plan_key = parts[1]

        from bot.config import SUBSCRIPTION_PLANS
        if plan_key not in SUBSCRIPTION_PLANS:
            logger.warning(f"Unknown plan: {plan_key}")
            return web.Response(text="ok")

        plan = SUBSCRIPTION_PLANS[plan_key]
        paid_amount = float(amount)

        if paid_amount < plan["price"] * 0.90:
            logger.warning(f"Amount too small: {paid_amount} < {plan['price']}")
            return web.Response(text="ok")

        # Активируем подписку
        from bot.handlers.payment import activate_subscription
        from bot.database import create_payment, get_payment
        from datetime import datetime

        payment_id = f"{user_id}_{plan_key}_{operation_id}"
        await create_payment(user_id, plan_key, plan["price"], payment_id)
        payment_rec = await get_payment(payment_id)

        class FakeUser:
            def __init__(self, uid):
                self.id = uid
                self.username = ""
                self.first_name = "Подписчик"

        await activate_subscription(FakeUser(user_id), payment_rec, bot)
        logger.info(f"Subscription activated via notification: user={user_id} plan={plan_key}")

        return web.Response(text="ok")

    except Exception as e:
        logger.error(f"YooMoney notify error: {e}", exc_info=True)
        return web.Response(text="error", status=500)


async def check_payment_handler(request):
    """Ручная проверка платежа из Mini App"""
    try:
        data = await request.json()
        user_id = int(data.get("user_id", 0))
        plan_key = data.get("plan", "")

        if not user_id or plan_key not in ["1m", "3m", "6m", "12m"]:
            return web.Response(
                text=json.dumps({"ok": False, "paid": False, "message": "Неверные параметры"}),
                content_type="application/json",
                headers={"Access-Control-Allow-Origin": "*"},
                status=400
            )

        from bot.config import SUBSCRIPTION_PLANS
        from bot.database import get_subscription
        plan = SUBSCRIPTION_PLANS[plan_key]
        label = f"{user_id}_{plan_key}"

        # Сначала проверяем — может подписка уже активирована через уведомление
        existing_sub = await get_subscription(user_id)
        if existing_sub:
            return web.Response(
                text=json.dumps({"ok": True, "paid": True, "message": "Подписка уже активирована!"}),
                content_type="application/json",
                headers={"Access-Control-Allow-Origin": "*"}
            )

        # Проверяем через API ЮМани
        is_paid = await check_yoomoney_api(label, plan["price"])

        if not is_paid:
            return web.Response(
                text=json.dumps({
                    "ok": False,
                    "paid": False,
                    "message": "Платёж не найден. Если оплатили — подождите 1-2 минуты и попробуйте снова."
                }),
                content_type="application/json",
                headers={"Access-Control-Allow-Origin": "*"}
            )

        # Активируем
        from bot.handlers.payment import activate_subscription
        from bot.database import create_payment, get_payment
        from datetime import datetime

        payment_id = f"{user_id}_{plan_key}_{int(datetime.now().timestamp())}"
        await create_payment(user_id, plan_key, plan["price"], payment_id)
        payment_rec = await get_payment(payment_id)

        class FakeUser:
            def __init__(self, uid):
                self.id = uid
                self.username = ""
                self.first_name = "Подписчик"

        await activate_subscription(FakeUser(user_id), payment_rec, bot)

        return web.Response(
            text=json.dumps({"ok": True, "paid": True, "message": "Подписка активирована!"}),
            content_type="application/json",
            headers={"Access-Control-Allow-Origin": "*"}
        )

    except Exception as e:
        logger.error(f"check_payment error: {e}", exc_info=True)
        return web.Response(
            text=json.dumps({"ok": False, "paid": False, "error": str(e)}),
            content_type="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
            status=500
        )


async def check_yoomoney_api(label: str, amount: int) -> bool:
    if not YOOMONEY_TOKEN:
        return False
    url = "https://yoomoney.ru/api/operation-history"
    headers = {
        "Authorization": f"Bearer {YOOMONEY_TOKEN}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = f"label={label}&records=10"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=data) as resp:
                body = await resp.text()
                logger.info(f"YooMoney API [{resp.status}] label={label}: {body[:200]}")
                if resp.status != 200:
                    return False
                result = json.loads(body)
                for op in result.get("operations", []):
                    if (op.get("status") == "success"
                            and op.get("direction") == "in"
                            and op.get("label") == label
                            and float(op.get("amount", 0)) >= amount * 0.90):
                        return True
                return False
    except Exception as e:
        logger.error(f"YooMoney API error: {e}")
        return False


async def get_token_handler(request):
    c = request.rel_url.query.get('code', '')
    if not c:
        return web.Response(text='no code')
    async with aiohttp.ClientSession() as s:
        async with s.post('https://yoomoney.ru/oauth/token', data={
            'code': c,
            'client_id': '1E1BB17B5A10F0923D398183C68EFDBF54FB6538387DE99ADF2B6601C838C21C',
            'grant_type': 'authorization_code',
            'redirect_uri': 'https://djmczub-bot.onrender.com'
        }) as r:
            return web.Response(text=await r.text(), headers={"Access-Control-Allow-Origin": "*"})


async def serve_webapp(request):
    filepath = os.path.join(os.path.dirname(__file__), '..', 'webapp', 'index.html')
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return web.Response(text=f.read(), content_type='text/html')
    except FileNotFoundError:
        return web.Response(text="Not found", status=404)


async def on_startup(app):
    await init_db()
    start_scheduler(bot)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(
            url=WEBHOOK_FULL_URL,
            allowed_updates=["message", "callback_query", "web_app_data"]
        )
        info = await bot.get_webhook_info()
        logger.info(f"Webhook OK: {info.url}")
    except Exception as e:
        logger.error(f"Webhook error: {e}")


async def on_shutdown(app):
    await bot.session.close()
    logger.info("Bot stopped")


def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.router.add_get("/ping", ping_handler)
    app.router.add_get("/get_token", get_token_handler)
    app.router.add_get("/webapp/config", config_handler)
    app.router.add_get("/webapp/stats", stats_handler)
    app.router.add_post("/webapp/check_payment", check_payment_handler)
    app.router.add_post("/yoomoney/notify", yoomoney_notify_handler)
    app.router.add_get("/webapp/", serve_webapp)
    app.router.add_get("/webapp", serve_webapp)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    web.run_app(app, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)


if __name__ == "__main__":
    main()
