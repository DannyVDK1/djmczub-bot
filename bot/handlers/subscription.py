import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import Command
from bot.database import get_subscription
from bot.config import SUBSCRIPTION_PLANS, WEBHOOK_URL

router = Router()
logger = logging.getLogger(__name__)

PLAN_NAMES = {
    "1m": "1 месяц",
    "3m": "3 месяца",
    "6m": "6 месяцев",
    "12m": "12 месяцев",
}


def make_progress_bar(days_left: int, total_days: int) -> str:
    """Делаем визуальный прогресс-бар из 10 блоков"""
    if total_days <= 0:
        return "██████████"
    pct = max(0, min(1, days_left / total_days))
    filled = round(pct * 10)
    bar = "█" * filled + "░" * (10 - filled)
    return bar


@router.message(Command("subscription"))
async def cmd_subscription(message: Message):
    user_id = message.from_user.id
    sub = await get_subscription(user_id)

    if not sub:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="🎵 Оформить подписку",
                web_app=WebAppInfo(url=f"{WEBHOOK_URL}/webapp/")
            )
        ]])
        await message.answer(
            "❌ <b>У вас нет активной подписки</b>\n\n"
            "Оформите подписку чтобы получить "
            "доступ к закрытому каналу DJ MC ZUB 🎧",
            reply_markup=keyboard
        )
        return

    # Считаем дни
    expires_at = datetime.fromisoformat(sub["expires_at"])
    now = datetime.now()
    days_left = (expires_at - now).days
    plan_key = sub.get("plan", "1m")
    plan = SUBSCRIPTION_PLANS.get(plan_key, {})
    total_days = plan.get("days", 30)
    plan_name = PLAN_NAMES.get(plan_key, plan_key)

    # Прогресс-бар
    bar = make_progress_bar(days_left, total_days)
    pct = max(0, min(100, round(days_left / total_days * 100))) if total_days > 0 else 0

    # Статус
    if days_left > 7:
        status_icon = "✅"
        status_text = "Активна"
    elif days_left > 0:
        status_icon = "⚠️"
        status_text = "Истекает скоро"
    else:
        status_icon = "❌"
        status_text = "Истекла"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🎵 Оформить новую",
            web_app=WebAppInfo(url=f"{WEBHOOK_URL}/webapp/")
        )
    ]])

    text = (
        f"🎫 <b>Подписка DJ MC ZUB</b>\n\n"
        f"{status_icon} Статус: <b>{status_text}</b>\n"
        f"📋 Тариф: <b>{plan_name}</b>\n\n"
        f"📅 Действует до: <b>{expires_at.strftime('%d.%m.%Y')}</b>\n"
        f"⏳ Осталось: <b>{max(0, days_left)} дней</b>\n\n"
        f"📊 Прогресс:\n"
        f"<code>{bar}</code> {pct}%\n\n"
    )

    if days_left <= 7 and days_left > 0:
        text += "⚠️ Подписка скоро истекает! Оформите новую чтобы не потерять доступ."
    elif days_left <= 0:
        text += "❌ Подписка истекла. Оформите новую чтобы восстановить доступ."
    else:
        text += "🎵 Приятного просмотра!"

    await message.answer(text, reply_markup=keyboard)
