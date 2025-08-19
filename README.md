# 🤖 Telegram Bot с Системой Платежей и Балансом

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![aiogram](https://img.shields.io/badge/aiogram-3.21+-green.svg)](https://aiogram.dev)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-blue.svg)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7+-red.svg)](https://redis.io)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://docker.com)

Современный Telegram бот с интегрированной системой платежей Heleket, балансом пользователей, покупкой звезд и продвинутым rate limiting. Архитектура построена на принципах SOLID, DRY, KISS с использованием асинхронного программирования.

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

## 📚 Дополнительная документация

- [🏗️ Детальная архитектура](docs/ARCHITECTURE.md) - Подробные диаграммы компонентов и паттернов
- [🚀 Развертывание и DevOps](docs/DEPLOYMENT.md) - CI/CD, Docker, инфраструктура
- [💎 Fragment API](docs/fragment.md) - Интеграция с Telegram Fragment для покупки звезд


## 🏗️ Архитектура

### Общая архитектура системы

```mermaid
graph TB
    subgraph "External Services"
        TG[Telegram API]
        HELEKET[Heleket Payment API]
        FRAGMENT[Telegram Fragment API]
    end

    subgraph "Load Balancer"
        NGINX[Nginx]
    end

    subgraph "Application Layer"
        BOT[Telegram Bot]
        WEBHOOK[Webhook Service]
        API[REST API]
    end

    subgraph "Business Logic"
        MH[Message Handler]
        PS[Payment Service]
        BS[Balance Service]
        SPS[Star Purchase Service]
        FS[Fragment Service]
        RL[Rate Limiter]
    end

    subgraph "Data Layer"
        UR[User Repository]
        BR[Balance Repository]
        CACHE[Cache Services]
    end

    subgraph "Infrastructure"
        PG[(PostgreSQL)]
        REDIS[(Redis Cluster)]
    end

    TG --> NGINX
    HELEKET --> NGINX
    FRAGMENT --> NGINX
    NGINX --> BOT
    NGINX --> WEBHOOK
    NGINX --> API

    BOT --> MH
    WEBHOOK --> PS
    MH --> PS
    MH --> BS
    MH --> SPS
    MH --> FS
    MH --> RL

    PS --> UR
    BS --> BR
    SPS --> UR
    SPS --> BR
    FS --> FRAGMENT
    RL --> CACHE

    UR --> PG
    BR --> PG
    CACHE --> REDIS

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
        CS["🗄️ Cache Service"]
        RL["🚦 Rate Limiter"]
        HS["❤️ Health Service"]
        WS["🔌 WebSocket Service"]
    end

    subgraph repos ["📊 Repository Layer"]
        UR["👤 User Repository"]
        BR["💰 Balance Repository"]
    end

    subgraph core ["🏗️ Core Layer"]
        INT["🔗 Interfaces"]
        CFG["⚙️ Configuration"]
    end

    MH --> PS
    MH --> BS
    MH --> SPS
    MH --> FS
    PH --> PS
    PuH --> SPS
    BalH --> BS

    PS --> UR
    BS --> BR
    SPS --> UR
    SPS --> BR
    FS --> SPS

    PS --> CS
    BS --> CS
    SPS --> CS

```

**Слоистая архитектура:**

```mermaid
graph TD
    subgraph "🎯 HANDLERS LAYER"
        MH["📨 Message Handler"]
        PH["💳 Payment Handler"]
        PuH["🛒 Purchase Handler"]
        BH["💰 Balance Handler"]
    end
    
    subgraph "⚙️ SERVICES LAYER"
        PS["💳 Payment Service"]
        BS["💰 Balance Service"]
        SPS["⭐ Star Purchase Service"]
        FS["💎 Fragment Service"]
        RL["🚦 Rate Limiter"]
    end
    
    subgraph "📊 REPOSITORY LAYER"
        UR["👤 User Repository"]
        BR["💰 Balance Repository"]
    end
    
    subgraph "🏗️ CORE LAYER"
        INT["🔗 Interface ABC"]
        CFG["⚙️ Config Settings"]
    end
    
    %% Connections between layers
    MH --> PS
    MH --> FS
    PH --> PS
    PuH --> SPS
    BH --> BS
    
    PS --> UR
    BS --> BR
    SPS --> UR
    SPS --> BR
    FS --> SPS
    
    PS --> INT
    BS --> INT
    SPS --> INT
    FS --> INT
    RL --> INT
    
    UR --> CFG
    BR --> CFG
```

## 📊 Структура базы данных

### ER-диаграмма

```mermaid
erDiagram
    USERS {
        int user_id PK "Telegram User ID"
        string username "Telegram username"
        string first_name "Имя пользователя"
        string last_name "Фамилия пользователя"
        datetime created_at "Дата создания"
        datetime updated_at "Дата обновления"
    }

    BALANCES {
        int id PK "Уникальный ID"
        int user_id FK "ID пользователя"
        decimal amount "Сумма баланса"
        string currency "Валюта (TON)"
        datetime created_at "Дата создания"
        datetime updated_at "Дата обновления"
    }

    TRANSACTIONS {
        int id PK "Уникальный ID"
        int user_id FK "ID пользователя"
        enum transaction_type "Тип транзакции"
        enum status "Статус транзакции"
        decimal amount "Сумма транзакции"
        string currency "Валюта"
        string description "Описание"
        string external_id UK "Внешний ID"
        text transaction_metadata "Метаданные JSON"
        datetime created_at "Дата создания"
        datetime updated_at "Дата обновления"
    }

    USERS ||--|| BALANCES : "имеет"
    USERS ||--o{ TRANSACTIONS : "совершает"
```

**Детализированная схема базы данных:**

```mermaid
graph LR
    subgraph USERS ["👤 USERS TABLE"]
        U_FIELDS["🔑 user_id (PK) - INTEGER<br/>📝 username - VARCHAR<br/>👤 first_name - VARCHAR<br/>👤 last_name - VARCHAR<br/>📅 created_at - DATETIME<br/>📅 updated_at - DATETIME"]
    end
    
    subgraph BALANCES ["💰 BALANCES TABLE"]
        B_FIELDS["🔑 id (PK) - INTEGER<br/>🔗 user_id (FK) - INTEGER<br/>💵 amount - DECIMAL<br/>💱 currency - VARCHAR<br/>📅 created_at - DATETIME<br/>📅 updated_at - DATETIME"]
    end
    
    subgraph TRANSACTIONS ["📊 TRANSACTIONS TABLE"]
        T_FIELDS["🔑 id (PK) - INTEGER<br/>🔗 user_id (FK) - INTEGER<br/>📋 transaction_type - ENUM<br/>📊 status - ENUM<br/>💵 amount - DECIMAL<br/>💱 currency - VARCHAR<br/>📝 description - VARCHAR<br/>🔒 external_id (UK) - VARCHAR<br/>📄 transaction_metadata - TEXT<br/>📅 created_at - DATETIME<br/>📅 updated_at - DATETIME"]
    end
    
    USERS -.->|"1:1 has balance"| BALANCES
    USERS -.->|"1:N makes transactions"| TRANSACTIONS
```

### Описание таблиц

| Таблица | Описание | Ключевые поля |
|---------|----------|---------------|
| **users** | Пользователи Telegram | `user_id` (PK), `username`, `first_name`, `last_name` |
| **balances** | Балансы пользователей | `user_id` (FK), `amount`, `currency` |
| **transactions** | История транзакций | `user_id` (FK), `transaction_type`, `status`, `amount`, `external_id` |

### Типы транзакций

| Тип | Описание |
|-----|----------|
| `purchase` | Покупка звезд |
| `refund` | Возврат средств |
| `bonus` | Бонусные начисления |
| `adjustment` | Корректировки |
| `recharge` | Пополнение баланса |

## 🛠️ Технологический стек

### Backend

| Технология | Версия | Назначение |
|------------|--------|------------|
| **Python** | 3.11+ | Основной язык |
| **aiogram** | 3.21+ | Telegram Bot Framework |
| **FastAPI** | 0.115+ | REST API и вебхуки |
| **SQLAlchemy** | 2.0+ | ORM для работы с БД |
| **Alembic** | 1.13+ | Миграции БД |
| **asyncpg** | 0.29+ | Асинхронный PostgreSQL драйвер |
| **fragment-api-lib** | 1.0+ | Библиотека для работы с Telegram Fragment API |

### Инфраструктура

| Технология | Версия | Назначение |
|------------|--------|------------|
| **PostgreSQL** | 15+ | Основная база данных |
| **Redis** | 7+ | Кеширование и сессии |
| **Nginx** | latest | Reverse proxy и load balancer |
| **Docker** | latest | Контейнеризация |
| **Docker Compose** | latest | Оркестрация сервисов |

### Мониторинг и безопасность

| Технология | Назначение |
|------------|------------|
| **Prometheus** | Метрики и мониторинг |
| **Grafana** | Визуализация метрик |
| **SSL/TLS** | Шифрование соединений |
| **HMAC** | Подписи вебхуков |

## ⚙️ Установка и настройка

### Предварительные требования

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Docker и Docker Compose (опционально)

### Локальная установка

1. **Клонирование репозитория**

```bash
git clone <repository-url>
cd telegram-bot-payment-system
```

2. **Создание виртуального окружения**

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows
```

3. **Установка зависимостей**

```bash
pip install -r requirements.txt
```

4. **Настройка переменных окружения**

```bash
cp .env.example .env
# Отредактируйте .env файл с вашими настройками
```

5. **Инициализация базы данных**

```bash
alembic upgrade head
```

6. **Запуск приложения**

```bash
python main.py
```

## 🐳 Docker развертывание

### Быстрый старт

```bash
# Клонирование и запуск
git clone <repository-url>
cd telegram-bot-payment-system
cp .env.example .env
# Отредактируйте .env файл
docker-compose up -d
```

### Архитектура Docker

```mermaid
graph TB
    subgraph "Docker Network: bot-network"
        subgraph "Application Services"
            APP[app - Telegram Bot]
            WEBHOOK[webhook - Webhook Service]
        end

        subgraph "Infrastructure Services"
            PG[db - PostgreSQL]
            NGINX[nginx - Load Balancer]
        end

        subgraph "Redis Cluster"
            R1[redis-node-1:7379]
            R2[redis-node-2:7380]
            R3[redis-node-3:7381]
            RR1[redis-replica-1]
            RR2[redis-replica-2]
            RR3[redis-replica-3]
        end

        subgraph "Utilities"
            RC[redis-cluster-creator]
            RM[redis-cluster-monitor]
        end
    end

    APP --> PG
    APP --> R1
    WEBHOOK --> PG
    WEBHOOK --> R1
    NGINX --> APP
    NGINX --> WEBHOOK

    R1 -.-> RR1
    R2 -.-> RR2
    R3 -.-> RR3

```

### Docker сервисы

| Сервис | Порт | Описание |
|--------|------|----------|
| **app** | - | Основной Telegram бот |
| **webhook** | 8001 | Сервис обработки вебхуков |
| **db** | 5432 | PostgreSQL база данных |
| **nginx** | 80, 443 | Reverse proxy |
| **redis-node-1** | 7379 | Redis кластер - узел 1 |
| **redis-node-2** | 7380 | Redis кластер - узел 2 |
| **redis-node-3** | 7381 | Redis кластер - узел 3 |

### Автоматическое обновление Fragment cookies

При включенной настройке `FRAGMENT_AUTO_COOKIE_REFRESH=true`:

- Контейнер автоматически устанавливает Chrome и ChromeDriver
- При каждом запуске происходит обновление Fragment cookies
- Во время работы приложения cookies автоматически обновляются при истечении срока действия
- Фоновая задача периодически обновляет cookies с интервалом `FRAGMENT_COOKIE_REFRESH_INTERVAL`
- Cookies сохраняются в файл и используются для всех операций Fragment API

### Ручное обновление cookies

Для ручного обновления cookies:

```bash
# В контейнере
python scripts/update_fragment_cookies.py

# Или через docker-compose
docker-compose exec app python scripts/update_fragment_cookies.py
```

### Проверка состояния Fragment API

Для проверки состояния Fragment API:

```bash
# В контейнере
python scripts/check_fragment_status.py

# Или через docker-compose
docker-compose exec app python scripts/check_fragment_status.py
```

## 📡 API и Вебхуки

### Webhook эндпоинты

| Эндпоинт | Метод | Описание |
|----------|-------|----------|
| `/webhook/heleket` | POST | Обработка платежей от Heleket |
| `/health` | GET | Проверка состояния сервиса |
| `/metrics` | GET | Метрики Prometheus |

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
    "stars_count": 100
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
    participant C as 📦 Cache

    U->>TB: /buy_stars 100
    TB->>PS: create_payment_request(user_id, 100)
    PS->>DB: create_transaction(pending)
    PS->>H: POST /create_payment
    H-->>PS: payment_url + uuid
    PS->>C: cache_payment(uuid, user_id)
    PS-->>TB: payment_url
    TB-->>U: 💳 Ссылка для оплаты
    
    Note over U,H: Пользователь переходит по ссылке и оплачивает
    
    H->>WH: POST /webhook/heleket (payment completed)
    WH->>C: get_payment_info(uuid)
    WH->>DB: update_transaction(completed)
    WH->>DB: update_user_balance(+100 stars)
    WH->>TB: notify_payment_success(user_id)
    TB->>U: ✅ Платеж успешен! +100 ⭐
```

### Диаграмма состояний транзакций

```mermaid
stateDiagram-v2
    [*] --> pending : Создание платежа
    
    pending --> processing : Пользователь начал оплату
    pending --> cancelled : Отмена пользователем
    pending --> expired : Истек срок действия
    
    processing --> completed : Успешная оплата
    processing --> failed : Ошибка платежа
    processing --> cancelled : Отмена во время оплаты
    
    completed --> refunded : Возврат средств
    failed --> pending : Повторная попытка
    
    cancelled --> [*]
    expired --> [*]
    completed --> [*]
    refunded --> [*]
    
    note right of completed : Баланс пользователя\nобновляется
    note right of refunded : Баланс пользователя\nуменьшается
```

### Rate Limiting

```mermaid
graph LR
    subgraph "Rate Limiting Layers"
        UL[User Limits]
        GL[Global Limits]
        BL[Burst Limits]
        PL[Premium Limits]
    end

    subgraph "Limit Types"
        MSG[Messages: 30/min]
        OPS[Operations: 20/min]
        PAY[Payments: 5/min]
    end

    subgraph "Special Cases"
        NEW[New Users: 15/min]
        PREM[Premium: x2 limits]
        BURST[Burst: 10/10sec]
    end

    UL --> MSG
    UL --> OPS
    UL --> PAY
    
    GL --> MSG
    GL --> OPS
    GL --> PAY

```

## 🔧 Конфигурация

### Основные настройки

| Категория | Переменная | Значение по умолчанию | Описание |
|-----------|------------|----------------------|----------|
| **Telegram** | `TELEGRAM_TOKEN` | - | Токен Telegram бота |
| **Heleket** | `MERCHANT_UUID` | - | UUID мерчанта |
| **Heleket** | `API_KEY` | - | API ключ |
| **Fragment** | `FRAGMENT_SEED_PHRASE` | - | 24-словная seed фраза TON кошелька (⚠️ СЕКРЕТ!) |
| **Fragment** | `FRAGMENT_COOKIES` | - | Cookies для авторизации в Fragment |
| **Fragment** | `FRAGMENT_AUTO_COOKIE_REFRESH` | `false` | Автоматическое обновление cookies |
| **Fragment** | `FRAGMENT_COOKIE_REFRESH_INTERVAL` | `3600` | Интервал обновления cookies (сек) |
| **Database** | `DATABASE_URL` | `postgresql+asyncpg://...` | URL базы данных |
| **Redis** | `REDIS_URL` | `redis://localhost:7379` | URL Redis |

### Rate Limiting настройки

| Параметр | Значение | Описание |
|----------|----------|----------|
| `RATE_LIMIT_USER_MESSAGES` | 30 | Сообщений в минуту на пользователя |
| `RATE_LIMIT_USER_OPERATIONS` | 20 | Операций в минуту на пользователя |
| `RATE_LIMIT_USER_PAYMENTS` | 5 | Платежей в минуту на пользователя |
| `RATE_LIMIT_GLOBAL_MESSAGES` | 1000 | Глобальный лимит сообщений |
| `RATE_LIMIT_PREMIUM_MULTIPLIER` | 2.0 | Множитель для премиум пользователей |

### Cache настройки

| Параметр | TTL (сек) | Описание |
|----------|-----------|----------|
| `CACHE_TTL_USER` | 1800 | Кеш пользователей |
| `CACHE_TTL_SESSION` | 1800 | Кеш сессий |
| `CACHE_TTL_PAYMENT` | 900 | Кеш платежей |
| `CACHE_TTL_RATE_LIMIT` | 60 | Кеш rate limiting |

## 📈 Мониторинг

### Метрики Prometheus

- **Счетчики**: количество сообщений, платежей, ошибок
- **Гистограммы**: время ответа API, время обработки платежей
- **Gauge**: активные пользователи, размер кеша
- **Rate Limiting**: количество заблокированных запросов

### Health Checks

```bash
# Проверка состояния приложения
curl http://localhost:8001/health

# Проверка метрик
curl http://localhost:8001/metrics
```

### Логирование

- **Уровни**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Формат**: JSON для production, текст для development
- **Ротация**: по размеру и времени
- **Централизация**: через Docker logging driver

## 🧪 Тестирование

### Запуск тестов

```bash
# Все тесты
pytest

# С покрытием
pytest --cov=.

# Только unit тесты
pytest tests/unit/

# Только integration тесты
pytest tests/integration/

# Тесты Fragment API
pytest tests/test_fragment_service.py
pytest tests/test_star_purchase_fragment.py
```

### Структура тестов

```mermaid
graph TD
    subgraph "🧪 Test Structure"
        TESTS["📁 tests/"]
        
        subgraph "🔬 Unit Tests"
            UNIT[("📁 unit/")]
            UNIT_SERVICES["📁 test_services/"]
            UNIT_REPOS[("📁 test_repositories/")]
            UNIT_HANDLERS[("📁 test_handlers/")]
        end
        
        subgraph "🔗 Integration Tests"
            INTEGRATION[("📁 integration/")]
            INT_PAYMENT[("📁 test_payment_flow/")]
            INT_WEBHOOK[("📁 test_webhook_processing/")]
            INT_FRAGMENT[("📁 test_fragment_integration/")]
        end
        
        subgraph "🛠️ Test Fixtures"
            FIXTURES[("📁 fixtures/")]
            FIX_DB["📄 database.py"]
            FIX_REDIS["📄 redis.py"]
        end
    end
    
    TESTS --> UNIT
    TESTS --> INTEGRATION
    TESTS --> FIXTURES
    
    UNIT --> UNIT_SERVICES
    UNIT --> UNIT_REPOS
    UNIT --> UNIT_HANDLERS
    
    INTEGRATION --> INT_PAYMENT
    INTEGRATION --> INT_WEBHOOK
    INTEGRATION --> INT_FRAGMENT
    
    FIXTURES --> FIX_DB
    FIXTURES --> FIX_REDIS
```

## 🚀 Производительность

### Оптимизации

- **Асинхронность**: все операции I/O асинхронные
- **Connection Pooling**: пулы соединений для БД и Redis
- **Кеширование**: многоуровневое кеширование
- **Rate Limiting**: защита от перегрузки
- **Circuit Breaker**: устойчивость к сбоям

### Масштабирование

- **Горизонтальное**: несколько экземпляров бота
- **Redis Cluster**: распределенное кеширование
- **Database Sharding**: разделение данных
- **Load Balancing**: распределение нагрузки

### 🔐 Безопасность

- ✅ **MD5 подписи** для вебхуков
- ✅ **SSL/TLS** шифрование
- ✅ **Rate Limiting** защита от DDoS
- ✅ **Input Validation** валидация входных данных
- ✅ **SQL Injection** защита через ORM
- ✅ **Environment Variables** для секретов
- ✅ **Seed Phrase Protection** хранение seed фразы в защищенном виде
- ✅ **Cookie Management** безопасное хранение cookies Fragment
- ✅ **Pre-flight Checks** автоматическая проверка настроек при запуске

### Рекомендации

1. Используйте сильные пароли для БД и Redis
2. Регулярно обновляйте зависимости
3. Мониторьте логи на подозрительную активность
4. Используйте HTTPS для всех внешних соединений
5. Настройте firewall для ограничения доступа
6. Храните seed фразу TON кошелька в защищенном месте
7. Регулярно обновляйте cookies Fragment API
8. Используйте предварительную проверку настроек перед запуском: `python scripts/precheck_fragment.py`

## 📝 Лицензия

Этот проект распространяется под лицензией MIT. См. файл `LICENSE` для подробностей.

## 🤝 Вклад в проект

1. Fork проекта
2. Создайте feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit изменения (`git commit -m 'Add some AmazingFeature'`)
4. Push в branch (`git push origin feature/AmazingFeature`)
5. Откройте Pull Request

## 📞 Поддержка

Если у вас есть вопросы или проблемы:

1. Проверьте [Issues](../../issues) на GitHub
2. Создайте новый Issue с подробным описанием
3. Приложите логи и конфигурацию (без секретов!)

---

**Создано с ❤️ для Telegram Bot разработчиков**
