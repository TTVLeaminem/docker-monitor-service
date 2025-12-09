#!/bin/bash
# Скрипт развертывания Docker Monitor Service на сервере

set -e

SERVER_HOST="212.193.54.178"
SERVER_USER="root"
SERVER_PASS="HAVw6-7K46B-8H2v9-Bis4g"
REPO_URL="https://github.com/TTVLeaminem/docker-monitor-service.git"
DEPLOY_DIR="/opt/docker-monitor-service"

echo "🚀 Начало развертывания Docker Monitor Service"
echo "================================================"

# Функция для выполнения команд на сервере
run_remote() {
    sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_HOST" "$1"
}

# Функция для копирования файлов на сервер
copy_to_remote() {
    sshpass -p "$SERVER_PASS" scp -o StrictHostKeyChecking=no "$1" "$SERVER_USER@$SERVER_HOST:$2"
}

echo ""
echo "📦 Шаг 1: Проверка и установка Docker..."
echo "----------------------------------------"

# Проверяем, установлен ли Docker
DOCKER_CHECK=$(run_remote "command -v docker || echo 'not_installed'")

if [ "$DOCKER_CHECK" = "not_installed" ]; then
    echo "Docker не установлен. Устанавливаем Docker..."
    
    # Установка Docker
    run_remote "apt-get update && apt-get install -y ca-certificates curl gnupg lsb-release"
    run_remote "mkdir -p /etc/apt/keyrings"
    run_remote "curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg"
    run_remote "echo \"deb [arch=\$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \$(lsb_release -cs) stable\" | tee /etc/apt/sources.list.d/docker.list > /dev/null"
    run_remote "apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin"
    run_remote "systemctl enable docker && systemctl start docker"
    
    echo "✅ Docker установлен"
else
    echo "✅ Docker уже установлен: $DOCKER_CHECK"
    run_remote "docker --version"
fi

# Проверяем Docker Compose
COMPOSE_CHECK=$(run_remote "command -v docker compose || echo 'not_installed'")

if [ "$COMPOSE_CHECK" = "not_installed" ]; then
    echo "Docker Compose не найден. Устанавливаем..."
    # Docker Compose уже должен быть установлен с docker-compose-plugin
    run_remote "apt-get install -y docker-compose-plugin"
    echo "✅ Docker Compose установлен"
else
    echo "✅ Docker Compose уже установлен"
    run_remote "docker compose version"
fi

echo ""
echo "📥 Шаг 2: Клонирование репозитория..."
echo "--------------------------------------"

# Создаем директорию для развертывания
run_remote "mkdir -p $DEPLOY_DIR"

# Клонируем репозиторий
run_remote "cd $DEPLOY_DIR && (git clone $REPO_URL . 2>/dev/null || git pull)"

echo "✅ Репозиторий склонирован"

echo ""
echo "⚙️  Шаг 3: Настройка переменных окружения..."
echo "--------------------------------------------"

# Проверяем, существует ли .env файл
ENV_EXISTS=$(run_remote "test -f $DEPLOY_DIR/.env && echo 'exists' || echo 'not_exists'")

if [ "$ENV_EXISTS" = "not_exists" ]; then
    echo "⚠️  Файл .env не найден. Создайте его вручную на сервере:"
    echo "   ssh $SERVER_USER@$SERVER_HOST"
    echo "   cd $DEPLOY_DIR"
    echo "   cp .env.example .env"
    echo "   nano .env  # Заполните TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID"
    echo ""
    echo "Или создайте файл автоматически (потребуется ввод токенов):"
    read -p "Введите TELEGRAM_BOT_TOKEN: " BOT_TOKEN
    read -p "Введите TELEGRAM_CHAT_ID: " CHAT_ID
    
    run_remote "cat > $DEPLOY_DIR/.env << EOF
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_CHAT_ID=$CHAT_ID
MONITOR_INTERVAL=60
MONITOR_STATE_FILE=/tmp/docker-monitor-state.json
MONITORED_CONTAINERS=
EOF
"
    echo "✅ Файл .env создан"
else
    echo "✅ Файл .env уже существует"
fi

echo ""
echo "🐳 Шаг 4: Запуск сервиса..."
echo "----------------------------"

# Останавливаем существующий контейнер, если есть
run_remote "cd $DEPLOY_DIR && docker compose down 2>/dev/null || true"

# Собираем и запускаем контейнер
run_remote "cd $DEPLOY_DIR && docker compose build"
run_remote "cd $DEPLOY_DIR && docker compose up -d"

echo ""
echo "✅ Развертывание завершено!"
echo "============================"
echo ""
echo "Проверка статуса:"
run_remote "cd $DEPLOY_DIR && docker compose ps"

echo ""
echo "Просмотр логов:"
echo "  ssh $SERVER_USER@$SERVER_HOST"
echo "  cd $DEPLOY_DIR"
echo "  docker compose logs -f monitor"
echo ""
echo "Остановка сервиса:"
echo "  cd $DEPLOY_DIR"
echo "  docker compose down"
echo ""

