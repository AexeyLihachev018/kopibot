#!/bin/bash
# Скрипт установки KopiBot на VPS (Ubuntu/Debian)
# Запускать от root: bash server_setup.sh

set -e
echo "=== Установка KopiBot ==="

# 1. Обновляем систему
apt-get update -y && apt-get upgrade -y

# 2. Устанавливаем Python3, pip, git
apt-get install -y python3 python3-pip python3-venv git

# 3. Переходим в папку проекта
cd /root/kopibot

# 4. Создаём виртуальное окружение
python3 -m venv venv

# 5. Устанавливаем зависимости
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# 6. Устанавливаем systemd-сервис
cp kopibot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable kopibot
systemctl start kopibot

echo ""
echo "=== Готово! ==="
echo "Статус бота: systemctl status kopibot"
echo "Логи бота:   journalctl -u kopibot -f"
