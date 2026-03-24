-- ============================================================
-- SaaS White Label платформа для копирайтеров
-- База данных: Supabase (PostgreSQL)
-- ============================================================

-- ============================================================
-- ШАГ 0: ОЧИСТКА (если запускаешь повторно — удаляет старое)
-- ============================================================

DROP VIEW  IF EXISTS public.admin_stats CASCADE;
DROP TABLE IF EXISTS public.subscriptions CASCADE;
DROP TABLE IF EXISTS public.orders       CASCADE;
DROP TABLE IF EXISTS public.clients      CASCADE;
DROP TABLE IF EXISTS public.bots         CASCADE;
DROP TABLE IF EXISTS public.copywriters  CASCADE;
DROP TABLE IF EXISTS public.admin_users  CASCADE;
DROP TYPE  IF EXISTS subscription_status CASCADE;
DROP TYPE  IF EXISTS order_status        CASCADE;
DROP TYPE  IF EXISTS plan_type           CASCADE;
DROP TRIGGER IF EXISTS trigger_new_user ON auth.users;
DROP FUNCTION IF EXISTS public.on_new_user_registered() CASCADE;
DROP FUNCTION IF EXISTS public.reset_monthly_generations() CASCADE;


-- ============================================================
-- ШАГ 1: ТИПЫ-ПЕРЕЧИСЛЕНИЯ (как выпадающие списки для колонок)
-- ============================================================

-- Тарифный план копирайтера
CREATE TYPE plan_type AS ENUM ('free', 'basic', 'pro');

-- Статус заказа на генерацию текста
CREATE TYPE order_status AS ENUM ('pending', 'done', 'failed');

-- Статус подписки
CREATE TYPE subscription_status AS ENUM ('active', 'expired', 'cancelled');


-- ============================================================
-- ШАГ 2: ТАБЛИЦЫ
-- ============================================================

-- ------------------------------------------------------------
-- Таблица: copywriters (профили копирайтеров)
-- Регистрация через Telegram. auth_user_id опционален (для будущей веб-панели).
-- ------------------------------------------------------------
CREATE TABLE public.copywriters (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id         UUID REFERENCES auth.users(id) ON DELETE SET NULL, -- опционально
    telegram_user_id     BIGINT UNIQUE,             -- Telegram ID в платформенном боте
    display_name         VARCHAR(255),              -- "Алексей — копирайтер"
    plan                 plan_type DEFAULT 'free',  -- текущий тариф
    plan_expires_at      TIMESTAMPTZ,               -- когда кончается подписка
    generations_used     INT DEFAULT 0,             -- генераций использовано в этом месяце
    generations_reset_at TIMESTAMPTZ DEFAULT (date_trunc('month', now()) + interval '1 month'),
    yookassa_customer_id VARCHAR(255),              -- ID клиента в ЮКасса
    is_active            BOOLEAN DEFAULT true,
    created_at           TIMESTAMPTZ DEFAULT now()
);

-- ------------------------------------------------------------
-- Таблица: bots (Telegram-боты копирайтеров)
-- Каждый копирайтер может подключить своего бота.
-- ------------------------------------------------------------
CREATE TABLE public.bots (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    copywriter_id     UUID NOT NULL REFERENCES public.copywriters(id) ON DELETE CASCADE,
    bot_token_encrypted TEXT NOT NULL,             -- токен зашифрован (никогда открытым текстом!)
    bot_username      VARCHAR(255),                -- @brand_bot
    bot_name          VARCHAR(255),                -- "Копирайтер Алексей"
    welcome_message   TEXT DEFAULT 'Привет! Я помогу создать отличный контент. Напишите /написать чтобы начать.',
    help_message      TEXT,                        -- кастомный текст /help
    style_guide       JSONB DEFAULT '{}'::jsonb,   -- стилевой профиль AI (JSON)
    content_plan      JSONB DEFAULT '[]'::jsonb,   -- контент-план (JSON)
    is_active         BOOLEAN DEFAULT false,       -- false пока токен не проверен
    created_at        TIMESTAMPTZ DEFAULT now()
);

-- ------------------------------------------------------------
-- Таблица: clients (клиенты копирайтеров в Telegram)
-- Каждый человек, написавший в бот копирайтера.
-- ------------------------------------------------------------
CREATE TABLE public.clients (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bot_id            UUID NOT NULL REFERENCES public.bots(id) ON DELETE CASCADE,
    copywriter_id     UUID NOT NULL REFERENCES public.copywriters(id) ON DELETE CASCADE,
    telegram_user_id  BIGINT NOT NULL,
    telegram_username VARCHAR(255),
    first_name        VARCHAR(255),
    joined_at         TIMESTAMPTZ DEFAULT now(),
    last_active_at    TIMESTAMPTZ DEFAULT now(),
    UNIQUE(bot_id, telegram_user_id)  -- один клиент = одна запись на бот
);

-- ------------------------------------------------------------
-- Таблица: orders (заказы на генерацию текстов)
-- Каждая генерация сохраняется здесь.
-- ------------------------------------------------------------
CREATE TABLE public.orders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id       UUID NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
    bot_id          UUID NOT NULL REFERENCES public.bots(id) ON DELETE CASCADE,
    copywriter_id   UUID NOT NULL REFERENCES public.copywriters(id) ON DELETE CASCADE,
    topic           TEXT NOT NULL,           -- тема, которую задал клиент
    generated_text  TEXT,                   -- готовый текст от AI
    status          order_status DEFAULT 'pending',
    tokens_used     INT DEFAULT 0,          -- сколько токенов потратили в OpenRouter
    created_at      TIMESTAMPTZ DEFAULT now(),
    completed_at    TIMESTAMPTZ
);

-- ------------------------------------------------------------
-- Таблица: subscriptions (история оплат и подписок)
-- Каждая оплата — отдельная запись.
-- ------------------------------------------------------------
CREATE TABLE public.subscriptions (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    copywriter_id         UUID NOT NULL REFERENCES public.copywriters(id) ON DELETE CASCADE,
    plan                  plan_type NOT NULL,
    amount                INT NOT NULL,           -- сумма в копейках (990₽ = 99000)
    yookassa_payment_id   VARCHAR(255),
    started_at            TIMESTAMPTZ DEFAULT now(),
    expires_at            TIMESTAMPTZ,
    status                subscription_status DEFAULT 'active'
);

-- ------------------------------------------------------------
-- Таблица: admin_users (суперадмины платформы)
-- Отдельная таблица, не связана с auth.users — только для нас.
-- ------------------------------------------------------------
CREATE TABLE public.admin_users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username      VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,   -- bcrypt хеш пароля
    created_at    TIMESTAMPTZ DEFAULT now()
);


-- ============================================================
-- ШАГ 3: ИНДЕКСЫ (как оглавление в книге — ускоряют поиск)
-- ============================================================

CREATE INDEX idx_bots_copywriter_id       ON public.bots(copywriter_id);
CREATE INDEX idx_clients_bot_id           ON public.clients(bot_id);
CREATE INDEX idx_clients_copywriter_id    ON public.clients(copywriter_id);
CREATE INDEX idx_clients_telegram_user_id ON public.clients(telegram_user_id);
CREATE INDEX idx_orders_client_id         ON public.orders(client_id);
CREATE INDEX idx_orders_copywriter_id     ON public.orders(copywriter_id);
CREATE INDEX idx_orders_bot_id            ON public.orders(bot_id);
CREATE INDEX idx_orders_created_at        ON public.orders(created_at DESC);
CREATE INDEX idx_subscriptions_copywriter ON public.subscriptions(copywriter_id);


-- ============================================================
-- ШАГ 4: ROW LEVEL SECURITY (замки на полках)
-- RLS — это как личный сейф у каждого копирайтера:
-- он видит только свои данные, даже если хочет залезть к чужим.
-- ============================================================

-- Включаем защиту на каждой таблице
ALTER TABLE public.copywriters  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bots         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.clients      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.orders       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;
-- admin_users намеренно БЕЗ RLS — доступ только через серверный код


-- Политики для copywriters: каждый видит и редактирует только себя
CREATE POLICY "copywriters: только свои данные"
    ON public.copywriters FOR ALL
    USING (auth.uid() = id);

-- Политики для bots: копирайтер работает только со своими ботами
CREATE POLICY "bots: только свои"
    ON public.bots FOR ALL
    USING (copywriter_id = auth.uid());

-- Политики для clients: копирайтер видит только своих клиентов
CREATE POLICY "clients: только свои"
    ON public.clients FOR ALL
    USING (copywriter_id = auth.uid());

-- Политики для orders: копирайтер видит только свои заказы
CREATE POLICY "orders: только свои"
    ON public.orders FOR ALL
    USING (copywriter_id = auth.uid());

-- Политики для subscriptions: копирайтер видит только свои подписки
CREATE POLICY "subscriptions: только свои"
    ON public.subscriptions FOR ALL
    USING (copywriter_id = auth.uid());


-- ============================================================
-- ШАГ 5: ТРИГГЕР — автосоздание профиля при регистрации
-- Когда копирайтер регистрируется через Supabase Auth,
-- автоматически создаётся запись в нашей таблице copywriters.
-- Это как "добро пожаловать" — дверь открылась, охранник
-- сразу заводит карточку нового гостя.
-- ============================================================

-- Триггер не нужен: копирайтеры регистрируются через Telegram-бот платформы,
-- а не через Supabase Auth. Запись создаётся напрямую в таблице copywriters.


-- ============================================================
-- ШАГ 6: ФУНКЦИЯ сброса счётчика генераций (ежемесячно)
-- Вызывается по расписанию 1-го числа каждого месяца.
-- ============================================================

CREATE OR REPLACE FUNCTION public.reset_monthly_generations()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    UPDATE public.copywriters
    SET
        generations_used     = 0,
        generations_reset_at = date_trunc('month', now()) + interval '1 month'
    WHERE generations_reset_at <= now();
END;
$$;


-- ============================================================
-- ШАГ 7: VIEW для суперадмина (сводная статистика)
-- View — это как готовый отчёт, который всегда актуален.
-- ============================================================

CREATE VIEW public.admin_stats AS
SELECT
    (SELECT COUNT(*) FROM public.copywriters WHERE is_active = true)   AS active_copywriters,
    (SELECT COUNT(*) FROM public.bots WHERE is_active = true)           AS active_bots,
    (SELECT COUNT(*) FROM public.clients)                               AS total_clients,
    (SELECT COUNT(*) FROM public.orders WHERE status = 'done')          AS total_generations,
    (SELECT COUNT(*) FROM public.orders
        WHERE status = 'done'
        AND created_at >= date_trunc('month', now()))                   AS generations_this_month,
    (SELECT COUNT(*) FROM public.copywriters WHERE plan = 'free')       AS free_plan_count,
    (SELECT COUNT(*) FROM public.copywriters WHERE plan = 'basic')      AS basic_plan_count,
    (SELECT COUNT(*) FROM public.copywriters WHERE plan = 'pro')        AS pro_plan_count;
