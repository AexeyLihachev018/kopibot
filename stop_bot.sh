#!/bin/bash
# Остановка бота

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/bot.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "Бот не запущен (файл bot.pid не найден)"
    # На всякий случай убиваем процесс по имени
    pkill -f "python3 bot.py" 2>/dev/null
    exit 0
fi

PID=$(cat "$PID_FILE")

# Останавливаем wrapper-процесс (цикл авто-перезапуска)
if kill "$PID" 2>/dev/null; then
    echo "Wrapper-процесс остановлен (PID: $PID)"
else
    echo "Wrapper-процесс не найден (PID: $PID)"
fi

# Останавливаем сам процесс bot.py
pkill -f "python3 bot.py" 2>/dev/null && echo "Процесс bot.py остановлен"

rm -f "$PID_FILE"
echo "Бот остановлен"
