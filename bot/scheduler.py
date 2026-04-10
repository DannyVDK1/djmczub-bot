import asyncio
import logging
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.database import get_expired_subscriptions, deactivate_subscription
from bot.config import CHANNEL_ID, CHAT_ID

logger = logging.getLogger(__name__)


async def kick_from_chat(bot: Bot, chat_id: int, user_id: int):
    """Кикаем пользователя из чата и сразу разбаниваем чтобы мог переподписаться"""
    try:
        await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        await bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
        logger.info(f"Kicked user {user_id} from {chat_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to kick {user_id} from {chat_id}: {e}")
        return False


async def check_expired_subscriptions(bot: Bot):
    expired = await get_expired_subscriptions()
    logger.info(f"Checking expired: {len(expired)} found")

    for sub in expired:
        user_id = sub["user_id"]
        try:
            # Кикаем из основного канала
            if CHANNEL_ID:
                await kick_from_chat(bot, CHANNEL_ID, user_id)

            # Кикаем из связанного чата
            if CHAT_ID:
                await kick_from_chat(bot, CHAT_ID, user_id)

            # Деактивируем в БД
            await deactivate_subscription(user_id)

            # Уведомляем пользователя
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
            from bot.config import WEBHOOK_URL
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
                    "Доступ к каналу и чату закрыт.\n\n"
                    "Чтобы продолжить — продлите подписку:"
                ),
                reply_markup=keyboard
            )
            logger.info(f"Processed expired sub for user {user_id}")
        except Exception as e:
            logger.error(f"Error processing expired sub for {user_id}: {e}")


def start_scheduler(bot: Bot):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_expired_subscriptions,
        trigger="interval",
        hours=1,
        args=[bot],
        id="check_subs",
        replace_existing=True
    )
    scheduler.start()
    logger.info("Scheduler started")
