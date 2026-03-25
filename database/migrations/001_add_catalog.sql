-- ============================================================
-- Миграция 001: Добавление каталога услуг в таблицу bots
-- Запусти этот SQL в Supabase → SQL Editor
-- ============================================================

-- Добавляем колонку catalog (массив услуг мастера)
-- Пример: [{"id":1,"title":"SEO-статья","description":"...","price":"2000 ₽"}]
ALTER TABLE public.bots
    ADD COLUMN IF NOT EXISTS catalog JSONB DEFAULT '[]'::jsonb;

-- Проверка (должно вернуть строки с колонкой catalog)
-- SELECT id, bot_username, catalog FROM public.bots;
