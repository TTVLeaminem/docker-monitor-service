# Инструкция по развертыванию на сервере

## Быстрая установка

### Вариант 1: Автоматическая установка (рекомендуется)

Выполните на сервере:

```bash
ssh root@212.193.54.178
```

Затем выполните:

```bash
curl -sSL https://raw.githubusercontent.com/TTVLeaminem/docker-monitor-service/main/install-on-server.sh | bash
```

Или клонируйте репозиторий и запустите скрипт:

```bash
cd /opt
git clone https://github.com/TTVLeaminem/docker-monitor-service.git
cd docker-monitor-service
bash install-on-server.sh
```

### Вариант 2: Ручная установка

#### Шаг 1: Подключение к серверу

```bash
ssh root@212.193.54.178
# Пароль: HAVw6-7K46B-8H2v9-Bis4g
```

#### Шаг 2: Установка Docker

```bash
# Обновление пакетов
apt-get update

# Установка зависимостей
apt-get install -y ca-certificates curl gnupg lsb-release

# Добавление GPG ключа Docker
mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Добавление репозитория Docker
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

# Установка Docker
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Запуск Docker
systemctl enable docker
systemctl start docker

# Проверка установки
docker --version
docker compose version
```

#### Шаг 3: Клонирование репозитория

```bash
mkdir -p /opt/docker-monitor-service
cd /opt/docker-monitor-service
git clone https://github.com/TTVLeaminem/docker-monitor-service.git .
```

#### Шаг 4: Настройка переменных окружения

```bash
cd /opt/docker-monitor-service
cp .env.example .env
nano .env
```

Заполните следующие переменные:
- `TELEGRAM_BOT_TOKEN` - токен вашего Telegram бота
- `TELEGRAM_CHAT_ID` - ID чата для уведомлений

Пример:
```
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
MONITOR_INTERVAL=60
MONITOR_STATE_FILE=/tmp/docker-monitor-state.json
MONITORED_CONTAINERS=
```

#### Шаг 5: Запуск сервиса

```bash
cd /opt/docker-monitor-service
docker compose build
docker compose up -d
```

#### Шаг 6: Проверка работы

```bash
# Проверка статуса
docker compose ps

# Просмотр логов
docker compose logs -f monitor
```

## Управление сервисом

### Остановка

```bash
cd /opt/docker-monitor-service
docker compose down
```

### Перезапуск

```bash
cd /opt/docker-monitor-service
docker compose restart
```

### Обновление

```bash
cd /opt/docker-monitor-service
git pull
docker compose build
docker compose down
docker compose up -d
```

### Просмотр логов

```bash
cd /opt/docker-monitor-service
docker compose logs -f monitor
```

## Получение Telegram Bot Token

1. Откройте Telegram и найдите бота [@BotFather](https://t.me/BotFather)
2. Отправьте команду `/newbot`
3. Следуйте инструкциям для создания бота
4. Скопируйте полученный токен

## Получение Chat ID

1. Откройте Telegram и найдите бота [@userinfobot](https://t.me/userinfobot)
2. Отправьте команду `/start`
3. Скопируйте ваш Chat ID

Или создайте группу, добавьте бота и получите ID группы через API:

```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates"
```

## Проверка работы

После запуска сервиса:

1. Откройте Telegram бота
2. Отправьте команду `/start`
3. Используйте кнопки для управления:
   - 📋 Список контейнеров
   - 📊 Статус контейнеров

## Устранение неполадок

### Docker не запускается

```bash
systemctl status docker
journalctl -u docker
```

### Контейнер не запускается

```bash
cd /opt/docker-monitor-service
docker compose logs monitor
```

### Проблемы с правами доступа

```bash
# Проверка доступа к Docker socket
ls -la /var/run/docker.sock
```

## Безопасность

⚠️ **Важно**: После установки измените пароль root на сервере:

```bash
passwd
```

Также рекомендуется настроить SSH ключи вместо пароля.

