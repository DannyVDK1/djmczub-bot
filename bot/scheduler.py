import asyncio
import logging
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bot.database import get_expired_subscriptions, deactivate_subscription
from bot.config import CHANNEL_ID

logger = logging.getLogger(__name__)

CHAT_ID = -1003989707456

RULES_MESSAGE = """
📋 <b>ПРАВИЛА ЧАТА DJ MC ZUB</b>

Добро пожаловать в наше сообщество! Чтобы общение было комфортным для всех, просим соблюдать правила:

🚫 <b>ЗАПРЕЩЕНО:</b>
• Обсуждение политики, выборов, войн и политических деятелей
• Обсуждение религии, религиозных убеждений и призывов
• Оскорбления других участников и автора канала
• Нецензурная лексика и грубость
• Реклама, спам и ссылки на сторонние ресурсы
• Провокации и разжигание конфликтов

⚠️ <b>СИСТЕМА ПРЕДУПРЕЖДЕНИЙ:</b>
1️⃣ 1-е нарушение — предупреждение (1/3)
2️⃣ 2-е нарушение — предупреждение (2/3)
3️⃣ 3-е нарушение — предупреждение (3/3)
🚫 После 3 предупреждений:
• 1-й раз — блокировка на 1 сутки
• 2-й раз — блокировка на 3 суток
• 3-й раз — блокировка на 1 неделю
• 4-й раз — постоянная блокировка в чате

✅ Блокировка только в этом чате. Доступ к основному каналу сохраняется.

💬 Давайте общаться уважительно и с удовольствием!
@dj_mc_zub_bot — модератор чата
""".strip()


async def send_rules_reminder(bot: Bot):
    """Отправляем напоминание о правилах каждый час"""
    try:
        msg = await bot.send_message(
            chat_id=CHAT_ID,
            text=RULES_MESSAGE,
            disable_notification=True
        )
        # Закрепляем если нужно — нет, просто отправляем
        logger.info(f"Rules reminder sent to chat {CHAT_ID}")
        # Удаляем через 50 минут чтобы не засорять чат
        await asyncio.sleep(50 * 60)
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
                    text="🎵 Продлить подписку",
                    web_app=WebAppInfo(url=f"{WEBHOOK_URL}/webapp/")
                )
            ]])
            await bot.send_message(
                chat_id=user_id,
                text=(
                    "🔒 <b>Ваша подписка на DJ MC ZUB истекла</b>\n\n"
                    "Доступ к закрытому каналу закрыт.\n\n"
                    "Чтобы продолжить получать эксклюзивный контент — продлите подписку 👇"
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
        trigger="interval", hours=1, args=[bot],
        id="rules_reminder", replace_existing=True
    )
    scheduler.start()
    logger.info("Scheduler started")
