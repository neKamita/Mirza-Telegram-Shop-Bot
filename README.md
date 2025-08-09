# Telegram Bot с Покупкой Звезд

Современный Telegram-бот для покупки звезд через интеграцию с платежной системой Heleket. Проект построен на микросервисной архитектуре с использованием Docker Compose, Redis кластера и высокодоступной инфраструктуры.

## ✨ Особенности

- **Микросервисная архитектура** - масштабируемые и независимые сервисы
- **Redis кластер** - 3 ноды (master + 2 slaves) для высокой доступности
- **Nginx reverse proxy** - SSL/TLS терминация и балансировка нагрузки
- **Circuit breaker** - защита от каскадных отказов
- **Rate limiting** - ограничение частоты запросов
- **Health checks** - мониторинг состояния сервисов
- **Альтернативные порты** - 8080/8443/8081 для решения конфликтов
- **PostgreSQL (Neon) + Redis** - надежное хранение и кеширование
- **Docker контейнеризация** - легкое развертывание и масштабирование

## 🏗️ Архитектура

### Микросервисная архитектура

```mermaid
graph TB
    subgraph "External Layer"
        TG[Telegram API] --> NG[Nginx Reverse Proxy]
        NG --> NGINX_SSL[Nginx SSL:8443]
        NG --> NGINX_HTTP[Nginx HTTP:8080]
    end

    subgraph "Application Layer"
        NGINX_SSL --> APP[Telegram Bot App:8081]
        NGINX_HTTP --> APP
        APP --> CB[Circuit Breaker]
        CB --> RL[Rate Limiter]
    end

    subgraph "Cache Layer"
        RL --> RC[Redis Cluster]
        RC --> RM[Redis Master:6379]
        RC --> RS1[Redis Slave 1:6380]
        RC --> RS2[Redis Slave 2:6381]

        APP --> UC[User Cache Service]
        APP --> SC[Session Cache Service]
        APP --> PC[Payment Cache Service]
        APP --> RLC[Rate Limit Cache]

        UC --> RC
        SC --> RC
        PC --> RC
        RLC --> RC
    end

    subgraph "Data Layer"
        APP --> US[User Service]
        APP --> PS[Payment Service]
        APP --> HS[Health Service]
        APP --> WS[WebSocket Service]

        US --> PG[(PostgreSQL Neon)]
        PS --> PG
        HS --> PG
        WS --> PG
    end

    subgraph "Monitoring"
        HS --> HC[Health Checks]
        HC --> APP
        HC --> RC
        HC --> PG
    end

    subgraph "Infrastructure Services"
        DC[Docker Compose]
        AL[Alembic Migrations]
        AL --> PG
    end
```

### Сетевая топология

```mermaid
graph LR
    subgraph "Ports Configuration"
        P1[8080: HTTP] --> NGINX
        P2[8443: HTTPS] --> NGINX
        P3[8081: App Port] --> APP
        P4[6379: Redis Master] --> REDIS_M
        P5[6380: Redis Slave1] --> REDIS_S1
        P6[6381: Redis Slave2] --> REDIS_S2
    end
```

## 🚀 Быстрый старт

### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd telegram-bot
```

### 2. Настройка окружения

```bash
# Копирование шаблона окружения
cp .env.example .env

# Генерация SSL сертификатов (для локальной разработки)
chmod +x ssl/generate-ssl.sh
./ssl/generate-ssl.sh
```

### 3. Конфигурация переменных окружения

Отредактируйте файл `.env`:

```env
# Telegram Bot Configuration
TELEGRAM_TOKEN=your_telegram_bot_token_here
WEBHOOK_HOST=your-domain.com
WEBHOOK_PORT=8443
WEBHOOK_PATH=/webhook

# Payment System - Heleket Configuration
MERCHANT_UUID=your_merchant_uuid_here
API_KEY=your_api_key_here
PAYMENT_TIMEOUT=300

# Database Configuration (Neon PostgreSQL)
DATABASE_URL=postgresql+asyncpg://username:password@host.neon.tech/database?ssl=require
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=30

# Redis Cluster Configuration
REDIS_MASTER_HOST=redis-master
REDIS_MASTER_PORT=6379
REDIS_SLAVE1_HOST=redis-slave-1
REDIS_SLAVE1_PORT=6380
REDIS_SLAVE2_HOST=redis-slave-2
REDIS_SLAVE2_PORT=6381
REDIS_PASSWORD=your_redis_password

# Circuit Breaker Configuration
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60
CIRCUIT_BREAKER_EXPECTED_EXCEPTION=Exception

# Rate Limiting Configuration
RATE_LIMIT_REQUESTS_PER_MINUTE=60
RATE_LIMIT_BURST=10

# Application Configuration
DEBUG=False
LOG_LEVEL=INFO
ENVIRONMENT=production
HEALTH_CHECK_INTERVAL=30

# SSL Configuration
SSL_CERT_PATH=/app/ssl/cert.pem
SSL_KEY_PATH=/app/ssl/key.pem
```

### 4. Запуск через Docker Compose

```bash
# Сборка и запуск всех сервисов
docker-compose up -d --build

# Проверка статуса всех сервисов
docker-compose ps

# Просмотр логов конкретного сервиса
docker-compose logs telegram-bot --tail=50
docker-compose logs redis-master --tail=30
docker-compose logs nginx --tail=30

# Проверка health checks
curl -k https://localhost:8443/health
curl http://localhost:8080/health
```

### 5. Инициализация базы данных

```bash
# Применение миграций через Docker
docker-compose exec telegram-bot alembic upgrade head

# Проверка состояния миграций
docker-compose exec telegram-bot alembic current
```

### 6. Запуск в development режиме

```bash
# Создание виртуального окружения
python -m venv venv
source venv/bin/activate  # Для Windows: venv\Scripts\activate

# Установка зависимостей
pip install -r requirements.txt

# Локальный запуск Redis (если не используется Docker)
redis-server redis/redis.conf

# Применение миграций
alembic upgrade head

# Запуск приложения
python main.py
```

## 📁 Структура проекта

```
telegram-bot/
├── alembic/                    # Миграции базы данных
│   ├── versions/              # Файлы миграций
│   ├── env.py                # Конфигурация Alembic
│   └── alembic.ini           # Настройки Alembic
├── config/                    # Конфигурация
│   ├── __init__.py
│   └── settings.py           # Настройки приложения
├── core/                     # Ядро приложения
│   ├── __init__.py
│   └── interfaces.py         # Интерфейсы для SOLID
├── handlers/                 # Обработчики
│   ├── __init__.py
│   └── message_handler.py    # Telegram команды
├── repositories/             # Репозитории
│   ├── __init__.py
│   └── user_repository.py    # Работа с PostgreSQL
├── services/                 # Бизнес-логика и микросервисы
│   ├── __init__.py
│   ├── payment_service.py    # Интеграция с Heleket
│   ├── cache_service.py      # Redis кеширование
│   ├── user_cache.py         # Кеширование пользователей
│   ├── session_cache.py      # Кеширование сессий
│   ├── payment_cache.py      # Кеширование платежей
│   ├── rate_limit_cache.py   # Кеширование лимитов
│   ├── health_service.py     # Health check сервис
│   ├── websocket_service.py  # WebSocket обработка
│   └── circuit_breaker.py    # Circuit breaker pattern
├── utils/                    # Утилиты
│   └── __init__.py
├── nginx/                    # Nginx конфигурация
│   ├── nginx.conf           # Базовая конфигурация
│   ├── nginx.ssl.conf       # SSL конфигурация
│   └── conf.d/              # Дополнительные конфиги
├── redis/                    # Redis конфигурация
│   └── redis.conf           # Конфигурация Redis
├── ssl/                      # SSL сертификаты
│   ├── cert.pem
│   ├── key.pem
│   └── generate-ssl.sh      # Скрипт генерации SSL
├── docker-compose.yml        # Docker сервисы
├── Dockerfile               # Контейнер приложения
├── main.py                  # Точка входа
├── requirements.txt         # Зависимости
└── README.md               # Документация
```

## 🔧 Сервисы Docker Compose

| Сервис         | Порт           | Описание                          |
| -------------- | -------------- | --------------------------------- |
| telegram-bot   | 8081           | Основное приложение               |
| nginx          | 80, 443, 8080  | Reverse proxy с SSL               |
| redis-master   | 6379           | Redis master нода                 |
| redis-slave-1  | 6380           | Redis slave нода 1                |
| redis-slave-2  | 6381           | Redis slave нода 2                |
| PostgreSQL     | Внешний (Neon) | Облачная база данных              |

## 🔄 Управление миграциями

### Создание новой миграции

```bash
# Автоматическое создание миграции через Docker
docker-compose exec telegram-bot alembic revision --autogenerate -m "Add new table"

# Локальное создание миграции
alembic revision --autogenerate -m "Description"
```

### Применение миграций

```bash
# Через Docker
docker-compose exec telegram-bot alembic upgrade head

# Локально
alembic upgrade head

# Применение до конкретной ревизии
alembic upgrade abc123
```

### Откат миграций

```bash
# Откат последней миграции
docker-compose exec telegram-bot alembic downgrade -1

# Откат до конкретной ревизии
docker-compose exec telegram-bot alembic downgrade abc123
```

## 💳 Покупка звезд через Heleket

### Процесс покупки с кешированием

```mermaid
sequenceDiagram
    participant User as Пользователь
    participant Bot as Telegram Bot
    participant Cache as Redis Cache
    participant CB as Circuit Breaker
    participant Heleket as Heleket API
    participant DB as PostgreSQL

    User->>Bot: Нажимает "Покупка Звезд"
    Bot->>Cache: Проверка кеша пакетов
    Cache-->>Bot: Возвращает кешированные пакеты

    Bot->>User: Показывает пакеты звезд
    User->>Bot: Выбирает пакет

    Bot->>CB: Проверка состояния circuit breaker
    CB->>Heleket: Создает счет на оплату (если CB открыт)
    Heleket->>Bot: Возвращает ссылку на оплату

    Bot->>Cache: Кеширует данные счета
    Bot->>User: Отправляет ссылку на оплату

    User->>Heleket: Оплачивает счет
    User->>Bot: Проверяет статус оплаты

    Bot->>Cache: Проверка кеша статуса
    Cache-->>Bot: Статус не найден

    Bot->>CB: Проверка circuit breaker
    CB->>Heleket: Проверяет статус счета
    Heleket->>Bot: Подтверждает оплату

    Bot->>Cache: Обновляет кеш статуса
    Bot->>DB: Обновляет баланс пользователя
    Bot->>User: Подтверждает покупку
```

### Доступные пакеты

- **100 звезд** - базовый пакет
- **250 звезд** - стандартный пакет
- **500 звезд** - расширенный пакет
- **1000 звезд** - максимальный пакет
- **Своя сумма** - индивидуальная покупка

## 📊 Мониторинг и Health Checks

### Health Check Endpoints

```bash
# Проверка общего состояния
curl -k https://localhost:8443/health
curl http://localhost:8080/health

# Проверка состояния базы данных
curl -k https://localhost:8443/health/db

# Проверка состояния Redis
curl -k https://localhost:8443/health/redis

# Проверка состояния платежной системы
curl -k https://localhost:8443/health/payment
```

### Docker health checks

```bash
# Проверка всех сервисов
docker-compose ps

# Подробная информация о health checks
docker inspect telegram-bot | jq '.[0].State.Health'

# Просмотр логов health checks
docker-compose logs telegram-bot | grep "health"
```

### Мониторинг через CLI

```bash
# Проверка ресурсов
docker stats

# Просмотр логов в реальном времени
docker-compose logs -f telegram-bot

# Проверка состояния Redis кластера
docker-compose exec redis-master redis-cli -a $REDIS_PASSWORD info replication

# Проверка PostgreSQL подключения
docker-compose exec telegram-bot python -c "from config.settings import settings; print('DB connected' if settings.database_url else 'DB not configured')"
```

## 🛠️ Переменные окружения

### Обязательные переменные

```env
# Telegram Bot Configuration
TELEGRAM_TOKEN=ваш_токен_бота от @BotFather
WEBHOOK_HOST=your-domain.com
WEBHOOK_PORT=8443
WEBHOOK_PATH=/webhook

# Payment System - Heleket Configuration
MERCHANT_UUID=ваш_merchant_uuid от Heleket
API_KEY=ваш_api_key от Heleket
PAYMENT_TIMEOUT=300

# Database Configuration (Neon PostgreSQL)
DATABASE_URL=postgresql+asyncpg://username:password@host.neon.tech/database?ssl=require
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=30

# Redis Cluster Configuration
REDIS_MASTER_HOST=redis-master
REDIS_MASTER_PORT=6379
REDIS_SLAVE1_HOST=redis-slave-1
REDIS_SLAVE1_PORT=6380
REDIS_SLAVE2_HOST=redis-slave-2
REDIS_SLAVE2_PORT=6381
REDIS_PASSWORD=your_secure_redis_password
```

### Опциональные переменные

```env
# Application Configuration
DEBUG=False
LOG_LEVEL=INFO
ENVIRONMENT=production
HEALTH_CHECK_INTERVAL=30

# Circuit Breaker Configuration
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60
CIRCUIT_BREAKER_EXPECTED_EXCEPTION=Exception

# Rate Limiting Configuration
RATE_LIMIT_REQUESTS_PER_MINUTE=60
RATE_LIMIT_BURST=10

# SSL Configuration
SSL_CERT_PATH=/app/ssl/cert.pem
SSL_KEY_PATH=/app/ssl/key.pem

# Redis Advanced Configuration
REDIS_MAX_CONNECTIONS=100
REDIS_SOCKET_TIMEOUT=5
REDIS_SOCKET_CONNECT_TIMEOUT=5
REDIS_RETRY_ON_TIMEOUT=True
```

## 🎯 Команды для разработки

### Docker команды

```bash
# Запуск всех сервисов
docker-compose up -d

# Запуск с пересборкой
docker-compose up -d --build

# Остановка всех сервисов
docker-compose down

# Остановка с удалением томов
docker-compose down -v

# Перезапуск конкретного сервиса
docker-compose restart telegram-bot

# Логи всех сервисов
docker-compose logs -f

# Логи конкретного сервиса
docker-compose logs telegram-bot --tail=100

# Выполнение команд в контейнере
docker-compose exec telegram-bot python main.py --check-connections
```

### Development команды

```bash
# Установка зависимостей
pip install -r requirements.txt

# Применение миграций
alembic upgrade head

# Запуск с hot reload
python main.py

# Проверка типов
mypy .

# Форматирование кода
black .
isort .

# Проверка стиля
flake8 .
```

### Redis команды

```bash
# Подключение к Redis master
docker-compose exec redis-master redis-cli -a $REDIS_PASSWORD

# Проверка репликации
docker-compose exec redis-master redis-cli -a $REDIS_PASSWORD info replication

# Просмотр всех ключей
docker-compose exec redis-master redis-cli -a $REDIS_PASSWORD keys "*"

# Очистка кеша
docker-compose exec redis-master redis-cli -a $REDIS_PASSWORD flushall
```

## 🔒 Безопасность

- **SSL/TLS** - обязательное шифрование соединений через Nginx
- **PostgreSQL** - параметризованные запросы и SSL соединения
- **Redis** - аутентификация и шифрование соединений
- **API ключи** - безопасное хранение в .env файлах
- **Rate limiting** - многоуровневая защита (Nginx + приложение)
- **Circuit breaker** - защита от каскадных отказов
- **Input validation** - проверка всех входных данных
- **Payment security** - безопасная обработка платежей через Heleket
- **Docker security** - изолированные контейнеры и минимальные привилегии

## 🐛 Решение проблем

### Проблемы с Docker Compose

```bash
# Проверка конфигурации
docker-compose config

# Проверка логов всех сервисов
docker-compose logs --tail=50

# Пересборка без кеша
docker-compose build --no-cache
docker-compose up -d

# Очистка Docker системы
docker system prune -f
docker volume prune -f
```

### Проблемы с Redis кластером

```bash
# Проверка состояния Redis master
docker-compose exec redis-master redis-cli -a $REDIS_PASSWORD ping

# Проверка репликации
docker-compose exec redis-master redis-cli -a $REDIS_PASSWORD info replication

# Проверка подключения slave нод
docker-compose exec redis-slave-1 redis-cli -a $REDIS_PASSWORD info replication

# Перезапуск Redis сервисов
docker-compose restart redis-master redis-slave-1 redis-slave-2
```

### Проблемы с базой данных

```bash
# Проверка подключения к PostgreSQL
docker-compose exec telegram-bot alembic current

# Применение отсутствующих миграций
docker-compose exec telegram-bot alembic upgrade head

# Проверка переменных окружения
docker-compose exec telegram-bot env | grep DATABASE

# Сброс базы (осторожно!)
docker-compose exec telegram-bot alembic downgrade base
docker-compose exec telegram-bot alembic upgrade head
```

### Проблемы с SSL сертификатами

```bash
# Проверка SSL сертификатов
openssl x509 -in ssl/cert.pem -text -noout

# Проверка приватного ключа
openssl rsa -in ssl/key.pem -check

# Генерация новых самоподписанных сертификатов
./ssl/generate-ssl.sh

# Перезапуск Nginx
docker-compose restart nginx
```

### Проблемы с circuit breaker

```bash
# Проверка состояния circuit breaker
docker-compose logs telegram-bot | grep "circuit_breaker"

# Сброс circuit breaker
docker-compose restart telegram-bot

# Проверка логов ошибок
docker-compose logs telegram-bot | grep -i error
```

### Проблемы с rate limiting

```bash
# Проверка rate limit логов
docker-compose logs telegram-bot | grep "rate_limit"

# Очистка rate limit кеша
docker-compose exec redis-master redis-cli -a $REDIS_PASSWORD del rate_limit:*

# Проверка текущих лимитов
docker-compose exec telegram-bot python -c "from services.rate_limit_cache import RateLimitCache; import asyncio; print(asyncio.run(RateLimitCache().get_rate_limit_status('test_user')))"
```

### Проблемы с портами

```bash
# Проверка занятых портов
netstat -tulpn | grep -E '8080|8443|8081|6379|6380|6381'

# Изменение портов в .env
# Отредактируйте docker-compose.yml или .env файл

# Перезапуск с новыми портами
docker-compose down
docker-compose up -d
```

## 📈 Производительность и масштабирование

### Мониторинг производительности

```bash
# Проверка использования ресурсов
docker stats

# Проверка нагрузки на Redis
docker-compose exec redis-master redis-cli -a $REDIS_PASSWORD info stats | grep keyspace

# Проверка пула соединений PostgreSQL
docker-compose exec telegram-bot python -c "from repositories.user_repository import UserRepository; import asyncio; print(asyncio.run(UserRepository().check_connection_pool()))"
```

### Горизонтальное масштабирование

```yaml
# Пример масштабирования в docker-compose.yml
services:
  telegram-bot:
    deploy:
      replicas: 3
    environment:
      - REDIS_MASTER_HOST=redis-cluster
```

### Настройка production окружения

```bash
# Production деплой с SSL
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Настройка мониторинга
docker-compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```

## 🤝 Contributing

1. Fork репозитория
2. Создайте ветку: `git checkout -b feature/AmazingFeature`
3. Обновите документацию при необходимости
4. Создайте миграцию при изменении схемы: `alembic revision --autogenerate -m "Add feature"`
5. Протестируйте с Docker: `docker-compose up -d --build`
6. Сделайте коммит: `git commit -m 'Add some AmazingFeature'`
7. Отправьте изменения: `git push origin feature/AmazingFeature`
8. Создайте Pull Request

## 📄 License

MIT License - см. файл LICENSE для деталей.

## 🆘 Поддержка

Если возникли проблемы:

1. Проверьте логи: `docker-compose logs telegram-bot`
2. Проверьте health checks: `curl -k https://localhost:8443/health`
3. Проверьте переменные окружения в `.env`
4. Проверьте миграции: `docker-compose exec telegram-bot alembic current`
5. Проверьте подключение к Neon PostgreSQL
6. Проверьте Redis кластер: `docker-compose exec redis-master redis-cli -a $REDIS_PASSWORD ping`
7. Создайте issue с описанием проблемы, логами и конфигурацией

## 📚 Дополнительные ресурсы

- [Aiogram Documentation](https://docs.aiogram.dev/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Heleket API Documentation](https://heleket.com/docs)
- [Neon PostgreSQL](https://neon.tech/docs)
- [Redis Cluster Documentation](https://redis.io/docs/manual/scaling/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Nginx SSL Configuration](https://nginx.org/en/docs/http/configuring_https_servers.html)
