from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from bot.config import WEBHOOK_URL
from bot.database import get_subscription
from datetime import datetime

router = Router()
WEBAPP_URL = f"{WEBHOOK_URL}/webapp/"

BOT_NAME = "DJ MC ZUB"
BOT_DESCRIPTION = "Zakrytyj kanal DJ MC ZUB - muzyka, lajvy, blog i zakulisie"


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    sub = await get_subscription(user.id)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🎵 Открыть DJ MC ZUB",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )
    ]])

    if sub:
        expires = datetime.fromisoformat(sub["expires_at"])
        days_left = (expires - datetime.now()).days
        text = (
            f"👋 С возвращением, <b>{user.first_name}</b>!\n\n"
            f"✅ Ваша подписка активна\n"
            f"📅 Тариф: <b>{sub['plan']}</b>\n"
            f"⏳ Осталось дней: <b>{days_left}</b>\n\n"
            f"Нажмите кнопку ниже чтобы открыть Mini App:"
        )
    else:
        text = (
            f"👋 Привет, <b>{user.first_name}</b>!\n\n"
            f"🎵 Добро пожаловать в мир <b>DJ MC ZUB</b>!\n\n"
            f"Здесь вы найдёте:\n"
            f"🎧 Эксклюзивные треки и миксы\n"
            f"📺 Прямые эфиры и лайвы\n"
            f"📸 Блог и закулисье\n\n"
            f"Оформите подписку чтобы получить доступ:"
        )

    await message.answer(text, reply_markup=keyboard)
