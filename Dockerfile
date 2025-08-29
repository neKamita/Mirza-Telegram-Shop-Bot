FROM python:3.13-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    wget \
    unzip \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Установка Chrome и ChromeDriver для автоматического обновления cookies
# Используем более надежный подход с установкой через apt
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor > /etc/apt/trusted.gpg.d/google-archive.gpg && \
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list && \
    apt-get update && \
    apt-get install -y google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# Установка ChromeDriver через pip (более надежный способ)
RUN pip install --no-cache-dir chromedriver-py

# Копирование requirements и установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Установка Selenium для автоматического обновления cookies (если включено)
RUN pip install --no-cache-dir selenium

# Копирование кода приложения
COPY . .

# Создание директорий для логов и ssl
RUN mkdir -p /app/logs /app/ssl

# Установка переменных окружения
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV CHROMEDRIVER_PATH=/usr/local/bin/chromedriver

# Expose ports for webhook service
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import asyncio; import sys; sys.path.append('/app'); from repositories.user_repository import UserRepository; import os; repo = UserRepository(os.getenv('DATABASE_URL', '')); asyncio.run(repo.create_tables())" || exit 1

# Предварительная проверка настроек Fragment API
# Запуск скрипта обновления Fragment cookies перед запуском приложения
# И запуск периодического обновлятора как фоновую задачу
CMD ["sh", "-c", "python scripts/precheck_fragment.py && python scripts/update_fragment_cookies.py && python scripts/periodic_cookie_refresher.py & python main.py"]
