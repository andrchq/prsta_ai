# 🤖 PRSTA AI Bot

Telegram-бот с доступом к AI моделям через OpenRouter и другие агрегаторы. Подписочная модель + внутренняя валюта.

## ⚡ Quick Install (на сервере)

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/andrchq/prsta_ai/main/setup.sh)
```

Или вручную:
```bash
git clone https://github.com/andrchq/prsta_ai.git
cd prsta_ai
bash setup.sh
```

## 🎮 Управление (`bai`)

| Команда | Описание |
|---------|----------|
| `bai update` | Git pull + пересборка + перезапуск |
| `bai start` / `stop` | Запуск / остановка |
| `bai restart` | Перезапуск бота |
| `bai status` | Статус контейнеров |
| `bai logs` | Логи бота (live) |
| `bai shell` | Bash в контейнере |
| `bai db-shell` | Консоль PostgreSQL |
| `bai backup-db` | Бэкап БД |
| `bai rebuild` | Полная пересборка |

## 🧠 Стек

- **Bot:** Aiogram 3.25
- **DB:** PostgreSQL + SQLAlchemy 2.0 (async)
- **AI:** LiteLLM → OpenRouter (GPT-4o, Claude, Gemini, Llama, DeepSeek)
- **Deploy:** Docker + Docker Compose

## 📁 Структура

```
app/
├── main.py              # Entrypoint
├── core/config.py       # Settings (.env)
├── database/            # Engine + session
├── models/              # User, Transaction, ChatSession, Subscription
├── middlewares/          # Auth, Throttling
├── handlers/            # /start, chat, models, ai_chat
└── services/            # ai_service (LiteLLM), billing (neurons)
```
