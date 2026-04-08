import uuid
import logging
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
    """Генерируем ссылку на оплату ЮМани"""
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


@router.callback_query(F.data.startswith("pay_"))
async def process_payment_callback(callback: CallbackQuery):
    plan_key = callback.data.replace("pay_", "")
    plan = SUBSCRIPTION_PLANS.get(plan_key)
    if not plan:
        await callback.answer("Неверный тариф")
        return

    user_id = callback.from_user.id
    payment_id = str(uuid.uuid4())

    await create_payment(user_id, plan_key, plan["price"], payment_id)

    pay_url = generate_payment_url(user_id, plan_key, plan["price"], payment_id)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💳 Оплатить {plan['price']} ₽", url=pay_url)],
        [InlineKeyboardButton(text="✅ Я оплатил — проверить", callback_data=f"check_{payment_id}")]
    ])

    await callback.message.answer(
        f"💳 <b>Оплата подписки</b>\n\n"
        f"Тариф: <b>{plan['label']}</b>\n"
        f"Сумма: <b>{plan['price']} ₽</b>\n\n"
        f"1. Нажми «Оплатить» — откроется ЮМани\n"
        f"2. После оплаты нажми «Я оплатил — проверить»\n\n"
        f"⚠️ После оплаты нажми кнопку проверки — доступ откроется автоматически.",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data.startswith("check_"))
async def check_payment(callback: CallbackQuery, bot):
    payment_id = callback.data.replace("check_", "")
    payment = await get_payment(payment_id)

    if not payment:
        await callback.answer("Платёж не найден", show_alert=True)
        return

    if payment["status"] == "confirmed":
        await callback.answer("Подписка уже активирована! ✅", show_alert=True)
        return

    # TODO: здесь будет проверка через ЮМани API
    # Пока — заглушка для тестирования
    await activate_subscription(callback.from_user, payment, bot)
    await callback.answer("✅ Подписка активирована!", show_alert=True)


async def activate_subscription(user, payment: dict, bot):
    """Активируем подписку и добавляем в канал"""
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

    # Создаём инвайт-ссылку в канал
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
        f"Тариф: <b>{plan['label']}</b>\n"
        f"Действует до: <b>{expires_at.strftime('%d.%m.%Y')}</b>\n\n"
    )
    if invite_url:
        text += f"👇 <b>Ссылка для входа в канал:</b>\n{invite_url}\n\n"
        text += "⚠️ Ссылка одноразовая — использовать только один раз!"
    else:
        text += "⚠️ Не удалось создать ссылку — напишите администратору."

    await bot.send_message(chat_id=user.id, text=text)
    logger.info(f"Subscription activated for user {user.id}, plan {payment['plan']}")
