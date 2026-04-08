from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from datetime import datetime

from bot.database import get_subscription
from bot.config import WEBHOOK_URL

router = Router()


@router.message(Command("subscription"))
async def cmd_subscription(message: Message):
    sub = await get_subscription(message.from_user.id)

    if not sub:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="🎵 Оформить подписку",
                web_app=WebAppInfo(url=f"{WEBHOOK_URL}/webapp/")
            )
        ]])
        await message.answer(
            "❌ <b>У вас нет активной подписки</b>\n\n"
            "Оформите подписку, чтобы получить доступ к закрытому каналу DJ MC ZUB.",
            reply_markup=keyboard
        )
        return

    expires = datetime.fromisoformat(sub["expires_at"])
    days_left = (expires - datetime.now()).days

    plans = {"1m": "1 месяц", "3m": "3 месяца", "6m": "6 месяцев", "12m": "12 месяцев"}
    plan_name = plans.get(sub["plan"], sub["plan"])

    status_emoji = "✅" if days_left > 7 else "⚠️"

    await message.answer(
        f"{status_emoji} <b>Ваша подписка</b>\n\n"
        f"📦 Тариф: <b>{plan_name}</b>\n"
        f"📅 Истекает: <b>{expires.strftime('%d.%m.%Y')}</b>\n"
        f"⏳ Осталось: <b>{days_left} дней</b>\n\n"
        f"{'⚠️ Скоро истекает! Продлите подписку.' if days_left <= 7 else '🎵 Приятного прослушивания!'}"
    )
