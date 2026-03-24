#!/bin/bash
# Проверка статуса бота

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/bot.pid"
LOG_FILE="$SCRIPT_DIR/bot.log"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Бот запущен (PID: $PID)"
    else
        echo "Бот не работает (устаревший PID: $PID)"
        rm -f "$PID_FILE"
    fi
else
    echo "Бот не запущен"
fi

# Показываем последние 20 строк лога
if [ -f "$LOG_FILE" ]; then
    echo ""
    echo "=== Последние строки лога ==="
    tail -20 "$LOG_FILE"
fi
