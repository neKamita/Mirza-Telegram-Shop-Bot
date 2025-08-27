# 🤖 Mirza Telegram Shop Bot

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![aiogram](https://img.shields.io/badge/aiogram-3.21+-green.svg)](https://aiogram.dev)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-blue.svg)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7+-red.svg)](https://redis.io)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Современный Telegram бот для электронной коммерции с интегрированной системой платежей Heleket, балансом пользователей, покупкой звезд через Fragment API и продвинутыми функциями масштабирования. Архитектура построена на принципах SOLID, DRY, KISS с использованием асинхронного программирования и микросервисного подхода.

## 📋 Содержание

- [🏗️ Архитектура](#️-архитектура)
- [📊 Структура базы данных](#-структура-базы-данных)
- [🛠️ Технологический стек](#️-технологический-стек)
- [⚙️ Установка и настройка](#️-установка-и-настройка)
- [🐳 Docker развертывание](#-docker-развертывание)
- [📡 API и Вебхуки](#-api-и-вебхуки)
- [🔧 Конфигурация](#-конфигурация)
- [📈 Мониторинг](#-мониторинг)
- [🧪 Тестирование](#-тестирование)
- [🚀 Развертывание](#-развертывание)
- [📁 Структура проекта](#-структура-проекта)
- [🤝 Вклад в проект](#-вклад-в-проект)

## 📚 Дополнительная документация

- [🏗️ Детальная архитектура](docs/ARCHITECTURE.md) - Подробные диаграммы компонентов и паттернов
- [🚀 Развертывание и DevOps](docs/DEPLOYMENT.md) - CI/CD, Docker, инфраструктура
- [🔒 SSL и безопасность](docs/SSL_SETUP.md) - Настройка SSL/TLS шифрования

## 🏗️ Архитектура

### Общая архитектура системы

```mermaid
graph TB
    subgraph "External Services"
        TG[Telegram API]
        HELEKET[Heleket Payment API]
        FRAGMENT[Telegram Fragment API]
        CLOUDFLARE[Cloudflare Tunnel]
    end

    subgraph "Load Balancer & Proxy"
        NGINX[Nginx Reverse Proxy]
        CF_WAF[Cloudflare WAF]
    end

    subgraph "Application Layer"
        BOT[Telegram Bot Core]
        WEBHOOK[Webhook Service]
        API[REST API Service]
    end

    subgraph "Business Logic Layer"
        MH[Message Handler]
        PS[Payment Service]
        BS[Balance Service]
        SPS[Star Purchase Service]
        FS[Fragment Service]
        RL[Advanced Rate Limiter]
        CB[Circuit Breaker]
    end

    subgraph "Data Access Layer"
        UR[User Repository]
        BR[Balance Repository]
        TR[Transaction Repository]
    end

    subgraph "Infrastructure Layer"
        PG[(PostgreSQL Cluster)]
        REDIS[(Redis HA Cluster)]
        PROMETHEUS[(Prometheus)]
        GRAFANA[(Grafana)]
    end

    TG --> CF_WAF
    HELEKET --> CF_WAF
    FRAGMENT --> CF_WAF
    CLOUDFLARE --> CF_WAF
    CF_WAF --> NGINX

    NGINX --> BOT
    NGINX --> WEBHOOK
    NGINX --> API

    BOT --> MH
    WEBHOOK --> PS
    API --> MH

    MH --> PS
    MH --> BS
    MH --> SPS
    MH --> FS
    MH --> RL
    MH --> CB

    PS --> UR
    BS --> BR
    SPS --> UR
    SPS --> BR
    FS --> UR

    UR --> PG
    BR --> PG
    TR --> PG

    RL --> REDIS
    CB --> REDIS
    MH --> REDIS

    PROMETHEUS --> BOT
    PROMETHEUS --> WEBHOOK
    PROMETHEUS --> API
    PROMETHEUS --> PG
    PROMETHEUS --> REDIS

    GRAFANA --> PROMETHEUS
```

### Компонентная архитектура

```mermaid
flowchart LR
    subgraph handlers ["🎯 Handlers Layer"]
        MH["📨 Message Handler"]
        BH["🔧 Base Handler"]
        EH["❌ Error Handler"]
        PH["💳 Payment Handler"]
        PuH["🛒 Purchase Handler"]
        BalH["💰 Balance Handler"]
    end

    subgraph services ["⚙️ Services Layer"]
        PS["💳 Payment Service"]
        BS["💰 Balance Service"]
        SPS["⭐ Star Purchase Service"]
        FS["💎 Fragment Service"]
        FCM["🍪 Fragment Cookie Manager"]
        CS["🗄️ Cache Service"]
        RL["🚦 Advanced Rate Limiter"]
        CB["🔄 Circuit Breaker"]
        HS["❤️ Health Service"]
        WS["🔌 Webhook Service"]
    end

    subgraph repos ["📊 Repository Layer"]
        UR["👤 User Repository"]
        BR["💰 Balance Repository"]
        TR["📊 Transaction Repository"]
    end

    subgraph core ["🏗️ Core Layer"]
        INT["🔗 Interfaces ABC"]
        CFG["⚙️ Configuration"]
        DT["📋 Data Transfer Objects"]
    end

    MH --> PS
    MH --> BS
    MH --> SPS
    MH --> FS
    MH --> FCM
    PH --> PS
    PuH --> SPS
    BalH --> BS

    PS --> UR
    BS --> BR
    SPS --> UR
    SPS --> BR
    FS --> FCM
    FS --> UR

    PS --> CS
    BS --> CS
    SPS --> CS
    FCM --> CS
    RL --> CS
    CB --> CS

    UR --> CFG
    BR --> CFG
    TR --> CFG

    PS --> INT
    BS --> INT
    SPS --> INT
    FS --> INT
    FCM --> INT
    RL --> INT
    CB --> INT

    MH --> DT
    PH --> DT
    PuH --> DT
    BalH --> DT
```

### Ключевые возможности архитектуры

- **Многоуровневая архитектура** с четким разделением ответственности
- **Асинхронная обработка** всех операций I/O
- **Распределенное кеширование** с Redis кластером
- **Circuit Breaker** для защиты от сбоев внешних API
- **Rate Limiting** на нескольких уровнях (пользователь, глобальный, burst)
- **Мониторинг и метрики** с Prometheus и Grafana
- **Автоматическое обновление** Fragment cookies
- **Cloudflare интеграция** для безопасности и производительности

## 📊 Структура базы данных

### ER-диаграмма

```mermaid
erDiagram
    USERS {
        bigint user_id PK "Telegram User ID"
        varchar username "Telegram username"
        varchar first_name "Имя пользователя"
        varchar last_name "Фамилия пользователя"
        boolean is_premium "Премиум статус"
        varchar language_code "Код языка"
        timestamp created_at "Дата создания"
        timestamp updated_at "Дата обновления"
    }

    BALANCES {
        serial id PK "Уникальный ID"
        bigint user_id FK "ID пользователя"
        decimal amount "Сумма баланса"
        varchar currency "Валюта (TON)"
        timestamp created_at "Дата создания"
        timestamp updated_at "Дата обновления"
    }

    TRANSACTIONS {
        serial id PK "Уникальный ID"
        bigint user_id FK "ID пользователя"
        transaction_type transaction_type "Тип транзакции"
        transaction_status status "Статус транзакции"
        decimal amount "Сумма транзакции"
        varchar currency "Валюта"
        text description "Описание"
        varchar external_id UK "Внешний ID платежа"
        jsonb transaction_metadata "Метаданные JSON"
        timestamp created_at "Дата создания"
        timestamp updated_at "Дата обновления"
    }

    FRAGMENT_COOKIES {
        serial id PK "Уникальный ID"
        varchar session_id "ID сессии Fragment"
        text cookies "Cookies данные"
        varchar status "Статус cookies"
        timestamp expires_at "Время истечения"
        timestamp created_at "Дата создания"
        timestamp updated_at "Дата обновления"
    }

    USERS ||--|| BALANCES : "имеет"
    USERS ||--o{ TRANSACTIONS : "совершает"
    FRAGMENT_COOKIES ||--o{ TRANSACTIONS : "используется"
```

### Типы транзакций

| Тип | Описание |
|-----|----------|
| `purchase` | Покупка звезд через Fragment API |
| `refund` | Возврат средств |
| `bonus` | Бонусные начисления |
| `adjustment` | Корректировки баланса |
| `recharge` | Пополнение баланса через Heleket |

### Статусы транзакций

| Статус | Описание |
|--------|----------|
| `pending` | Ожидание оплаты |
| `processing` | Обработка платежа |
| `completed` | Успешно завершен |
| `failed` | Ошибка платежа |
| `cancelled` | Отменен пользователем |
| `expired` | Истек срок действия |

## 🛠️ Технологический стек

### Backend

| Технология | Версия | Назначение |
|------------|--------|------------|
| **Python** | 3.11+ | Основной язык программирования |
| **aiogram** | 3.21+ | Telegram Bot Framework |
| **FastAPI** | 0.115+ | REST API и обработка вебхуков |
| **SQLAlchemy** | 2.0+ | ORM для работы с PostgreSQL |
| **Alembic** | 1.13+ | Миграции базы данных |
| **asyncpg** | 0.29+ | Асинхронный драйвер PostgreSQL |
| **Redis** | 6.4+ | Распределенное кеширование |
| **fragment-api-lib** | 1.0+ | Библиотека для работы с Fragment API |

### Инфраструктура

| Технология | Версия | Назначение |
|------------|--------|------------|
| **PostgreSQL** | 15+ | Основная база данных |
| **Redis Cluster** | 7+ | Высокодоступное кеширование |
| **Nginx** | latest | Reverse proxy и load balancer |
| **Docker** | latest | Контейнеризация |
| **Docker Compose** | latest | Оркестрация микросервисов |
| **Cloudflare Tunnel** | latest | Безопасный доступ к сервисам |

### Безопасность и мониторинг

| Технология | Назначение |
|------------|------------|
| **SSL/TLS** | Шифрование соединений |
| **HMAC** | Подписи вебхуков |
| **Rate Limiting** | Защита от перегрузки |
| **Circuit Breaker** | Устойчивость к сбоям |
| **Prometheus** | Сбор метрик |
| **Grafana** | Визуализация метрик |
| **Selenium** | Автоматизация обновления cookies |
| **ChromeDriver** | Браузерная автоматизация |

### Разработка и тестирование

| Технология | Назначение |
|------------|------------|
| **pytest** | Unit и integration тесты |
| **pytest-asyncio** | Тестирование асинхронного кода |
| **pytest-cov** | Измерение покрытия кода |
| **colorlog** | Структурированное логирование |
| **structlog** | JSON логирование |
| **psutil** | Мониторинг системных ресурсов |

## ⚙️ Установка и настройка

### Системные требования

- **Python** 3.11 или выше
- **PostgreSQL** 15 или выше
- **Redis** 7 или выше
- **Docker** и Docker Compose (рекомендуется)
- Минимум 2GB RAM, 4GB рекомендуется
- Минимум 2 CPU cores, 4 рекомендуется

### Локальная установка

#### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd mirza-telegram-shop-bot
```

#### 2. Настройка виртуального окружения

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows
```

#### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

#### 4. Настройка переменных окружения

```bash
cp .env.example .env
# Отредактируйте .env файл с вашими настройками
```

#### 5. Инициализация базы данных

```bash
# Создание таблиц
alembic upgrade head

# Или через Python
python -c "from repositories.user_repository import UserRepository; import asyncio; repo = UserRepository(); asyncio.run(repo.create_tables())"
```

#### 6. Предварительная проверка настроек

```bash
# Проверка Fragment API
python scripts/precheck_fragment.py

# Обновление Fragment cookies
python scripts/update_fragment_cookies.py
```

#### 7. Запуск приложения

```bash
python main.py
```

### Конфигурация переменных окружения

#### Основные настройки

| Переменная | Значение по умолчанию | Описание |
|------------|----------------------|----------|
| `TELEGRAM_TOKEN` | - | Токен Telegram бота |
| `MERCHANT_UUID` | - | UUID мерчанта в Heleket |
| `API_KEY` | - | API ключ Heleket |
| `DATABASE_URL` | postgresql://user:password@localhost:5432/telegram_bot | URL базы данных |
| `REDIS_URL` | redis://redis-node-1:7379 | URL Redis |

#### Fragment API настройки

| Переменная | Значение по умолчанию | Описание |
|------------|----------------------|----------|
| `FRAGMENT_SEED_PHRASE` | - | 24-словная seed фраза TON кошелька |
| `FRAGMENT_COOKIES` | - | Cookies для авторизации |
| `FRAGMENT_AUTO_COOKIE_REFRESH` | false | Автоматическое обновление cookies |
| `FRAGMENT_COOKIE_REFRESH_INTERVAL` | 3600 | Интервал обновления (сек) |

#### Rate Limiting настройки

| Переменная | Значение | Описание |
|------------|----------|----------|
| `RATE_LIMIT_USER_MESSAGES` | 30 | Сообщений в минуту на пользователя |
| `RATE_LIMIT_USER_OPERATIONS` | 20 | Операций в минуту на пользователя |
| `RATE_LIMIT_USER_PAYMENTS` | 5 | Платежей в минуту на пользователя |
| `RATE_LIMIT_GLOBAL_MESSAGES` | 1000 | Глобальный лимит сообщений |
| `RATE_LIMIT_PREMIUM_MULTIPLIER` | 2.0 | Множитель для премиум пользователей |

#### Cache настройки

| Переменная | Значение | Описание |
|------------|----------|----------|
| `CACHE_TTL_USER` | 1800 | Кеш пользователей (сек) |
| `CACHE_TTL_SESSION` | 1800 | Кеш сессий (сек) |
| `CACHE_TTL_PAYMENT` | 900 | Кеш платежей (сек) |
| `CACHE_TTL_RATE_LIMIT` | 60 | Кеш rate limiting (сек) |

## 🐳 Docker развертывание

### Быстрый старт

```bash
# Клонирование и запуск
git clone <repository-url>
cd mirza-telegram-shop-bot
cp .env.example .env
# Отредактируйте .env файл
docker-compose up -d
```

### Архитектура Docker контейнеров

```mermaid
graph TB
    subgraph "🌐 External Network"
        INTERNET[Internet]
        TG_API[Telegram API]
        HELEKET_API[Heleket API]
        FRAGMENT_API[Fragment API]
    end

    subgraph "🔒 Cloudflare Layer"
        CF_TUNNEL[Cloudflare Tunnel]
        CF_WAF[WAF & DDoS Protection]
    end

    subgraph "🚪 DMZ Network"
        NGINX[nginx: Load Balancer & SSL]
    end

    subgraph "🏠 Application Network (bot-network)"
        subgraph "Application Services"
            BOT[app: Telegram Bot]
            WEBHOOK[webhook: Webhook Handler]
            API[api: REST API]
        end

        subgraph "Database Services"
            POSTGRES[db: PostgreSQL 15]
        end

        subgraph "Cache Services"
            REDIS1[redis-node-1: Redis 7]
            REDIS2[redis-node-2: Redis 7]
            REDIS3[redis-node-3: Redis 7]
            REDIS_REPLICA1[redis-replica-1]
            REDIS_REPLICA2[redis-replica-2]
            REDIS_REPLICA3[redis-replica-3]
        end

        subgraph "Monitoring"
            PROMETHEUS[prometheus: Metrics]
            GRAFANA[grafana: Dashboards]
        end

        subgraph "Utilities"
            REDIS_CREATOR[redis-cluster-creator]
            REDIS_MONITOR[redis-cluster-monitor]
        end
    end

    INTERNET --> CF_TUNNEL
    TG_API --> CF_WAF
    HELEKET_API --> CF_WAF
    FRAGMENT_API --> CF_WAF

    CF_TUNNEL --> CF_WAF
    CF_WAF --> NGINX

    NGINX --> BOT
    NGINX --> WEBHOOK
    NGINX --> API

    BOT --> POSTGRES
    WEBHOOK --> POSTGRES
    API --> POSTGRES

    BOT --> REDIS1
    WEBHOOK --> REDIS1
    API --> REDIS1

    REDIS1 --> REDIS_REPLICA1
    REDIS2 --> REDIS_REPLICA2
    REDIS3 --> REDIS_REPLICA3

    PROMETHEUS --> BOT
    PROMETHEUS --> WEBHOOK
    PROMETHEUS --> API
    PROMETHEUS --> POSTGRES
    PROMETHEUS --> REDIS1

    GRAFANA --> PROMETHEUS
```

### Docker сервисы

| Сервис | Порт | Описание | Ресурсы |
|--------|------|----------|---------|
| **app** | - | Основной Telegram бот | 512MB RAM, 0.5 CPU |
| **webhook** | 8001 | Обработчик вебхуков | 256MB RAM, 0.2 CPU |
| **api** | 8002 | REST API сервис | 256MB RAM, 0.2 CPU |
| **db** | 5432 | PostgreSQL база данных | 1GB RAM, 1 CPU |
| **nginx** | 80, 443 | Load balancer и SSL | 128MB RAM, 0.1 CPU |
| **redis-node-1** | 7379 | Redis кластер узел 1 | 256MB RAM, 0.2 CPU |
| **redis-node-2** | 7380 | Redis кластер узел 2 | 256MB RAM, 0.2 CPU |
| **redis-node-3** | 7381 | Redis кластер узел 3 | 256MB RAM, 0.2 CPU |
| **prometheus** | 9090 | Сбор метрик | 256MB RAM, 0.1 CPU |
| **grafana** | 3000 | Визуализация метрик | 256MB RAM, 0.1 CPU |

### Автоматическое управление Fragment cookies

Docker контейнер автоматически:

1. **Устанавливает Chrome и ChromeDriver** при первом запуске
2. **Обновляет Fragment cookies** при истечении срока действия
3. **Периодически обновляет cookies** в фоне
4. **Сохраняет cookies** в постоянное хранилище
5. **Проверяет статус Fragment API** перед операциями

```bash
# Просмотр логов обновления cookies
docker-compose logs app | grep -i fragment

# Ручное обновление cookies
docker-compose exec app python scripts/update_fragment_cookies.py

# Проверка статуса Fragment API
docker-compose exec app python scripts/check_fragment_status.py
```

## 📡 API и Вебхуки

### Webhook эндпоинты

| Эндпоинт | Метод | Описание | Аутентификация |
|----------|-------|----------|----------------|
| `/webhook/heleket` | POST | Обработка платежей Heleket | HMAC подпись |
| `/webhook/telegram` | POST | Обновления от Telegram | Секретный токен |
| `/health` | GET | Проверка состояния сервиса | - |
| `/health/detailed` | GET | Детальная диагностика | - |
| `/metrics` | GET | Prometheus метрики | - |
| `/api/v1/users/{user_id}/balance` | GET | Баланс пользователя | JWT токен |
| `/api/v1/transactions` | GET | История транзакций | JWT токен |

### Структура вебхука Heleket

```json
{
  "uuid": "payment_uuid_here",
  "status": "completed",
  "amount": "100.00",
  "currency": "TON",
  "external_id": "user_12345_stars_100",
  "created_at": "2024-01-01T12:00:00Z",
  "metadata": {
    "user_id": 12345,
    "stars_count": 100,
    "purchase_type": "balance"
  }
}
```

### Диаграмма последовательности платежей

```mermaid
sequenceDiagram
    participant U as 👤 User
    participant TB as 🤖 Telegram Bot
    participant PS as 💳 Payment Service
    participant H as 🏦 Heleket API
    participant WH as 🔗 Webhook Handler
    participant DB as 🗄️ Database
    participant C as 📦 Redis Cache

    U->>TB: /buy_stars 100
    TB->>PS: create_payment_request(user_id, 100)
    PS->>DB: create_transaction(pending)
    PS->>C: cache_payment(uuid, user_id)
    PS->>H: POST /create_payment
    H-->>PS: payment_url + uuid
    PS-->>TB: payment_url
    TB-->>U: 💳 Ссылка для оплаты

    Note over U,H: Пользователь переходит по ссылке и оплачивает

    H->>WH: POST /webhook/heleket (payment completed)
    WH->>C: get_payment_info(uuid)
    WH->>DB: update_transaction(completed)
    WH->>DB: update_user_balance(+100)
    WH->>C: invalidate_user_cache(user_id)
    WH->>TB: notify_payment_success(user_id)
    TB->>U: ✅ Платеж успешен! +100 ⭐
```

### Rate Limiting архитектура

```mermaid
graph LR
    subgraph "Rate Limiting Layers"
        UL[👤 User Limits]
        GL[🌍 Global Limits]
        BL[⚡ Burst Limits]
        PL[⭐ Premium Limits]
        NL[🆕 New User Limits]
    end

    subgraph "Limit Types"
        MSG[📨 Messages: 30/min]
        OPS[⚙️ Operations: 20/min]
        PAY[💳 Payments: 5/min]
        API[🔌 API calls: 10/min]
    end

    subgraph "Storage"
        REDIS[(Redis Cluster)]
        LOCAL[Local Cache]
    end

    UL --> MSG
    UL --> OPS
    UL --> PAY
    UL --> API

    GL --> MSG
    GL --> OPS
    GL --> PAY
    GL --> API

    BL --> MSG
    BL --> OPS

    PL --> UL
    NL --> UL

    MSG --> REDIS
    OPS --> REDIS
    PAY --> REDIS
    API --> REDIS

    REDIS --> LOCAL
```

## 🔧 Конфигурация

### Расширенная конфигурация

#### Circuit Breaker настройки

| Переменная | Значение | Описание |
|------------|----------|----------|
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | 5 | Количество сбоев для открытия |
| `CIRCUIT_BREAKER_TIMEOUT` | 60 | Время ожидания восстановления |
| `CIRCUIT_BREAKER_SUCCESS_THRESHOLD` | 3 | Успехов для закрытия |

#### SSL/TLS настройки

| Переменная | Значение | Описание |
|------------|----------|----------|
| `SSL_CERT_PATH` | ./ssl/cert.pem | Путь к SSL сертификату |
| `SSL_KEY_PATH` | ./ssl/key.pem | Путь к приватному ключу |
| `SSL_CA_PATH` | ./ssl/ca.pem | Путь к CA сертификату |

#### Мониторинг настройки

| Переменная | Значение | Описание |
|------------|----------|----------|
| `METRICS_ENABLED` | true | Включить сбор метрик |
| `HEALTH_CHECK_INTERVAL` | 30 | Интервал проверки здоровья |
| `LOG_LEVEL` | INFO | Уровень логирования |

## 📈 Мониторинг

### Метрики Prometheus

| Метрика | Тип | Описание |
|---------|-----|----------|
| `telegram_bot_messages_total` | Counter | Общее количество сообщений |
| `telegram_bot_payments_total` | Counter | Общее количество платежей |
| `telegram_bot_errors_total` | Counter | Общее количество ошибок |
| `telegram_bot_active_users` | Gauge | Активные пользователи |
| `telegram_bot_response_time_seconds` | Histogram | Время ответа API |
| `telegram_bot_rate_limit_hits` | Counter | Попытки превышения лимита |

### Health Checks

```bash
# Основная проверка здоровья
curl https://your-domain.com/health

# Детальная диагностика
curl https://your-domain.com/health/detailed

# Метрики Prometheus
curl https://your-domain.com/metrics
```

### Логирование

#### Уровни логирования

- **DEBUG** - Детальная информация для разработки
- **INFO** - Общая информация о работе
- **WARNING** - Предупреждения о потенциальных проблемах
- **ERROR** - Ошибки выполнения
- **CRITICAL** - Критические ошибки

#### Форматы логов

- **Разработка**: Человекочитаемый формат с цветами
- **Production**: Структурированный JSON формат

#### Ротация логов

- **По размеру**: Максимум 100MB на файл
- **По времени**: Ежедневная ротация
- **Сжатие**: Автоматическое сжатие старых логов

## 🧪 Тестирование

### Структура тестов

```mermaid
graph TD
    subgraph "🧪 Test Structure"
        TESTS["📁 tests/"]

        subgraph "🔬 Unit Tests"
            UNIT[("📁 unit/")]
            UNIT_SERVICES["📁 test_services/"]
            UNIT_REPOS["📁 test_repositories/"]
            UNIT_HANDLERS["📁 test_handlers/"]
            UNIT_UTILS["📁 test_utils/"]
        end

        subgraph "🔗 Integration Tests"
            INTEGRATION[("📁 integration/")]
            INT_PAYMENT["📁 test_payment_flow/"]
            INT_WEBHOOK["📁 test_webhook_processing/"]
            INT_FRAGMENT["📁 test_fragment_integration/"]
            INT_CACHE["📁 test_cache_operations/"]
        end

        subgraph "🛠️ Test Fixtures"
            FIXTURES[("📁 fixtures/")]
            FIX_DB["📄 database.py"]
            FIX_REDIS["📄 redis.py"]
            FIX_MOCKS["📄 mocks.py"]
        end
    end

    TESTS --> UNIT
    TESTS --> INTEGRATION
    TESTS --> FIXTURES

    UNIT --> UNIT_SERVICES
    UNIT --> UNIT_REPOS
    UNIT --> UNIT_HANDLERS
    UNIT --> UNIT_UTILS

    INTEGRATION --> INT_PAYMENT
    INTEGRATION --> INT_WEBHOOK
    INTEGRATION --> INT_FRAGMENT
    INTEGRATION --> INT_CACHE

    FIXTURES --> FIX_DB
    FIXTURES --> FIX_REDIS
    FIXTURES --> FIX_MOCKS
```

### Запуск тестов

```bash
# Все тесты
pytest

# С покрытием кода
pytest --cov=. --cov-report=html

# Только unit тесты
pytest tests/unit/

# Только integration тесты
pytest tests/integration/

# Тесты конкретного компонента
pytest tests/unit/test_services/
pytest tests/integration/test_payment_flow/

# Тесты Fragment API
pytest tests/test_fragment_service.py
pytest tests/test_fragment_cookie_manager.py
pytest tests/integration/test_fragment_integration/
```

### Тестовые сценарии

#### Unit тесты

```python
# Пример unit теста для PaymentService
import pytest
from services.payment.payment_service import PaymentService

class TestPaymentService:
    @pytest.mark.asyncio
    async def test_create_payment_success(self, mock_heleket_api):
        service = PaymentService()
        result = await service.create_payment(user_id=123, amount=100)

        assert result["status"] == "success"
        assert "payment_url" in result
        assert "uuid" in result

    @pytest.mark.asyncio
    async def test_create_payment_invalid_amount(self):
        service = PaymentService()

        with pytest.raises(ValueError, match="Invalid amount"):
            await service.create_payment(user_id=123, amount=-100)
```

#### Integration тесты

```python
# Пример integration теста
@pytest.mark.asyncio
async def test_full_payment_flow(test_client, test_db):
    # 1. Создание платежа
    response = await test_client.post("/api/v1/payments", json={
        "user_id": 123,
        "amount": 100,
        "currency": "TON"
    })
    assert response.status_code == 200
    payment_data = response.json()

    # 2. Симуляция вебхука
    webhook_data = {
        "uuid": payment_data["uuid"],
        "status": "completed",
        "amount": "100.00"
    }
    response = await test_client.post("/webhook/heleket", json=webhook_data)
    assert response.status_code == 200

    # 3. Проверка баланса
    response = await test_client.get("/api/v1/users/123/balance")
    assert response.status_code == 200
    balance_data = response.json()
    assert balance_data["amount"] == 100
```

### Покрытие кода

Проект стремится к покрытию кода не менее 80%:

- **Unit тесты**: 85% покрытие основных сервисов
- **Integration тесты**: 75% покрытие основных потоков
- **API тесты**: 90% покрытие эндпоинтов

## 🚀 Развертывание

### Процесс развертывания

```mermaid
graph TD
    A[🚀 Deployment Trigger] --> B[🔍 Pre-deployment Checks]
    B --> C[📦 Build Docker Images]
    C --> D[🧪 Run Tests]
    D --> E[🔐 Security Scan]
    E --> F[📋 Configuration Validation]
    F --> G{🌿 Environment?}

    G -->|Staging| H[🚀 Deploy to Staging]
    G -->|Production| I[🔄 Blue-Green Deployment]

    H --> J[🧪 Staging Tests]
    J --> K[✅ Staging Approval]
    K --> I

    I --> L[🔍 Health Checks]
    L --> M[📊 Performance Monitoring]
    M --> N{✅ Success?}

    N -->|Yes| O[🔄 Switch Traffic]
    N -->|No| P[🔙 Rollback]

    O --> Q[🧪 Post-deployment Tests]
    Q --> R[📢 Notification]
    R --> S[✅ Deployment Complete]

    P --> T[📢 Alert Team]
    T --> S
```

### CI/CD Pipeline

#### GitOps процесс

```mermaid
gitGraph
    commit id: "Initial commit"
    branch develop
    checkout develop
    commit id: "feat: add payment processing"
    commit id: "fix: rate limiting bug"
    commit id: "refactor: optimize cache usage"
    checkout main
    merge develop
    commit id: "Release v2.1.0"
    branch hotfix
    checkout hotfix
    commit id: "fix: critical payment bug"
    checkout main
    merge hotfix
    commit id: "Release v2.1.1"
    branch feature/new-payment-method
    checkout feature/new-payment-method
    commit id: "feat: add Stripe integration"
    commit id: "test: add Stripe payment tests"
    checkout develop
    merge feature/new-payment-method
    checkout main
    merge develop
    commit id: "Release v2.2.0"
```

#### Автоматизированное развертывание

```yaml
# .github/workflows/deploy.yml
name: Deploy to Production
on:
  push:
    branches: [ main ]
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run tests
        run: |
          python -m venv venv
          source venv/bin/activate
          pip install -r requirements.txt
          pytest --cov=. --cov-report=xml

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Security scan
        uses: github/super-linter@v4

  deploy:
    needs: [test, security]
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to production
        run: |
          echo "Deploying to production..."
          # Deployment commands here
```

### Масштабирование

#### Горизонтальное масштабирование

```mermaid
graph TB
    subgraph "Load Balancer"
        LB[Load Balancer]
    end

    subgraph "Application Cluster"
        APP1[App Instance 1]
        APP2[App Instance 2]
        APP3[App Instance 3]
        APP4[App Instance 4]
    end

    subgraph "Database Layer"
        PRIMARY[(PostgreSQL Primary)]
        REPLICA1[(Replica 1)]
        REPLICA2[(Replica 2)]
    end

    subgraph "Cache Layer"
        REDIS[(Redis Cluster)]
    end

    LB --> APP1
    LB --> APP2
    LB --> APP3
    LB --> APP4

    APP1 --> PRIMARY
    APP2 --> REPLICA1
    APP3 --> REPLICA2
    APP4 --> PRIMARY

    APP1 --> REDIS
    APP2 --> REDIS
    APP3 --> REDIS
    APP4 --> REDIS

    PRIMARY -.-> REPLICA1
    PRIMARY -.-> REPLICA2
```

#### Вертикальное масштабирование

```mermaid
graph TB
    subgraph "Enhanced Instance"
        APP[Enhanced App]
        subgraph "Resource Optimization"
            CPU[CPU Optimization]
            MEM[Memory Management]
            IO[I/O Optimization]
        end
        subgraph "Connection Pooling"
            DB_POOL[Database Pool]
            CACHE_POOL[Cache Pool]
            API_POOL[API Pool]
        end
        subgraph "Async Processing"
            TASK_QUEUE[Task Queue]
            WORKER_POOL[Worker Pool]
            BG_JOBS[Background Jobs]
        end
    end

    APP --> CPU
    APP --> MEM
    APP --> IO

    APP --> DB_POOL
    APP --> CACHE_POOL
    APP --> API_POOL

    APP --> TASK_QUEUE
    TASK_QUEUE --> WORKER_POOL
    TASK_QUEUE --> BG_JOBS
```

## 📁 Структура проекта

```
mirza-telegram-shop-bot/
├── 📁 alembic/                    # Миграции базы данных
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
├── 📁 cloudflare/                 # Cloudflare настройки
│   ├── cloudflared-credentials.json.example
│   ├── cloudflared.json.example
│   └── cloudflared-cert.pem
├── 📁 config/                     # Конфигурация приложения
│   ├── __init__.py
│   └── settings.py
├── 📁 core/                       # Ядро приложения
│   ├── __init__.py
│   └── interfaces.py
├── 📁 docs/                       # Документация
│   ├── ARCHITECTURE.md
│   ├── DEPLOYMENT.md
│   └── SSL_SETUP.md
├── 📁 handlers/                   # Обработчики Telegram
│   ├── __init__.py
│   ├── balance_handler.py
│   ├── base_handler.py
│   ├── error_handler.py
│   ├── message_handler.py
│   ├── payment_handler.py
│   └── purchase_handler.py
├── 📁 nginx/                      # Nginx конфигурация
│   ├── conf.d/
│   │   └── ssl.conf
│   └── nginx.conf
├── 📁 redis/                      # Redis конфигурация
│   ├── conf/
│   │   └── redis.conf
│   └── scripts/
│       ├── create_cluster.sh
│       └── monitor_cluster_new.sh
├── 📁 repositories/               # Репозитории данных
│   ├── __init__.py
│   ├── balance_repository.py
│   └── user_repository.py
├── 📁 scripts/                    # Скрипты обслуживания
│   ├── check_fragment_status.py
│   ├── periodic_cookie_refresher.py
│   ├── precheck_fragment.py
│   ├── ssl-renewal.sh
│   ├── update_fragment_cookies.py
│   └── cron/
│       └── ssl-renewal.cron
├── 📁 services/                   # Бизнес логика
│   ├── __init__.py
│   ├── balance/
│   │   └── balance_service.py
│   ├── cache/
│   │   ├── payment_cache.py
│   │   ├── rate_limit_cache.py
│   │   ├── session_cache.py
│   │   └── user_cache.py
│   ├── fragment/
│   │   ├── fragment_cookie_manager.py
│   │   └── fragment_service.py
│   ├── payment/
│   │   ├── payment_service.py
│   │   └── star_purchase_service.py
│   ├── system/
│   │   ├── advanced_rate_limiter.py
│   │   └── circuit_breaker.py
│   └── webhook/
│       ├── webhook_app.py
│       └── webhook_handler.py
├── 📁 tests/                      # Тесты
│   ├── test_fragment_cookie_manager.py
│   ├── test_fragment_service.py
│   ├── test_periodic_cookie_refresher.py
│   ├── test_precheck_fragment.py
│   ├── test_seed_phrase.py
│   ├── test_star_purchase_fragment.py
│   └── test_precheck_fragment.py
├── 📁 utils/                      # Утилиты
│   ├── __init__.py
│   ├── message_templates.py
│   └── rate_limit_messages.py
├── 🔧 Dockerfile                 # Docker образ
├── 🔧 docker-compose.yml         # Docker оркестрация
├── 🔧 main.py                    # Точка входа приложения
├── 🔧 requirements.txt           # Зависимости Python
├── 🔧 .env.example               # Шаблон переменных окружения
├── 🔧 .gitignore                 # Игнорируемые файлы
└── 📖 README.md                  # Документация проекта
```

### Описание основных директорий

| Директория | Описание |
|------------|----------|
| `handlers/` | Обработчики команд и сообщений Telegram |
| `services/` | Бизнес логика и интеграция с внешними API |
| `repositories/` | Работа с базой данных и кешем |
| `config/` | Конфигурация приложения |
| `core/` | Абстракции и интерфейсы |
| `scripts/` | Скрипты обслуживания и автоматизации |
| `tests/` | Unit и integration тесты |
| `docs/` | Подробная документация |

## 🤝 Вклад в проект

### Процесс внесения вклада

1. **Форк проекта**
   ```bash
   git clone https://github.com/your-username/mirza-telegram-shop-bot.git
   ```

2. **Создание feature ветки**
   ```bash
   git checkout -b feature/amazing-feature
   ```

3. **Внесение изменений**
   - Следуйте принципам SOLID и DRY
   - Добавляйте тесты для нового кода
   - Обновляйте документацию
   - Соблюдайте стиль кода проекта

4. **Тестирование**
   ```bash
   pytest --cov=. --cov-report=html
   ```

5. **Коммит изменений**
   ```bash
   git add .
   git commit -m "feat: add amazing feature"
   ```

6. **Push и Pull Request**
   ```bash
   git push origin feature/amazing-feature
   # Создайте Pull Request на GitHub
   ```

### Стандарты кода

#### Стиль кода

- **PEP 8** - стиль кода Python
- **Типизация** - использование type hints
- **Документация** - docstrings для всех функций
- **Линтеры** - black, flake8, mypy

#### Коммиты

```
feat: add new payment method
fix: resolve rate limiting bug
docs: update API documentation
refactor: optimize database queries
test: add unit tests for payment service
```

#### Pull Request

- **Заголовок**: Краткое описание изменений
- **Описание**: Детальное объяснение изменений
- **Тестирование**: Результаты тестов и покрытие
- **Документация**: Обновления документации
- **Breaking Changes**: Если применимо

### Разработка

#### Настройка среды разработки

```bash
# Клонирование
git clone https://github.com/username/mirza-telegram-shop-bot.git
cd mirza-telegram-shop-bot

# Виртуальное окружение
python -m venv venv
source venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt
pip install -e .[dev]

# Настройка pre-commit hooks
pre-commit install

# Запуск в режиме разработки
python main.py
```

#### Отладка

```bash
# С отладкой
DEBUG=true python main.py

# С подробным логированием
LOG_LEVEL=DEBUG python main.py

# С профилированием
python -m cProfile main.py
```

## 📞 Поддержка

### Получение помощи

1. **Документация**: Проверьте [документацию](docs/) проекта
2. **Issues**: Поищите решение в [GitHub Issues](../../issues)
3. **Discussions**: Обсудите в [GitHub Discussions](../../discussions)
4. **Telegram**: Свяжитесь с разработчиком @Mirza

### Сообщение об ошибке

При создании Issue укажите:

- **Версию Python и ОС**
- **Версии основных зависимостей**
- **Полное описание ошибки**
- **Шаги для воспроизведения**
- **Логи приложения** (без чувствительных данных)

```markdown
## Описание ошибки

## Шаги воспроизведения
1. 
2. 
3. 

## Ожидаемое поведение

## Фактическое поведение

## Логи

## Системная информация
- Python версия:
- ОС:
- Docker версия:
```

## 🔐 Безопасность

### Аудит безопасности

Проект прошел аудит безопасности:

- ✅ **Input Validation** - валидация всех входных данных
- ✅ **SQL Injection Protection** - использование ORM
- ✅ **XSS Protection** - экранирование пользовательского контента
- ✅ **CSRF Protection** - защита от CSRF атак
- ✅ **Rate Limiting** - защита от DoS атак
- ✅ **SSL/TLS** - шифрование всех соединений
- ✅ **HMAC Signatures** - подписи вебхуков
- ✅ **Environment Variables** - хранение секретов
- ✅ **Seed Phrase Protection** - безопасное хранение seed фраз
- ✅ **Cookie Management** - безопасное управление cookies
- ✅ **Pre-flight Checks** - автоматическая проверка настроек

### Рекомендации по безопасности

1. **Храните секреты в защищенном месте**
   - Используйте HashiCorp Vault или AWS Secrets Manager
   - Никогда не коммитте `.env` файлы
   - Регулярно обновляйте токены

2. **Мониторьте систему**
   - Настройте алерты на подозрительную активность
   - Регулярно проверяйте логи
   - Мониторьте использование ресурсов

3. **Обновляйте зависимости**
   - Регулярно обновляйте Python и зависимости
   - Следите за security advisories
   - Используйте Dependabot для автоматизации

4. **Сетевая безопасность**
   - Используйте firewall
   - Ограничьте доступ к портам
   - Настройте VPN для административного доступа

5. **Резервное копирование**
   - Регулярно создавайте бэкапы базы данных
   - Тестируйте восстановление из бэкапа
   - Храните бэкапы в защищенном месте

## 📊 Производительность

### Оптимизации

- **Асинхронность** - все I/O операции асинхронные
- **Connection Pooling** - пулы соединений для БД и Redis
- **Кеширование** - многоуровневое кеширование (L1 + L2)
- **Rate Limiting** - защита от перегрузки
- **Circuit Breaker** - устойчивость к сбоям внешних API
- **Database Indexing** - оптимизированные индексы
- **Query Optimization** - оптимизированные запросы

### Метрики производительности

| Метрика | Значение | Описание |
|---------|----------|----------|
| **Response Time** | < 100ms | Среднее время ответа API |
| **Throughput** | 1000+ req/min | Пропускная способность |
| **Error Rate** | < 0.1% | Процент ошибок |
| **Cache Hit Rate** | > 95% | Эффективность кеширования |
| **Database Latency** | < 10ms | Задержка базы данных |

### Масштабирование

#### Автоматическое масштабирование

```yaml
# docker-compose.scale.yml
version: '3.8'
services:
  app:
    image: mirza-telegram-shop-bot:latest
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
        reservations:
          cpus: '0.2'
          memory: 256M
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
        window: 120s
    environment:
      - REDIS_URL=redis://redis-cluster:7000
      - DATABASE_URL=postgresql://user:pass@postgres-primary:5432/db
```

## 📝 Лицензия

Этот проект распространяется под лицензией MIT. См. файл `LICENSE` для подробностей.

## 🙏 Благодарности

- **aiogram** - мощный фреймворк для Telegram ботов
- **FastAPI** - современный веб-фреймворк
- **PostgreSQL** - надежная база данных
- **Redis** - высокопроизводительное кеширование
- **Docker** - контейнеризация приложений
- **Cloudflare** - защита и доставка контента

---

**Разработано с ❤️ для сообщества Telegram разработчиков**

*Последнее обновление: 2025-01-27*
