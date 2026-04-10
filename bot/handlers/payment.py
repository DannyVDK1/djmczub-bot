import uuid
import logging
import json
import aiohttp
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import SUBSCRIPTION_PLANS, YOOMONEY_TOKEN, YOOMONEY_WALLET, CHANNEL_ID
from bot.database import create_payment, confirm_payment, create_or_update_subscription, get_payment

router = Router()
logger = logging.getLogger(__name__)


def make_label(user_id: int, plan: str) -> str:
    """Короткий label до 64 символов для ЮМани"""
    return f"{user_id}_{plan}"


def generate_payment_url(user_id: int, plan: str, amount: int) -> str:
    """Ссылка quickpay — пользователь платит через браузер"""
    label = make_label(user_id, plan)
    comment = SUBSCRIPTION_PLANS[plan]['label']
    return (
        f"https://yoomoney.ru/quickpay/confirm"
        f"?receiver={YOOMONEY_WALLET}"
        f"&quickpay-form=button"
        f"&targets={comment}"
        f"&paymentType=AC"
        f"&sum={amount}"
        f"&label={label}"
    )


async def check_yoomoney_payment(user_id: int, plan: str, amount: int) -> bool:
    """
    Проверяем платёж через ЮМани API operation-history.
    Документация: https://yoomoney.ru/docs/wallet/user-account/operation-history
    Content-Type: application/x-www-form-urlencoded (ОБЯЗАТЕЛЬНО)
    Authorization: Bearer TOKEN
    """
    if not YOOMONEY_TOKEN or not YOOMONEY_WALLET:
        logger.error("YOOMONEY_TOKEN or YOOMONEY_WALLET not configured")
        return False

    label = make_label(user_id, plan)
    url = "https://yoomoney.ru/api/operation-history"
    headers = {
        "Authorization": f"Bearer {YOOMONEY_TOKEN}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    # Фильтруем по label — только входящие за последние 7 дней
    data = f"label={label}&type=deposition"

    logger.info(f"Checking YooMoney payment: label={label}, amount={amount}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=data) as resp:
                body = await resp.text()
                logger.info(f"YooMoney API response [{resp.status}]: {body[:300]}")

                if resp.status != 200:
                    logger.error(f"YooMoney API error: {resp.status} — {body}")
                    return False

                result = await resp.json(content_type=None)
                operations = result.get("operations", [])
                logger.info(f"Found {len(operations)} operations for label={label}")

                for op in operations:
                    op_status = op.get("status")
                    op_direction = op.get("direction")
                    op_amount = float(op.get("amount", 0))
                    op_label = op.get("label", "")

                    logger.info(f"Operation: status={op_status} dir={op_direction} amount={op_amount} label={op_label}")

                    if (op_status == "success"
                            and op_direction == "in"
                            and op_label == label
                            and op_amount >= amount * 0.99):
                        logger.info(f"Payment CONFIRMED for user {user_id} plan {plan}")
                        return True

                logger.info(f"Payment NOT found for label={label}")
                return False

    except Exception as e:
        logger.error(f"YooMoney check exception: {e}", exc_info=True)
        return False


@router.message(F.web_app_data)
async def handle_web_app_data(message: Message):
    """Получаем данные из Mini App"""
    logger.info(f"web_app_data received from user {message.from_user.id}: {message.web_app_data.data}")
    try:
        data = json.loads(message.web_app_data.data)
    except Exception as e:
        logger.error(f"web_app_data parse error: {e}")
        await message.answer("❌ Ошибка данных. Попробуйте ещё раз.")
        return

    action = data.get("action")
    plan_key = data.get("plan")
    user_id = message.from_user.id

    if action == "confirm_payment" and plan_key in SUBSCRIPTION_PLANS:
        await process_payment_check(message, user_id, plan_key)
    else:
        logger.warning(f"Unknown action: {action}")


async def process_payment_check(message: Message, user_id: int, plan_key: str):
    """Проверяем оплату и активируем подписку"""
    plan = SUBSCRIPTION_PLANS[plan_key]
    payment_id = f"{user_id}_{plan_key}_{int(datetime.now().timestamp())}"

    # Сохраняем в БД
    existing = await get_payment_by_user_plan(user_id, plan_key)
    if existing and existing["status"] == "confirmed":
        await message.answer("✅ Подписка уже активирована!")
        return

    await message.answer("⏳ Проверяю платёж в ЮМани...")

    is_paid = await check_yoomoney_payment(user_id, plan_key, plan["price"])

    if not is_paid:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="🔄 Проверить ещё раз",
                callback_data=f"recheck_{plan_key}"
            )
        ]])
        await message.answer(
            f"❌ <b>Платёж не найден</b>\n\n"
            f"Убедитесь что:\n"
            f"• Перевели ровно <b>{plan['price']} ₽</b>\n"
            f"• Оплата прошла успешно в ЮМани\n"
            f"• Прошло не менее 1-2 минут\n\n"
            f"Нажмите «Проверить ещё раз» через минуту.",
            reply_markup=keyboard
        )
        return

    # Создаём платёж и активируем
    await create_payment(user_id, plan_key, plan["price"], payment_id)
    payment = await get_payment(payment_id)
    if payment:
        await activate_subscription(message.from_user, payment, message.bot)


async def get_payment_by_user_plan(user_id: int, plan: str):
    """Проверяем есть ли уже подтверждённый платёж"""
    import aiosqlite
    async with aiosqlite.connect("data/bot.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM payments WHERE user_id=? AND plan=? AND status='confirmed' ORDER BY id DESC LIMIT 1",
            (user_id, plan)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


@router.callback_query(F.data.startswith("recheck_"))
async def recheck_payment(callback: CallbackQuery):
    """Повторная проверка платежа"""
    plan_key = callback.data.replace("recheck_", "")
    if plan_key not in SUBSCRIPTION_PLANS:
        await callback.answer("Неверный тариф", show_alert=True)
        return

    plan = SUBSCRIPTION_PLANS[plan_key]
    user_id = callback.from_user.id
    await callback.answer("Проверяю...")

    # Проверяем не активирована ли уже
    existing = await get_payment_by_user_plan(user_id, plan_key)
    if existing:
        await callback.message.edit_text("✅ Подписка уже активирована!")
        return

    is_paid = await check_yoomoney_payment(user_id, plan_key, plan["price"])

    if not is_paid:
        await callback.message.edit_text(
            f"❌ <b>Платёж всё ещё не найден</b>\n\n"
            f"Нужна сумма: <b>{plan['price']} ₽</b>\n\n"
            f"Если уверены что оплатили — напишите администратору.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔄 Проверить ещё раз", callback_data=f"recheck_{plan_key}")
            ]])
        )
        return

    payment_id = f"{user_id}_{plan_key}_{int(datetime.now().timestamp())}"
    await create_payment(user_id, plan_key, plan["price"], payment_id)
    payment = await get_payment(payment_id)
    if payment:
        await activate_subscription(callback.from_user, payment, callback.bot)
        await callback.message.edit_reply_markup(reply_markup=None)


async def activate_subscription(user, payment: dict, bot):
    """Активируем подписку и создаём инвайт"""
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

    # Создаём одноразовую ссылку в канал
    invite_url = None
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
        logger.error(f"Failed to create invite for user {user.id}: {e}")

    text = (
        f"🎉 <b>Подписка активирована!</b>\n\n"
        f"📦 Тариф: <b>{plan['label']}</b>\n"
        f"📅 Действует до: <b>{expires_at.strftime('%d.%m.%Y')}</b>\n\n"
    )

    if invite_url:
        text += (
            f"👇 <b>Ссылка для входа в канал:</b>\n"
            f"{invite_url}\n\n"
            f"⚠️ Ссылка одноразовая!"
        )
    else:
        text += "⚠️ Напишите администратору для получения ссылки."

    await bot.send_message(chat_id=user.id, text=text)
    logger.info(f"Subscription activated: user={user.id} plan={payment['plan']} until={expires_at}")
