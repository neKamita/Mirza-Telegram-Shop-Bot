# Многоступенчатая сборка на Alpine Linux для максимальной скорости
FROM python:3.13-alpine AS builder

WORKDIR /app

# Установка системных зависимостей - СУПЕР БЫСТРО с apk
RUN apk add --no-cache --virtual .build-deps \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    curl \
    cargo \
    && apk add --no-cache \
    ca-certificates

# Установка uv для быстрой установки Python зависимостей
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv

# Установка Python зависимостей
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/uv \
    /usr/local/bin/uv pip install --system --compile -r requirements.txt

# Удаляем build dependencies чтобы уменьшить размер
RUN apk del .build-deps

# Финальный этап - минимальный Alpine образ
FROM python:3.13-alpine AS runtime

WORKDIR /app

# Копирование установленных пакетов из builder этапа
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/

# Установка только runtime зависимостей
RUN apk add --no-cache \
    # Для работы с SSL
    ca-certificates \
    # Для работы с сетевыми операциями
    libstdc++

# Копирование кода приложения
COPY . .

# Создание необходимых директорий
RUN mkdir -p /app/logs

# Установка переменных окружения
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

# Expose ports for webhook service
EXPOSE 8001

# Оптимизированный HEALTHCHECK
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys; sys.path.append('/app'); from services.system.health_service import HealthService; import asyncio; asyncio.run(HealthService(None).check_database_health())" || exit 1

# Запуск приложения
CMD ["sh", "-c", "python scripts/precheck_fragment.py & python scripts/update_fragment_cookies.py & python scripts/periodic_cookie_refresher.py & python main.py"]