from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from bot.config import WEBHOOK_URL
from bot.database import get_subscription
from datetime import datetime

router = Router()
WEBAPP_URL = f"{WEBHOOK_URL}/webapp/"


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    sub = await get_subscription(user.id)

    if sub:
        expires = datetime.fromisoformat(sub["expires_at"])
        days_left = (expires - datetime.now()).days
        text = (
            f"👋 Привет, <b>{user.first_name}</b>!\n\n"
            f"✅ <b>Подписка активна</b>\n"
            f"📅 Истекает: <b>{expires.strftime('%d.%m.%Y')}</b> "
            f"(через {days_left} дн.)\n\n"
            f"🎵 Добро пожаловать в мир <b>{"DJ MC ZUB"}</b>!\n"
            f"Заходи в канал и наслаждайся эксклюзивным контентом."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🎵 Открыть приложение",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )],
        ])
    else:
        text = (
            f"👋 Привет, <b>{user.first_name}</b>!\n\n"
            f"🎵 <b>{"DJ MC ZUB"}</b>\n"
            "Закрытый канал DJ MC ZUB - музыка, лайвы, блог и закулисье\n\n"
            f"🔒 <b>Закрытый канал</b> - это:\n"
            f"• Эксклюзивные треки и миксы до релиза\n"
            f"• Лайвы и стримы каждую неделю\n"
            f"• Закулисье жизни DJ\n"
            f"• Закрытое комьюнити\n\n"
            f"💳 Подписка от <b>499 ₽/мес</b>\n"
            f"Оплата через ЮМани · Без автопродления"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🎵 Открыть и подписаться",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )]
        ])

    await message.answer(text, reply_markup=keyboard)
