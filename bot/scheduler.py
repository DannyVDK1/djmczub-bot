import asyncio
import logging
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bot.database import get_expired_subscriptions, deactivate_subscription
from bot.config import CHANNEL_ID

logger = logging.getLogger(__name__)
CHAT_ID = -1003989707456

RULES_MESSAGE = """\U0001f4cb <b>ПРАВИЛА ЧАТА DJ MC ZUB</b>

Привет! Чтобы общение было комфортным — соблюдай правила:

\U0001f6ab <b>ЗАПРЕЩЕНО:</b>
• Мат и нецензурная лексика
• Оскорбления участников и автора
• Обсуждение политики и войн
• Обсуждение религии и призывы
• Реклама, спам и ссылки
• Провокации и конфликты

\u26a0\ufe0f <b>СИСТЕМА ПРЕДУПРЕЖДЕНИЙ:</b>
1\ufe0f\u20e3 Нарушение → предупреждение 1/3
2\ufe0f\u20e3 Нарушение → предупреждение 2/3
3\ufe0f\u20e3 Нарушение → предупреждение 3/3

\U0001f6ab После 3 предупреждений:
• 1-й раз — блокировка на <b>1 сутки</b>
• 2-й раз — блокировка на <b>3 суток</b>
• 3-й раз — блокировка на <b>1 неделю</b>
• 4-й раз — <b>навсегда</b>

\u2705 Блокировка только в чате. Канал остаётся!
\U0001f916 Модератор: @dj_mc_zub_bot""".strip()


async def send_rules_reminder(bot: Bot):
    try:
        msg = await bot.send_message(
            chat_id=CHAT_ID,
            text=RULES_MESSAGE,
            disable_notification=True
        )
        logger.info(f"Rules reminder sent to chat {CHAT_ID}")
        await asyncio.sleep(25 * 60)
        try:
            await bot.delete_message(CHAT_ID, msg.message_id)
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Failed to send rules reminder: {e}")


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
                    text="\U0001f3b5 Продлить подписку",
                    web_app=WebAppInfo(url=f"{WEBHOOK_URL}/webapp/")
                )
            ]])
            await bot.send_message(
                chat_id=user_id,
                text=(
                    "\U0001f512 <b>Ваша подписка на DJ MC ZUB истекла</b>\n\n"
                    "Доступ к закрытому каналу закрыт.\n\n"
                    "Чтобы продолжить — продлите подписку \U0001f447"
                ),
                reply_markup=keyboard
            )
            logger.info(f"Kicked and notified user {user_id}")
        except Exception as e:
            logger.error(f"Error processing expired sub for {user_id}: {e}")


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
