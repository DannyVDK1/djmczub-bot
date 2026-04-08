# 🎵 DJ MC ZUB — Telegram Bot

Бот с Mini App для продажи подписки на закрытый Telegram канал.  
Оплата через ЮМани. Автоматический кик при истечении подписки.

## Стек
- Python 3.11 + aiogram 3
- SQLite (aiosqlite)
- aiohttp (webhook сервер)
- APScheduler (проверка подписок)
- Render.com (хостинг)

## Деплой на Render.com

### 1. Создай репозиторий на GitHub и залей код

### 2. Зарегистрируйся на render.com

### 3. New → Web Service → Connect GitHub repo

### 4. Настрой переменные окружения (Environment Variables):
```
BOT_TOKEN      = твой_токен_от_BotFather
ADMIN_ID       = твой_telegram_id (узнать у @userinfobot)
CHANNEL_ID     = id_закрытого_канала (отрицательное число, узнать у @username_to_id_bot)
WEBHOOK_URL    = https://djmczub-bot.onrender.com  (твой URL на Render — появится после деплоя)
```

### 5. После деплоя — скопируй URL (например https://djmczub-bot.onrender.com)
   Вставь его в WEBHOOK_URL и передеплой.

### 6. UptimeRobot — чтобы бот не засыпал
- Зарегистрируйся на uptimerobot.com
- New Monitor → HTTP(s)
- URL: https://djmczub-bot.onrender.com/ping
- Интервал: 5 минут

### 7. Настрой бота как админа канала
- Добавь бота в закрытый канал как администратора
- Дай права: добавлять участников, удалять участников

## Команды бота
- `/start` — приветствие + открытие Mini App
- `/subscription` — статус подписки
- `/stats` — статистика (только для ADMIN_ID)
- `/broadcast текст` — рассылка всем активным (только для ADMIN_ID)

## Структура
```
bot/
  main.py          # запуск
  config.py        # конфиг
  database.py      # SQLite
  scheduler.py     # проверка истёкших подписок
  handlers/
    start.py       # /start
    payment.py     # оплата
    subscription.py # /subscription
    admin.py       # /stats, /broadcast
webapp/
  index.html       # Mini App главный экран
render.yaml        # конфиг Render
```

## ЮМани (добавить позже)
1. Зарегистрируй кошелёк на yoomoney.ru
2. Получи токен в настройках → API
3. Добавь YOOMONEY_TOKEN и YOOMONEY_WALLET в переменные окружения Render
