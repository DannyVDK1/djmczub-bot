import asyncio
import logging
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bot.database import get_expired_subscriptions, deactivate_subscription
from bot.config import CHANNEL_ID

logger = logging.getLogger(__name__)

CHAT_ID = -1003989707456

RULES_MESSAGE = (
    "\U0001f4cb <b>ПРАВИЛА ЧАТА DJ MC ZUB</b>\n\n"
    "Добро пожаловать! Для комфортного общения соблюдайте правила:\n\n"
    "\U0001f6ab <b>ЗАПРЕЩЕНО:</b>\n"
    "- Политика (выборы, война, политики)\n"
    "- Религия и религиозные призывы\n"
    "- Оскорбления участников и автора\n"
    "- Нецензурная лексика\n"
    "- Реклама, спам, сторонние ссылки\n"
    "- Провокации и конфликты\n\n"
    "\u26a0\ufe0f <b>ПРЕДУПРЕЖДЕНИЯ:</b>\n"
    "1 наруш. - предупреждение 1/3\n"
    "2 наруш. - предупреждение 2/3\n"
    "3 наруш. - предупреждение 3/3 + бан 1 сутки\n"
    "Далее: 3 суток - 1 неделя - навсегда\n\n"
    "\u2705 Бан только из чата. Канал остаётся!\n"
    "@dj_mc_zub_bot - модератор"
)


async def send_rules_reminder(bot: Bot):
    try:
        msg = await bot.send_message(
            chat_id=CHAT_ID,
            text=RULES_MESSAGE,
            disable_notification=True
        )
        logger.info(f"Rules sent to {CHAT_ID}, msg_id={msg.message_id}")
        # Планируем удаление через отдельную задачу
        asyncio.create_task(_delete_later(bot, CHAT_ID, msg.message_id, 25 * 60))
    except Exception as e:
        logger.error(f"Rules reminder error: {e}")


async def _delete_later(bot: Bot, chat_id: int, msg_id: int, delay: int):
    try:
        await asyncio.sleep(delay)
        await bot.delete_message(chat_id, msg_id)
    except Exception:
        pass


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
                    "Чтобы продолжить - продлите подписку:"
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
