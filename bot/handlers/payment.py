import uuid
import logging
import json
import aiohttp
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.config import SUBSCRIPTION_PLANS, YOOMONEY_TOKEN, YOOMONEY_WALLET, CHANNEL_ID
from bot.database import (
    create_payment, confirm_payment,
    create_or_update_subscription, get_payment
)

router = Router()
logger = logging.getLogger(__name__)


def generate_payment_url(user_id: int, plan: str, amount: int, payment_id: str) -> str:
    """Генерируем ссылку на быструю оплату ЮМани"""
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


async def check_yoomoney_payment(label: str, amount: int) -> bool:
    """Проверяем платёж через ЮМани API по label"""
    if not YOOMONEY_TOKEN:
        logger.warning("YOOMONEY_TOKEN not set")
        return False

    url = "https://yoomoney.ru/api/operation-history"
    headers = {"Authorization": f"Bearer {YOOMONEY_TOKEN}"}
    data = {"label": label, "details": True}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=data) as resp:
                if resp.status != 200:
                    logger.error(f"YooMoney API error: {resp.status}")
                    return False
                result = await resp.json()
                operations = result.get("operations", [])
                logger.info(f"YooMoney operations for label {label}: {len(operations)}")

                for op in operations:
                    if (op.get("status") == "success" and
                        op.get("direction") == "in" and
                        float(op.get("amount", 0)) >= amount * 0.99):  # допуск 1% на комиссию
                        logger.info(f"Payment confirmed: {op}")
                        return True
                return False
    except Exception as e:
        logger.error(f"YooMoney check error: {e}")
        return False


@router.message(F.web_app_data)
async def handle_web_app_data(message: Message):
    """Получаем данные из Mini App — пользователь подтвердил оплату"""
    try:
        data = json.loads(message.web_app_data.data)
        action = data.get("action")
        plan_key = data.get("plan")
        payment_id = data.get("payment_id", "")
        user_id = data.get("user_id", message.from_user.id)
    except Exception as e:
        logger.error(f"web_app_data parse error: {e}")
        await message.answer("❌ Ошибка при обработке данных. Попробуйте ещё раз.")
        return

    if action == "confirm_payment":
        await process_payment_confirmation(message, plan_key, payment_id)
    else:
        await message.answer("❌ Неизвестное действие.")


async def process_payment_confirmation(message: Message, plan_key: str, payment_id: str):
    """Проверяем оплату и активируем подписку"""
    if plan_key not in SUBSCRIPTION_PLANS:
        await message.answer("❌ Неверный тариф.")
        return

    plan = SUBSCRIPTION_PLANS[plan_key]
    user_id = message.from_user.id

    # Сохраняем платёж в БД если не сохранён
    payment = await get_payment(payment_id)
    if not payment:
        await create_payment(user_id, plan_key, plan["price"], payment_id)
        payment = await get_payment(payment_id)

    if payment and payment["status"] == "confirmed":
        await message.answer("✅ Подписка уже активирована!")
        return

    # Проверяем платёж через ЮМани API
    label = payment_id
    await message.answer("⏳ Проверяю платёж в ЮМани...")

    is_paid = await check_yoomoney_payment(label, plan["price"])

    if not is_paid:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="🔄 Проверить ещё раз",
                callback_data=f"recheck_{plan_key}_{payment_id}"
            )
        ]])
        await message.answer(
            f"❌ <b>Платёж не найден</b>\n\n"
            f"Возможные причины:\n"
            f"• Платёж ещё обрабатывается (подождите 1-2 мин)\n"
            f"• Оплата не была совершена\n"
            f"• Неверная сумма — нужно ровно <b>{plan['price']} ₽</b>\n\n"
            f"Попробуй нажать «Проверить ещё раз» через минуту.",
            reply_markup=keyboard
        )
        return

    # Платёж подтверждён — активируем
    await activate_subscription(message.from_user, payment, message.bot)


@router.callback_query(F.data.startswith("recheck_"))
async def recheck_payment(callback: CallbackQuery):
    """Повторная проверка платежа"""
    parts = callback.data.replace("recheck_", "").split("_", 1)
    if len(parts) != 2:
        await callback.answer("Ошибка", show_alert=True)
        return

    plan_key, payment_id = parts[0], parts[1]

    if plan_key not in SUBSCRIPTION_PLANS:
        await callback.answer("Неверный тариф", show_alert=True)
        return

    plan = SUBSCRIPTION_PLANS[plan_key]
    await callback.answer("Проверяю...")

    payment = await get_payment(payment_id)
    if payment and payment["status"] == "confirmed":
        await callback.message.edit_text("✅ Подписка уже активирована!")
        return

    is_paid = await check_yoomoney_payment(payment_id, plan["price"])

    if not is_paid:
        await callback.message.edit_text(
            f"❌ <b>Платёж всё ещё не найден</b>\n\n"
            f"Убедитесь что перевели ровно <b>{plan['price']} ₽</b> на кошелёк DJ MC ZUB.\n\n"
            f"Если уверены что оплатили — напишите @admin.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔄 Проверить ещё раз", callback_data=f"recheck_{plan_key}_{payment_id}")
            ]])
        )
        return

    if not payment:
        await create_payment(callback.from_user.id, plan_key, plan["price"], payment_id)
        payment = await get_payment(payment_id)

    await activate_subscription(callback.from_user, payment, callback.bot)
    await callback.message.edit_reply_markup(reply_markup=None)


async def activate_subscription(user, payment: dict, bot):
    """Активируем подписку и отправляем инвайт в канал"""
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

    # Генерируем одноразовую инвайт-ссылку в канал
    try:
        invite = await bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
            expire_date=int(expires_at.timestamp()),
            name=f"sub_{user.id}"
        )
        invite_url = invite.invite_link
        logger.info(f"Invite created for user {user.id}: {invite_url}")
    except Exception as e:
        logger.error(f"Failed to create invite for {user.id}: {e}")
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
            f"⚠️ Ссылка одноразовая — используй только один раз!\n"
            f"После входа ты будешь в канале до {expires_at.strftime('%d.%m.%Y')}."
        )
    else:
        text += "⚠️ Не удалось создать ссылку автоматически — напиши администратору."

    await bot.send_message(chat_id=user.id, text=text)
    logger.info(f"Subscription activated: user={user.id} plan={payment['plan']} expires={expires_at}")
