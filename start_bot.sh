#!/bin/bash
# Запуск бота в фоновом режиме с авто-перезапуском

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/bot.pid"
LOG_FILE="$SCRIPT_DIR/bot.log"

# Проверяем, не запущен ли уже бот
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Бот уже запущен (PID: $OLD_PID)"
        echo "Чтобы остановить: ./stop_bot.sh"
        exit 1
    else
        rm "$PID_FILE"
    fi
fi

# Запускаем цикл авто-перезапуска в фоне
nohup bash -c "
cd '$SCRIPT_DIR'
while true; do
    echo \"[$(date '+%Y-%m-%d %H:%M:%S')] Бот запущен\"
    python3 bot.py
    EXIT_CODE=\$?
    echo \"[$(date '+%Y-%m-%d %H:%M:%S')] Бот остановился (код \$EXIT_CODE)\"
    if [ \$EXIT_CODE -eq 0 ]; then
        echo 'Штатная остановка — перезапуск отменён'
        break
    fi
    echo 'Перезапуск через 5 секунд...'
    sleep 5
done
" >> "$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"
echo "Бот запущен в фоне (PID: $!)"
echo "Логи: tail -f $LOG_FILE"
echo "Остановить: ./stop_bot.sh"
