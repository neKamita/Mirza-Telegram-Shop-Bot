# Multi-stage build для оптимизации размера образа
FROM python:3.13-slim AS base

# Установка системных зависимостей для сборки
FROM base AS builder
WORKDIR /app

# Установка системных зависимостей для Chrome и сборки Python пакетов
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    wget \
    unzip \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements и установка зависимостей в virtual environment
COPY requirements.txt .
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Финальный образ
FROM base AS final

# Создание непривилегированного пользователя
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Установка системных зависимостей для runtime
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Установка Chrome и ChromeDriver только если требуется Fragment функциональность
RUN if [ "$FRAGMENT_AUTO_COOKIE_REFRESH" = "true" ]; then \
    wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor > /etc/apt/trusted.gpg.d/google-archive.gpg && \
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list && \
    apt-get update && \
    apt-get install -y google-chrome-stable && \
    # Установка ChromeDriver
    CHROMEDRIVER_VERSION=$(curl -sS chromedriver.storage.googleapis.com/LATEST_RELEASE) && \
    wget -O /tmp/chromedriver.zip http://chromedriver.storage.googleapis.com/${CHROMEDRIVER_VERSION}/chromedriver_linux64.zip && \
    unzip /tmp/chromedriver.zip chromedriver -d /tmp/ && \
    mv /tmp/chromedriver /usr/local/bin/chromedriver && \
    chmod +x /usr/local/bin/chromedriver && \
    rm /tmp/chromedriver.zip && \
    rm -rf /var/lib/apt/lists/*; \
    fi

# Копирование виртуального окружения из builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Установка рабочей директории
WORKDIR /app

# Копирование кода приложения
COPY . .

# Создание необходимых директорий
RUN mkdir -p /app/logs /app/ssl && \
    chown -R appuser:appuser /app

# Установка переменных окружения
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app:$PYTHONPATH"

# Переключение на непривилегированного пользователя
USER appuser

# Экспорт портов
EXPOSE 8001

# Оптимизированный health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Оптимизированная команда запуска
CMD ["sh", "-c", "python main.py"]
