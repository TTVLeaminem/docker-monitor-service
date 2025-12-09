FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей системы
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копирование файлов зависимостей
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения
COPY main.py .
COPY entrypoint.sh .

# Делаем entrypoint.sh исполняемым
RUN chmod +x entrypoint.sh

# Установка entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

