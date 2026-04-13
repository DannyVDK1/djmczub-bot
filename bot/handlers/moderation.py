import logging
import asyncio
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, ChatPermissions
from aiogram.filters import Command
from bot.database import get_db

router = Router()
logger = logging.getLogger(__name__)

CHAT_ID = -1003989707456

BANNED_KEYWORDS = {
    "политика": ["путин", "зеленский", "байден", "навальный", "политик", "выборы", "кремль",
        "война", "сво", "украина", "нато", "санкции", "оппозиция", "партия", "голосование"],
    "религия": ["аллах", "иисус", "христос", "джихад", "халяль", "библия", "коран",
        "церковь", "мечеть", "батюшка", "пастор", "религия", "атеист", "верующий"],
    "оскорбления": ["тупой", "идиот", "дебил", "урод", "мразь", "сволочь", "ублюдок",
        "козел", "скотина", "придурок", "кретин", "мудак", "ублюдок"],
    "спам": ["подписывайтесь на", "переходите по ссылке", "реклама", "куплю", "продам",
        "заработок", "инвестиции", "крипта", "казино", "ставки", "криптовалют"],
}

REASON_MESSAGES = {
    "политика": "Обсуждение политики запрещено в этом чате",
    "религия": "Обсуждение религии запрещено в этом чате",
    "оскорбления": "Оскорбления и нецензурная лексика запрещены",
    "спам": "Реклама и спам запрещены",
}

BAN_DURATIONS = [
    timedelta(days=1),
    timedelta(days=3),
    timedelta(days=7),
    None,
]


async def get_violations(user_id: int) -> dict:
    async with get_db() as db:
        async with db.execute(
            "SELECT warnings, bans FROM violations WHERE user_id=? AND chat_id=?",
            (user_id, CHAT_ID)
        ) as cur:
            row = await cur.fetchone()
            return {"warnings": row[0], "bans": row[1]} if row else {"warnings": 0, "bans": 0}


async def save_violations(user_id: int, warnings: int, bans: int):
    async with get_db() as db:
        await db.execute(
            """INSERT INTO violations (user_id, chat_id, warnings, bans, updated_at)
               VALUES (?,?,?,?,?)
               ON CONFLICT(user_id,chat_id) DO UPDATE SET
               warnings=excluded.warnings,bans=excluded.bans,updated_at=excluded.updated_at""",
            (user_id, CHAT_ID, warnings, bans, datetime.now().isoformat())
        )
        await db.commit()


def check_violations(text: str):
    if not text:
        return None
    t = text.lower()
    for category, keywords in BANNED_KEYWORDS.items():
        for kw in keywords:
            if kw in t:
                return REASON_MESSAGES[category]
    return None


async def warn_user(bot: Bot, message: Message, reason: str):
    user = message.from_user
    v = await get_violations(user.id)
    warnings = v["warnings"] + 1
    bans = v["bans"]
    await save_violations(user.id, warnings, bans)

    try:
        await message.delete()
    except Exception:
        pass

    if warnings < 3:
        remaining = 3 - warnings
        text = (
            f"⚠️ <b>{user.first_name}</b>, предупреждение <b>{warnings}/3</b>\n\n"
            f"📌 Причина: {reason}\n\n"
            f"❗ До блокировки осталось предупреждений: <b>{remaining}</b>\n"
            f"После 3 предупреждений последует ограничение доступа к чату."
        )
        msg = await bot.send_message(CHAT_ID, text)
        await asyncio.sleep(30)
        try:
            await msg.delete()
        except Exception:
            pass
    else:
        await save_violations(user.id, 0, bans)
        await apply_ban(bot, user, bans)


async def apply_ban(bot: Bot, user, ban_number: int):
    idx = min(ban_number, len(BAN_DURATIONS) - 1)
    duration = BAN_DURATIONS[idx]

    await save_violations(user.id, 0, ban_number + 1)

    if duration is None:
        await bot.ban_chat_member(chat_id=CHAT_ID, user_id=user.id)
        text = (
            f"🚫 <b>{user.first_name}</b> заблокирован в чате <b>навсегда</b>.\n\n"
            f"Это {ban_number + 1}-е серьёзное нарушение правил.\n"
            f"\n✅ Доступ к основному каналу DJ MC ZUB сохранён."
        )
    else:
        until = datetime.now() + duration
        await bot.restrict_chat_member(
            chat_id=CHAT_ID, user_id=user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until
        )
        dur_map = {1: "1 сутки", 3: "3 суток", 7: "1 неделю"}
        dur_str = dur_map.get(duration.days, f"{duration.days} дней")
        text = (
            f"🚫 <b>{user.first_name}</b> ограничен в чате на <b>{dur_str}</b>.\n\n"
            f"Это {ban_number + 1}-е нарушение после предупреждений.\n"
            f"Ограничение снимется: <b>{until.strftime('%d.%m.%Y в %H:%M')}</b>\n"
            f"\n✅ Доступ к основному каналу DJ MC ZUB сохранён."
        )

    msg = await bot.send_message(CHAT_ID, text)
    await asyncio.sleep(60)
    try:
        await msg.delete()
    except Exception:
        pass


async def is_admin(bot: Bot, user_id: int) -> bool:
    try:
        m = await bot.get_chat_member(CHAT_ID, user_id)
        return m.status in ["administrator", "creator"]
    except Exception:
        return False


@router.message(F.chat.id == CHAT_ID, F.text)
async def moderate_message(message: Message, bot: Bot):
    if not message.from_user:
        return
    if await is_admin(bot, message.from_user.id):
        return
    reason = check_violations(message.text or "")
    if reason:
        await warn_user(bot, message, reason)


@router.message(Command("warn"), F.chat.id == CHAT_ID)
async def cmd_warn(message: Message, bot: Bot):
    if not await is_admin(bot, message.from_user.id):
        return
    if not message.reply_to_message:
        await message.reply("Ответьте на сообщение пользователя командой /warn [причина]")
        return
    parts = message.text.split(maxsplit=1)
    reason = parts[1] if len(parts) > 1 else "Нарушение правил чата"
    await warn_user(bot, message.reply_to_message, reason)
    try:
        await message.delete()
    except Exception:
        pass


@router.message(Command("violations"), F.chat.id == CHAT_ID)
async def cmd_violations(message: Message, bot: Bot):
    if not await is_admin(bot, message.from_user.id):
        return
    if not message.reply_to_message:
        await message.reply("Ответьте на сообщение пользователя")
        return
    target = message.reply_to_message.from_user
    v = await get_violations(target.id)
    await message.reply(
        f"📊 Нарушения <b>{target.first_name}</b>:\n"
        f"⚠️ Предупреждений: {v['warnings']}/3\n"
        f"🚫 Блокировок: {v['bans']}"
    )


@router.message(Command("resetwarn"), F.chat.id == CHAT_ID)
async def cmd_resetwarn(message: Message, bot: Bot):
    if not await is_admin(bot, message.from_user.id):
        return
    if not message.reply_to_message:
        await message.reply("Ответьте на сообщение пользователя")
        return
    target = message.reply_to_message.from_user
    await save_violations(target.id, 0, 0)
    await message.reply(f"✅ Предупреждения <b>{target.first_name}</b> сброшены")
