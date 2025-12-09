#!/bin/sh
# Entrypoint скрипт для monitor
# Секреты загружаются из переменных окружения (из .env.production через docker-compose)

set -e

# Проверка обязательных переменных окружения
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "❌ ОШИБКА: TELEGRAM_BOT_TOKEN не установлен"
    echo "   Убедитесь, что переменная установлена в .env.production"
    exit 1
fi

if [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "❌ ОШИБКА: TELEGRAM_CHAT_ID не установлен"
    echo "   Убедитесь, что переменная установлена в .env.production"
    exit 1
fi

echo "✅ Секреты загружены из переменных окружения"
echo "   TELEGRAM_BOT_TOKEN: установлен"
echo "   TELEGRAM_CHAT_ID: установлен"

# Запуск Python приложения
exec python /app/main.py

