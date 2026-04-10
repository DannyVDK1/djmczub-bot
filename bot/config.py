import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_PATH = "/bot/webhook"
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.getenv("PORT", "10000"))

# ЮМани
YOOMONEY_TOKEN = os.getenv("YOOMONEY_TOKEN", "")
YOOMONEY_WALLET = os.getenv("YOOMONEY_WALLET", "")

SUBSCRIPTION_PLANS = {
    "1m":  {"days": 30,  "price": 499,  "label": "1 месяц"},
    "3m":  {"days": 90,  "price": 1197, "label": "3 месяца"},
    "6m":  {"days": 180, "price": 1974, "label": "6 месяцев"},
    "12m": {"days": 365, "price": 2988, "label": "12 месяцев"},
}

BOT_NAME = "DJ MC ZUB"
BOT_DESCRIPTION = "Евгений Шестаков — музыка, лайвы, блог"
