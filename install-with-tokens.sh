#!/bin/bash
# Скрипт установки с предустановленными токенами
# Использование: curl -sSL https://raw.githubusercontent.com/TTVLeaminem/docker-monitor-service/main/install-with-tokens.sh | bash

set -e

REPO_URL="https://github.com/TTVLeaminem/docker-monitor-service.git"
DEPLOY_DIR="/opt/docker-monitor-service"
BOT_TOKEN="7612297610:AAG-RN3dad9uTjgI-2N2DXtv9-1P2Y0uxks"
CHAT_ID="6355414381"

echo "🚀 Развертывание Docker Monitor Service"
echo "========================================"

# Установка Docker
if ! command -v docker &> /dev/null; then
    echo "📦 Установка Docker..."
    apt-get update
    apt-get install -y ca-certificates curl gnupg lsb-release
    
    mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    
    systemctl enable docker
    systemctl start docker
    echo "✅ Docker установлен"
else
    echo "✅ Docker уже установлен: $(docker --version)"
fi

# Клонирование репозитория
echo ""
echo "📥 Клонирование репозитория..."
mkdir -p $DEPLOY_DIR
cd $DEPLOY_DIR

if [ -d ".git" ]; then
    echo "Обновление репозитория..."
    git pull
else
    echo "Клонирование репозитория..."
    git clone $REPO_URL .
fi
echo "✅ Репозиторий готов"

# Настройка .env файла
echo ""
echo "⚙️  Настройка .env файла..."
cat > .env << EOF
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_CHAT_ID=$CHAT_ID
MONITOR_INTERVAL=60
MONITOR_STATE_FILE=/tmp/docker-monitor-state.json
MONITORED_CONTAINERS=
EOF
echo "✅ Файл .env создан"

# Запуск сервиса
echo ""
echo "🐳 Запуск сервиса..."
docker compose down 2>/dev/null || true
docker compose build
docker compose up -d

echo ""
echo "✅ Развертывание завершено!"
echo "============================"
echo ""
echo "Статус контейнеров:"
docker compose ps

echo ""
echo "Просмотр логов:"
echo "  cd $DEPLOY_DIR"
echo "  docker compose logs -f monitor"
echo ""

