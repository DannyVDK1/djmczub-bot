import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
YOOMONEY_TOKEN = os.getenv("YOOMONEY_TOKEN", "")
YOOMONEY_WALLET = os.getenv("YOOMONEY_WALLET", "4100116898751593")

WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.getenv("PORT", "10000"))

# Тарифы: базовая цена 149 руб/мес
SUBSCRIPTION_PLANS = {
    "1m": {
        "name": "1 месяц",
        "months": 1,
        "price": 149,
        "per_month": 149,
        "discount": 0,
        "label": "Подписка DJ MC ZUB 1 месяц",
    },
    "3m": {
        "name": "3 месяца",
        "months": 3,
        "price": 357,
        "per_month": 119,
        "discount": 20,
        "label": "Подписка DJ MC ZUB 3 месяца",
    },
    "6m": {
        "name": "6 месяцев",
        "months": 6,
        "price": 591,
        "per_month": 98,
        "discount": 34,
        "label": "Подписка DJ MC ZUB 6 месяцев",
    },
    "12m": {
        "name": "12 месяцев",
        "months": 12,
        "price": 894,
        "per_month": 74,
        "discount": 50,
        "label": "Подписка DJ MC ZUB 12 месяцев",
    },
}
