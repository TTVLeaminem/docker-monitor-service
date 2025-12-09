#!/bin/bash
# Скрипт для установки и развертывания на сервере
# Запускать на сервере: bash install-on-server.sh

set -e

REPO_URL="https://github.com/TTVLeaminem/docker-monitor-service.git"
DEPLOY_DIR="/opt/docker-monitor-service"

echo "🚀 Установка Docker Monitor Service"
echo "===================================="

# Проверка и установка Docker
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

# Проверка Docker Compose
if ! command -v docker compose &> /dev/null; then
    echo "📦 Установка Docker Compose..."
    apt-get install -y docker-compose-plugin
    echo "✅ Docker Compose установлен"
else
    echo "✅ Docker Compose установлен: $(docker compose version)"
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

# Создание .env файла, если его нет
if [ ! -f ".env" ]; then
    echo ""
    echo "⚙️  Создание файла .env..."
    cp .env.example .env
    
    echo ""
    echo "⚠️  ВАЖНО: Необходимо заполнить файл .env!"
    echo "   Отредактируйте файл: nano $DEPLOY_DIR/.env"
    echo "   Заполните:"
    echo "     - TELEGRAM_BOT_TOKEN"
    echo "     - TELEGRAM_CHAT_ID"
    echo ""
    read -p "Нажмите Enter после заполнения .env файла..."
else
    echo "✅ Файл .env уже существует"
fi

# Запуск сервиса
echo ""
echo "🐳 Запуск сервиса..."
docker compose down 2>/dev/null || true
docker compose build
docker compose up -d

echo ""
echo "✅ Установка завершена!"
echo "======================="
echo ""
echo "Статус контейнеров:"
docker compose ps
echo ""
echo "Просмотр логов:"
echo "  cd $DEPLOY_DIR"
echo "  docker compose logs -f monitor"
echo ""

