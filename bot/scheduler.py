import asyncio
import logging
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bot.database import get_expired_subscriptions, deactivate_subscription
from bot.config import CHANNEL_ID

logger = logging.getLogger(__name__)
CHAT_ID = -1003989707456

RULES_MESSAGE = """📋 <b>ПРАВИЛА ЧАТА DJ MC ZUB</b>

👋 Добро пожаловать! Для комфортного общения соблюдайте правила:

🚫 <b>ЗАПРЕЩЕНО:</b>
• Политика — любые политические темы, деятели, события
• Религия — религиозные темы, убеждения, призывы
• Оскорбления участников и автора канала
• Нецензурная лексика и мат
• Реклама, спам, ссылки на сторонние ресурсы
• Провокации и разжигание конфликтов

⚠️ <b>СИСТЕМА ПРЕДУПРЕЖДЕНИЙ:</b>
1️⃣ Нарушение → предупреждение 1/3
2️⃣ Нарушение → предупреждение 2/3  
3️⃣ Нарушение → предупреждение 3/3 → <b>бан 1 сутки</b>
🔴 Повторно → <b>3 суток → неделя → навсегда</b>

✅ Бан только в чате. Доступ к каналу сохраняется.
🤖 Модератор: @dj_mc_zub_bot"""


async def send_rules_reminder(bot: Bot):
    try:
        msg = await bot.send_message(
            chat_id=CHAT_ID,
            text=RULES_MESSAGE,
            disable_notification=True
        )
        logger.info(f"Rules reminder sent")
        await asyncio.sleep(25 * 60)
        try:
            await bot.delete_message(CHAT_ID, msg.message_id)
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Rules reminder error: {e}")


async def check_expired_subscriptions(bot: Bot):
    expired = await get_expired_subscriptions()
    logger.info(f"Checking expired subscriptions: {len(expired)} found")
    for sub in expired:
        user_id = sub["user_id"]
        try:
            await bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
            await asyncio.sleep(0.5)
            await bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
            await deactivate_subscription(user_id)
            from bot.config import WEBHOOK_URL
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="🎵 Продлить подписку",
                    web_app=WebAppInfo(url=f"{WEBHOOK_URL}/webapp/")
                )
            ]])
            await bot.send_message(
                chat_id=user_id,
                text=(
                    "🔒 <b>Ваша подписка на DJ MC ZUB истекла</b>\n\n"
                    "Доступ к закрытому каналу закрыт.\n\n"
                    "Чтобы продолжить получать эксклюзивный контент — оформите подписку заново 👇"
                ),
                reply_markup=keyboard
            )
            logger.info(f"Kicked user {user_id}")
        except Exception as e:
            logger.error(f"Error for user {user_id}: {e}")


def start_scheduler(bot: Bot):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_expired_subscriptions,
        trigger="interval", hours=1, args=[bot],
        id="check_subs", replace_existing=True
    )
    scheduler.add_job(
        send_rules_reminder,
        trigger="interval", minutes=30, args=[bot],
        id="rules_reminder", replace_existing=True
    )
    scheduler.start()
    logger.info("Scheduler started")
