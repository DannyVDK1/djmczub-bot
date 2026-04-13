import aiosqlite
import logging
from datetime import datetime

DB_PATH = "data/bot.db"
logger = logging.getLogger(__name__)



from contextlib import asynccontextmanager

@asynccontextmanager
async def get_db():
    import os
    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db

async def init_db():
    import os
    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                plan        TEXT,
                started_at  TEXT,
                expires_at  TEXT,
                is_active   INTEGER DEFAULT 1,
                payment_id  TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                plan        TEXT,
                amount      INTEGER,
                payment_id  TEXT UNIQUE,
                status      TEXT DEFAULT 'pending',
                created_at  TEXT
            )
        """)
        await db.commit()
    logger.info("Database initialized")


async def get_subscription(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM subscriptions WHERE user_id = ? AND is_active = 1",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_or_update_subscription(user_id: int, username: str, plan: str,
                                         expires_at: datetime, payment_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO subscriptions (user_id, username, plan, started_at, expires_at, is_active, payment_id)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                plan=excluded.plan,
                started_at=excluded.started_at,
                expires_at=excluded.expires_at,
                is_active=1,
                payment_id=excluded.payment_id
        """, (user_id, username, plan,
              datetime.now().isoformat(),
              expires_at.isoformat(),
              payment_id))
        await db.commit()


async def deactivate_subscription(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE subscriptions SET is_active = 0 WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()


async def get_expired_subscriptions() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        now = datetime.now().isoformat()
        async with db.execute("""
            SELECT * FROM subscriptions
            WHERE is_active = 1 AND expires_at <= ?
        """, (now,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def create_payment(user_id: int, plan: str, amount: int, payment_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR IGNORE INTO payments (user_id, plan, amount, payment_id, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, plan, amount, payment_id, datetime.now().isoformat()))
        await db.commit()


async def get_payment(payment_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM payments WHERE payment_id = ?", (payment_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def confirm_payment(payment_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE payments SET status = 'confirmed' WHERE payment_id = ?",
            (payment_id,)
        )
        await db.commit()


async def get_all_active_users() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id FROM subscriptions WHERE is_active = 1"
        ) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]
