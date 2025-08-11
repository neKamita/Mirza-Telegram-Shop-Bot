FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements и установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения
COPY . .

# Создание директорий для логов и ssl
RUN mkdir -p /app/logs /app/ssl

# Установка переменных окружения
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Expose ports for webhook service
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import asyncio; import sys; sys.path.append('/app'); from repositories.user_repository import UserRepository; import os; repo = UserRepository(os.getenv('DATABASE_URL', '')); asyncio.run(repo.create_tables())" || exit 1

# Запуск приложения (основной сервис)
CMD ["python", "main.py"]
