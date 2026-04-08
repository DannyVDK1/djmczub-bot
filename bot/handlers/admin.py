from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from bot.config import ADMIN_ID
from bot.database import get_all_active_users
import aiosqlite

router = Router()

DB_PATH = "data/bot.db"


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM subscriptions WHERE is_active=1") as c:
            active = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM subscriptions") as c:
            total = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM payments WHERE status='confirmed'") as c:
            paid = (await c.fetchone())[0]
        async with db.execute("SELECT SUM(amount) FROM payments WHERE status='confirmed'") as c:
            revenue = (await c.fetchone())[0] or 0

    await message.answer(
        f"📊 <b>Статистика DJ MC ZUB бота</b>\n\n"
        f"👥 Активных подписок: <b>{active}</b>\n"
        f"📦 Всего подписок: <b>{total}</b>\n"
        f"💳 Оплачено: <b>{paid}</b>\n"
        f"💰 Выручка: <b>{revenue:,} ₽</b>"
    )


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, bot):
    if not is_admin(message.from_user.id):
        return

    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await message.answer("Использование: /broadcast Текст сообщения")
        return

    users = await get_all_active_users()
    sent, failed = 0, 0

    await message.answer(f"📤 Рассылка для {len(users)} пользователей...")

    for user_id in users:
        try:
            await bot.send_message(user_id, text)
            sent += 1
        except Exception:
            failed += 1

    await message.answer(
        f"✅ Рассылка завершена\n"
        f"Отправлено: {sent}\nОшибок: {failed}"
    )
