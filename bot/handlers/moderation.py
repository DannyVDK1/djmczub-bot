import logging
import asyncio
import os
import aiosqlite
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, ChatPermissions
from aiogram.filters import Command

router = Router()
logger = logging.getLogger(__name__)

CHAT_ID = -1003989707456
DB_PATH = "data/bot.db"

BANNED_KEYWORDS = {
    "политика": ["путин", "зеленский", "байден", "навальный", "политик", "выборы", "кремль",
        "война", "сво", "нато", "санкции", "оппозиция", "голосование"],
    "религия": ["аллах", "иисус", "христос", "джихад", "халяль", "библия", "коран",
        "церковь", "мечеть", "батюшка", "пастор", "религия", "атеист"],
    "оскорбления": ["тупой", "идиот", "дебил", "урод", "мразь", "сволочь", "ублюдок",
        "козел", "скотина", "придурок", "кретин"],
    "спам": ["подписывайтесь на", "переходите по ссылке", "куплю", "продам",
        "заработок", "инвестиции", "крипта", "казино", "ставки"],
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
    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("""
            CREATE TABLE IF NOT EXISTS violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                warnings INTEGER DEFAULT 0,
                bans INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, chat_id)
            )
        """)
        await db.commit()
        async with db.execute(
            "SELECT warnings, bans FROM violations WHERE user_id=? AND chat_id=?",
            (user_id, CHAT_ID)
        ) as cur:
            row = await cur.fetchone()
            return {"warnings": row[0], "bans": row[1]} if row else {"warnings": 0, "bans": 0}


async def save_violations(user_id: int, warnings: int, bans: int):
    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                warnings INTEGER DEFAULT 0,
                bans INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, chat_id)
            )
        """)
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


async def is_admin(bot: Bot, user_id: int) -> bool:
    try:
        m = await bot.get_chat_member(CHAT_ID, user_id)
        return m.status in ["administrator", "creator"]
    except Exception:
        return False


async def warn_user(bot: Bot, message: Message, reason: str):
    user = message.from_user
    v = await get_violations(user.id)
    warnings = v["warnings"] + 1
    bans = v["bans"]

    try:
        await message.delete()
    except Exception:
        pass

    if warnings < 3:
        await save_violations(user.id, warnings, bans)
        remaining = 3 - warnings
        text = (
            f"\u26a0\ufe0f <b>{user.first_name}</b>, предупреждение <b>{warnings}/3</b>\n\n"
            f"\U0001f4cc Причина: {reason}\n\n"
            f"\u2757 До блокировки: <b>{remaining}</b> предупр.\n"
            f"После 3 предупреждений — ограничение доступа."
        )
        msg = await bot.send_message(CHAT_ID, text)
        await asyncio.sleep(30)
        try:
            await bot.delete_message(CHAT_ID, msg.message_id)
        except Exception:
            pass
    else:
        # 3 предупреждения — баним
        await save_violations(user.id, 0, bans)
        await apply_ban(bot, user, bans)


async def apply_ban(bot: Bot, user, ban_number: int):
    idx = min(ban_number, len(BAN_DURATIONS) - 1)
    duration = BAN_DURATIONS[idx]
    await save_violations(user.id, 0, ban_number + 1)

    if duration is None:
        await bot.ban_chat_member(chat_id=CHAT_ID, user_id=user.id)
        text = (
            f"\U0001f6ab <b>{user.first_name}</b> заблокирован в чате <b>навсегда</b>.\n\n"
            f"Это {ban_number + 1}-е серьёзное нарушение.\n"
            f"\u2705 Доступ к основному каналу сохранён."
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
            f"\U0001f6ab <b>{user.first_name}</b> ограничен на <b>{dur_str}</b>.\n\n"
            f"Нарушение {ban_number + 1} после предупреждений.\n"
            f"Снимется: <b>{until.strftime('%d.%m.%Y %H:%M')}</b>\n"
            f"\u2705 Доступ к каналу сохранён."
        )

    msg = await bot.send_message(CHAT_ID, text)
    await asyncio.sleep(60)
    try:
        await bot.delete_message(CHAT_ID, msg.message_id)
    except Exception:
        pass


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
        await message.reply("Используйте: /warn [причина] — ответом на сообщение")
        return
    parts = message.text.split(maxsplit=1)
    reason = parts[1] if len(parts) > 1 else "Нарушение правил"
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
        f"\U0001f4ca Нарушения <b>{target.first_name}</b>:\n"
        f"\u26a0\ufe0f Предупреждений: {v['warnings']}/3\n"
        f"\U0001f6ab Блокировок: {v['bans']}"
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
    await message.reply(f"\u2705 Предупреждения <b>{target.first_name}</b> сброшены")
