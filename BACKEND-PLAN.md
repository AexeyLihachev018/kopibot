# BACKEND-PLAN.md — SaaS White Label платформа для копирайтеров

---

## Мои решения по открытым вопросам

### 3. Оплата (рекомендация)
**ЮКасса** для российского рынка.
- Копирайтер платит платформе за подписку (ежемесячно, авто-продление)
- Платформа централизованно платит OpenRouter за API
- Клиенты копирайтера платят ему напрямую вне платформы (не в боте) — упрощает MVP

### 5. White Label — что кастомизируется (рекомендация)
| Параметр | Как меняется | Кто делает |
|---|---|---|
| Имя бота | Через BotFather | Копирайтер |
| Аватар бота | Telegram API (setMyPhoto) | Платформа через токен |
| Описание бота | Telegram API (setMyDescription) | Платформа через токен |
| Приветственное сообщение /start | Хранится в БД, платформа отправляет | Копирайтер настраивает |
| Список команд /help | Хранится в БД | Копирайтер настраивает |
| Стиль генерации AI | JSON профиль (как в текущем боте) | Копирайтер загружает архив |

### 6. Тарифы (рекомендация)
| Тариф | Цена | Генераций/месяц | Клиентов | Контент-планов |
|---|---|---|---|---|
| Free | 0 ₽ | 10 | до 5 | 1 |
| Basic | 990 ₽/мес | 100 | до 50 | 10 |
| Pro | 2 990 ₽/мес | безлимит | безлимит | безлимит |

Лимиты сбрасываются 1-го числа каждого месяца.

---

## 1. Архитектура системы

```
┌─────────────────────────────────────────────────┐
│              ПЛАТФОРМА (бэкенд)                 │
│                                                 │
│  ┌──────────────┐    ┌────────────────────┐     │
│  │  Platform    │    │   Bot Manager      │     │
│  │  API         │    │   (управляет N     │     │
│  │  (FastAPI)   │    │    ботами сразу)   │     │
│  └──────┬───────┘    └────────┬───────────┘     │
│         │                    │                  │
│  ┌──────▼────────────────────▼──────────┐       │
│  │         PostgreSQL база данных       │       │
│  └──────────────────────────────────────┘       │
│                                                 │
│  ┌─────────────┐   ┌──────────────────────┐     │
│  │  ЮКасса     │   │  OpenRouter API      │     │
│  │  (платежи)  │   │  (AI генерация)      │     │
│  └─────────────┘   └──────────────────────┘     │
└─────────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
  Telegram бот         Telegram бот
  Копирайтера А        Копирайтера Б
  @brand_a_bot         @brand_b_bot
         │                    │
    Клиенты А           Клиенты Б
```

**Ключевой принцип:** один бэкенд процесс управляет всеми ботами одновременно
через aiogram multi-bot (один dispatcher, N Bot-инстансов).

---

## 2. Роли и доступы

### Копирайтер (регистрируется на платформе)
- Регистрируется через **платформенного бота** (`@platform_saas_bot`)
- Вводит свой Telegram-токен от BotFather
- Загружает стилевой профиль (архив постов)
- Настраивает приветствие и описание своего бота
- Видит список своих клиентов
- Видит статистику генераций
- Управляет подпиской (оплата)

### Клиент копирайтера
- Открывает бот своего копирайтера
- `/start` → подключение, получает приветствие
- `/написать` → заказывает текст (вводит тему)
- `/история` → список своих готовых текстов
- `/заказы` → текущие/последние заказы
- Не знает о платформе, видит только брендированный бот

### Суперадмин
- Веб-панель (отдельный URL, Basic Auth)
- Видит всех копирайтеров, их статусы и тарифы
- Видит сводную статистику (активных ботов, генераций за месяц)
- Может отключить аккаунт копирайтера
- Видит ошибки и логи

---

## 3. База данных (PostgreSQL)

### Таблица: `copywriters`
```sql
id                  UUID PRIMARY KEY
email               VARCHAR UNIQUE NOT NULL
password_hash       VARCHAR NOT NULL
telegram_user_id    BIGINT UNIQUE        -- Telegram ID в платформенном боте
display_name        VARCHAR              -- "Алексей — копирайтер"
plan                ENUM('free','basic','pro') DEFAULT 'free'
plan_expires_at     TIMESTAMP
generations_used    INT DEFAULT 0        -- счётчик текущего месяца
generations_reset_at TIMESTAMP           -- когда сбрасывать счётчик
yookassa_customer_id VARCHAR
is_active           BOOLEAN DEFAULT true
created_at          TIMESTAMP
```

### Таблица: `bots`
```sql
id                  UUID PRIMARY KEY
copywriter_id       UUID REFERENCES copywriters
bot_token           VARCHAR ENCRYPTED      -- токен от BotFather (шифруем)
bot_username        VARCHAR                -- @brand_bot
bot_name            VARCHAR                -- "Копирайтер Алексей"
welcome_message     TEXT                   -- текст /start
help_message        TEXT                   -- текст /help
style_guide         JSONB                  -- стилевой профиль AI
content_plan        JSONB                  -- контент-план
is_active           BOOLEAN DEFAULT false  -- false пока токен не проверен
created_at          TIMESTAMP
```

### Таблица: `clients`
```sql
id                  UUID PRIMARY KEY
bot_id              UUID REFERENCES bots
copywriter_id       UUID REFERENCES copywriters
telegram_user_id    BIGINT NOT NULL
telegram_username   VARCHAR
first_name          VARCHAR
joined_at           TIMESTAMP
last_active_at      TIMESTAMP
UNIQUE(bot_id, telegram_user_id)
```

### Таблица: `orders`
```sql
id                  UUID PRIMARY KEY
client_id           UUID REFERENCES clients
bot_id              UUID REFERENCES bots
copywriter_id       UUID REFERENCES copywriters
topic               TEXT NOT NULL          -- тема от клиента
generated_text      TEXT                   -- готовый текст
status              ENUM('pending','done','failed') DEFAULT 'pending'
tokens_used         INT                    -- кол-во токенов OpenRouter
created_at          TIMESTAMP
completed_at        TIMESTAMP
```

### Таблица: `subscriptions`
```sql
id                  UUID PRIMARY KEY
copywriter_id       UUID REFERENCES copywriters
plan                ENUM('free','basic','pro')
amount              INT                    -- сумма в копейках
yookassa_payment_id VARCHAR
started_at          TIMESTAMP
expires_at          TIMESTAMP
status              ENUM('active','expired','cancelled')
```

### Таблица: `admin_users`
```sql
id                  UUID PRIMARY KEY
username            VARCHAR UNIQUE
password_hash       VARCHAR
created_at          TIMESTAMP
```

---

## 4. API Endpoints (FastAPI)

### Auth (копирайтер)
```
POST /auth/register          -- email + password
POST /auth/login             -- возвращает JWT токен
POST /auth/telegram-link     -- привязать Telegram аккаунт
```

### Bot management
```
POST   /bots                 -- добавить бот (передать токен)
GET    /bots                 -- список своих ботов
PUT    /bots/{id}            -- обновить приветствие / описание
DELETE /bots/{id}            -- удалить бот
POST   /bots/{id}/style      -- загрузить стилевой профиль (файл)
POST   /bots/{id}/activate   -- проверить токен и запустить бота
```

### Clients & Orders
```
GET /bots/{id}/clients       -- список клиентов бота
GET /bots/{id}/orders        -- история генераций
GET /orders/{id}             -- конкретный текст
```

### Subscription
```
GET  /subscription           -- текущий тариф и лимиты
POST /subscription/upgrade   -- создать платёж ЮКасса
POST /subscription/webhook   -- вебхук от ЮКасса (подтверждение оплаты)
```

### Admin (только для суперадмина, отдельный prefix /admin)
```
GET  /admin/copywriters      -- все копирайтеры
GET  /admin/copywriters/{id} -- детали
PUT  /admin/copywriters/{id}/deactivate
GET  /admin/stats            -- сводная статистика
```

---

## 5. Telegram Bot Manager

### Как это работает
Один Python-процесс управляет всеми ботами:

```python
# Псевдокод запуска
active_bots = {}  # {bot_id: (Bot, Dispatcher)}

async def load_all_bots():
    bots = db.query("SELECT * FROM bots WHERE is_active = true")
    for bot_record in bots:
        await start_bot(bot_record)

async def start_bot(bot_record):
    bot = Bot(token=decrypt(bot_record.bot_token))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(create_client_router(bot_record))
    active_bots[bot_record.id] = (bot, dp)
    asyncio.create_task(dp.start_polling(bot))

async def stop_bot(bot_id):
    bot, dp = active_bots.pop(bot_id)
    await dp.stop_polling()
    await bot.session.close()
```

### Роутер для клиентского бота
Каждый бот получает одинаковые роуты, но с данными своего копирайтера:
```
/start    → приветствие из bots.welcome_message
/написать → запросить тему → сгенерировать текст в стиле копирайтера
/история  → последние 10 текстов клиента из orders
/заказы   → статус текущих заказов
```

### Добавление нового бота (flow)
```
Копирайтер вводит токен
    → POST /bots (токен)
    → Платформа проверяет токен (getMe)
    → Сохраняет в bots.is_active = false
    → Показывает: "Бот @username подключён, нажмите Активировать"
    → POST /bots/{id}/activate
    → Bot Manager загружает бота в память
    → is_active = true
    → Бот начинает принимать сообщения
```

---

## 6. Платёжный flow (ЮКасса)

```
Копирайтер выбирает тариф Basic (990 ₽/мес)
    → POST /subscription/upgrade {plan: "basic"}
    → Платформа создаёт платёж в ЮКасса API
    → Возвращает ссылку на оплату
    → Копирайтер оплачивает
    → ЮКасса отправляет вебхук на POST /subscription/webhook
    → Платформа обновляет: plan = 'basic', plan_expires_at = now + 30 дней
    → Сбрасывает счётчик generations_used = 0
```

---

## 7. Безопасность

- **Токены ботов** шифруются в БД (Fernet/AES) — никогда не хранятся открытым текстом
- **JWT** для API аутентификации копирайтеров (срок 24ч)
- **Лимиты** проверяются до генерации: `if copywriter.generations_used >= plan_limit: reject`
- **Изоляция данных**: каждый запрос к БД фильтруется по `copywriter_id`
- **Admin panel**: отдельный Basic Auth, не связан с JWT копирайтеров

---

## 8. Порядок разработки (MVP → полная версия)

### Фаза 1 — MVP (минимально работающий продукт)
- [ ] PostgreSQL схема (4 основные таблицы)
- [ ] FastAPI: auth (register/login), добавление бота, активация
- [ ] Bot Manager: загрузка и запуск нескольких ботов
- [ ] Клиентский роутер: /start, /написать, /история
- [ ] Лимиты по тарифу Free (10 генераций/месяц)
- [ ] Простой веб-интерфейс для копирайтера (или через платформенного бота)

### Фаза 2 — Монетизация
- [ ] Интеграция ЮКасса
- [ ] Тарифы Basic и Pro
- [ ] Авто-сброс счётчика генераций каждый месяц
- [ ] Уведомления об окончании подписки

### Фаза 3 — White Label и полировка
- [ ] Настройка аватара бота через Telegram API
- [ ] Кастомное приветствие и описание
- [ ] Суперадмин панель
- [ ] Аналитика для копирайтера (сколько текстов, активных клиентов)

---

## Стек технологий

| Компонент | Технология |
|---|---|
| Бэкенд API | Python + FastAPI |
| Telegram боты | Python + aiogram 3 |
| База данных | PostgreSQL + SQLAlchemy |
| Миграции | Alembic |
| AI генерация | OpenRouter (Claude Sonnet/Haiku) |
| Платежи | ЮКасса |
| Шифрование токенов | cryptography (Fernet) |
| Деплой | Docker + docker-compose |
| Веб-интерфейс | React или простой Jinja2 (для MVP) |
