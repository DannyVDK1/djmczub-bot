import uuid
import logging
import json
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.config import SUBSCRIPTION_PLANS, YOOMONEY_WALLET, CHANNEL_ID, WEBHOOK_URL
from bot.database import (
    create_payment, confirm_payment,
    create_or_update_subscription, get_payment
)

router = Router()
logger = logging.getLogger(__name__)


def generate_payment_url(user_id: int, plan: str, amount: int, payment_id: str) -> str:
    label = f"{user_id}_{plan}_{payment_id[:8]}"
    comment = f"Подписка DJ MC ZUB — {SUBSCRIPTION_PLANS[plan]['label']}"
    return (
        f"https://yoomoney.ru/quickpay/confirm?"
        f"receiver={YOOMONEY_WALLET}"
        f"&quickpay-form=button"
        f"&targets={comment}"
        f"&paymentType=AC"
        f"&sum={amount}"
        f"&label={label}"
    )


@router.message(F.web_app_data)
async def handle_web_app_data(message: Message, bot=None):
    """Обработчик данных из Mini App — пользователь выбрал тариф"""
    try:
        data = json.loads(message.web_app_data.data)
        action = data.get("action")
        plan_key = data.get("plan")
    except Exception:
        await message.answer("❌ Ошибка при обработке данных. Попробуйте ещё раз.")
        return

    if action != "pay" or plan_key not in SUBSCRIPTION_PLANS:
        await message.answer("❌ Неверный тариф.")
        return

    plan = SUBSCRIPTION_PLANS[plan_key]
    user_id = message.from_user.id
    payment_id = str(uuid.uuid4())

    await create_payment(user_id, plan_key, plan["price"], payment_id)

    # Если кошелёк ЮМани не настроен — тестовый режим
    if not YOOMONEY_WALLET or YOOMONEY_WALLET == "":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Активировать (тест)",
                callback_data=f"check_{payment_id}"
            )]
        ])
        await message.answer(
            f"🧪 <b>Тестовый режим оплаты</b>\n\n"
            f"Тариф: <b>{plan['label']}</b>\n"
            f"Сумма: <b>{plan['price']} ₽</b>\n\n"
            f"ЮМани пока не подключены.\n"
            f"Нажми кнопку чтобы активировать тестовую подписку.",
            reply_markup=keyboard
        )
        return

    pay_url = generate_payment_url(user_id, plan_key, plan["price"], payment_id)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💳 Оплатить {plan['price']} ₽ через ЮМани", url=pay_url)],
        [InlineKeyboardButton(text="✅ Я оплатил — проверить", callback_data=f"check_{payment_id}")]
    ])

    await message.answer(
        f"💳 <b>Оплата подписки</b>\n\n"
        f"Тариф: <b>{plan['label']}</b>\n"
        f"Сумма: <b>{plan['price']} ₽</b>\n\n"
        f"1️⃣ Нажми <b>«Оплатить»</b> — откроется ЮМани\n"
        f"2️⃣ Переведи точную сумму\n"
        f"3️⃣ Вернись и нажми <b>«Я оплатил»</b>\n\n"
        f"⚡ Доступ откроется автоматически после проверки.",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("check_"))
async def check_payment(callback: CallbackQuery, bot=None):
    payment_id = callback.data.replace("check_", "")
    payment = await get_payment(payment_id)

    if not payment:
        await callback.answer("Платёж не найден", show_alert=True)
        return

    if payment["status"] == "confirmed":
        await callback.answer("✅ Подписка уже активирована!", show_alert=True)
        return

    if payment["user_id"] != callback.from_user.id:
        await callback.answer("❌ Это не ваш платёж", show_alert=True)
        return

    # TODO: здесь проверка через ЮМани API по label
    # Пока активируем сразу (тест)
    await activate_subscription(callback.from_user, payment, callback.bot)
    await callback.answer("🎉 Подписка активирована!", show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=None)


async def activate_subscription(user, payment: dict, bot):
    plan = SUBSCRIPTION_PLANS[payment["plan"]]
    expires_at = datetime.now() + timedelta(days=plan["days"])

    await confirm_payment(payment["payment_id"])
    await create_or_update_subscription(
        user_id=user.id,
        username=user.username or "",
        plan=payment["plan"],
        expires_at=expires_at,
        payment_id=payment["payment_id"]
    )

    try:
        invite = await bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
            expire_date=int(expires_at.timestamp())
        )
        invite_url = invite.invite_link
    except Exception as e:
        logger.error(f"Failed to create invite: {e}")
        invite_url = None

    text = (
        f"🎉 <b>Подписка активирована!</b>\n\n"
        f"📦 Тариф: <b>{plan['label']}</b>\n"
        f"📅 Действует до: <b>{expires_at.strftime('%d.%m.%Y')}</b>\n\n"
    )

    if invite_url:
        text += (
            f"👇 <b>Твоя ссылка для входа в канал:</b>\n"
            f"{invite_url}\n\n"
            f"⚠️ Ссылка одноразовая — используй только один раз!"
        )
    else:
        text += "⚠️ Не удалось создать ссылку — напиши администратору."

    await bot.send_message(chat_id=user.id, text=text)
    logger.info(f"Subscription activated: user={user.id} plan={payment['plan']}")
