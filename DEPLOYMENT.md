# Деплой КопиБот на VPS — пошаговая инструкция

Эта инструкция для тех, кто деплоит первый раз.
Платформа: Ubuntu 24.04, VPS (Beget или любой другой).

---

## Что у тебя должно быть готово до начала

- VPS с Ubuntu 24.04 и root-доступом
- IP-адрес сервера и пароль root
- Аккаунт на [supabase.com](https://supabase.com) (бесплатный)
- Аккаунт на [openrouter.ai](https://openrouter.ai) (бесплатный)
- Два Telegram-бота, созданных через @BotFather:
  - **Платформенный бот** — для копирайтеров (ты управляешь через него)
  - **Клиентский бот** — для клиентов (подключается через платформу)

---

## Шаг 1. Подключись к серверу

На Mac/Linux открой Терминал и введи:

```bash
ssh root@ТВО_IP
```

Введи пароль. Увидишь строку `root@hostname:~#` — значит подключился.

---

## Шаг 2. Установи зависимости

```bash
apt-get update -y && apt-get install -y python3 python3-pip python3-venv git
```

---

## Шаг 3. Скачай код проекта

```bash
cd /root
git clone https://github.com/AexeyLihachev018/kopibot.git kopibot
cd kopibot
```

---

## Шаг 4. Создай виртуальное окружение и установи библиотеки

```bash
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
```

Это займёт 1–2 минуты.

---

## Шаг 5. Настрой базу данных в Supabase

### 5.1 Создай проект

1. Зайди на [supabase.com](https://supabase.com) → New project
2. Придумай имя и пароль БД → Create project
3. Подожди ~1 минуту пока поднимется

### 5.2 Создай таблицы

1. В боковом меню → **SQL Editor**
2. Вставь содержимое файла `database/schema.sql` (весь файл целиком)
3. Нажми **Run**
4. Затем вставь содержимое `database/migrations/001_add_catalog.sql`
5. Нажми **Run**

### 5.3 Получи ключи

В боковом меню → **Project Settings** → **API**:

- **Project URL** — выглядит как `https://xxxx.supabase.co`
- **service_role secret** — длинная строка (НЕ anon key!)

Сохрани оба — понадобятся в шаге 6.

---

## Шаг 6. Создай файл .env

На сервере выполни (замени значения на свои):

```bash
cat > /root/kopibot/.env << 'EOF'
# Токен платформенного бота (от @BotFather)
PLATFORM_BOT_TOKEN=1234567890:AABBccDDee...

# Supabase
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# OpenRouter (для генерации текстов)
OPENROUTER_API_KEY=sk-or-v1-...

# Ключ шифрования токенов ботов (генерируется один раз)
ENCRYPTION_KEY=
EOF
```

### 6.1 Сгенерируй ENCRYPTION_KEY

```bash
cd /root/kopibot
./venv/bin/python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Скопируй вывод и вставь в .env после `ENCRYPTION_KEY=`:

```bash
nano /root/kopibot/.env
```

Найди строку `ENCRYPTION_KEY=` и допиши ключ. Сохрани: `Ctrl+O`, `Enter`, `Ctrl+X`.

> ⚠️ **Важно:** ENCRYPTION_KEY нельзя менять после того, как боты добавлены в БД — токены не расшифруются.

### 6.2 Проверь .env

```bash
cat /root/kopibot/.env
```

Убедись, что все 4 переменные заполнены (не пустые).

---

## Шаг 7. Запусти бота как системный сервис

```bash
cp /root/kopibot/kopibot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable kopibot
systemctl start kopibot
```

---

## Шаг 8. Проверь что всё работает

```bash
systemctl status kopibot
```

Должно быть: `Active: active (running)` зелёным цветом.

Посмотреть логи в реальном времени:

```bash
journalctl -u kopibot -f
```

Выйти из логов: `Ctrl+C`.

---

## Шаг 9. Проверь бота в Telegram

1. Открой свой платформенный бот
2. Отправь `/start`
3. Введи своё имя — появится главное меню
4. Нажми **➕ Добавить бота** и подключи клиентский бот

---

## Обновление кода (после изменений)

Когда вышла новая версия — зайди на сервер и выполни:

```bash
cd /root/kopibot && git pull origin main && systemctl restart kopibot
```

Одна команда — и новая версия работает.

---

## Диагностика проблем

| Симптом | Что делать |
|---|---|
| `Active: failed` в статусе | `journalctl -u kopibot -n 50` — смотри ошибку |
| Бот не отвечает | Проверь токен в `.env`, перезапусти: `systemctl restart kopibot` |
| `SUPABASE_URL ... должны быть в .env` | Отредактируй `.env`: `nano /root/kopibot/.env` |
| `ENCRYPTION_KEY не найден` | Добавь ключ в `.env` (см. шаг 6.1) |
| Бот запускается и сразу падает | Смотри логи: `journalctl -u kopibot -n 100` |

---

## Структура проекта (кратко)

```
kopibot/
├── run_platform.py          # точка входа — запускает всё
├── saas/
│   ├── platform_bot/        # бот для копирайтеров (платформа)
│   └── bot_manager/         # управление клиентскими ботами
├── database/
│   ├── schema.sql           # структура БД — запускать один раз
│   └── migrations/          # обновления БД
├── requirements.txt         # зависимости Python
├── kopibot.service          # конфиг systemd-сервиса
└── .env                     # секретные ключи (не коммитить!)
```
