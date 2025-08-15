# Telegram Bot с Покупкой Звезд v2.0

Современный Telegram-бот для покупки звезд через интеграцию с платежной системой Heleket. Проект построен на микросервисной архитектуре с использованием Docker Compose, Redis кластера и высокодоступной инфраструктуры.

## 🎉 Версия 2.0 - Новые возможности

### ✨ Основные улучшения

- **Оптимизированный обработчик сообщений** - полная переработка handlers/message_handler.py с применением SOLID принципов
- **Система сессий** - улучшенное управление состоянием пользователей с Redis кешированием
- **Rate limiting** - многоуровневая защита от злоупотреблений
- **Circuit breaker** - защита от каскадных отказов с автоматическим восстановлением
- **Улучшенный UI/UX** - современный интерфейс с эмодзи и HTML форматированием
- **Расширенная навигация** - интуитивно понятная иерархическая структура меню
- **Улучшенные сообщения об ошибках** - понятные и информативные уведомления с рекомендациями
- **Оптимизированный баланс отображения** - детальная информация о балансе и транзакциях
- **Новые callback обработчики** - расширенная функциональность кнопок
- **История транзакций** - просмотр всех операций за последние 30 дней

## 🆕 Новые функции v2.0

### 💫 Основные улучшения интерфейса

- **Улучшенное главное меню** - современный дизайн с эмодзи и четкой структурой навигации
- **Расширенный экран баланса** - детальная информация о балансе и доступных действиях
- **Улучшенный магазин звезд** - описание пакетов с бонусами и информацией об экономии
- **История транзакций** - просмотр всех операций за последние 30 дней с детализацией
- **Улучшенные сообщения об ошибках** - понятные и информативные уведомления с рекомендациями
- **Улучшенные успешные операции** - праздничное оформление для успешных покупок

### 🎯 Система сессий и состояния

- **Автоматическое управление сессиями** - создание и восстановление пользовательских сессий
- **Кеширование состояния в Redis** - быстрый доступ к данным пользователей
- **Множественные активные сессии** - поддержка нескольких действий на одного пользователя
- **Восстановление прерванных действий** - автоматический возврат в предыдущее состояние

### 🔄 Callback обработчики

- **Расширенная система кнопок** - интуитивно понятная навигация через инлайн-клавиатуры
- **Иерархическое меню** - логичная структура с автоматическим возвратом в предыдущие меню
- **Визуальные подсказки** - эмодзи для быстрого распознавания функций
- **Оптимизированная компоновка** - правильное расположение элементов интерфейса

### 🛡️ Системы защиты

- **Rate limiting** - многоуровневая защита от злоупотреблений с индивидуальными лимитами
- **Circuit breaker** - автоматическая защита от каскадных отказов с восстановлением
- **Graceful degradation** - корректная работа при недоступности сервисов
- **Retry logic** - повторные попытки при временных ошибках

### ⚡ Оптимизация производительности

- **Многоуровневое кеширование** - User Cache, Payment Cache, Session Cache, Rate Limit Cache
- **Асинхронная обработка** - все операции используют async/await для максимальной производительности
- **Connection pooling** - пул соединений с PostgreSQL для эффективной работы с базой данных
- **Batch operations** - групповые операции для оптимизации запросов к базе данных

## ✨ Особенности

- **Микросервисная архитектура** - масштабируемые и независимые сервисы
- **Redis кластер** - 3 ноды (master + 2 slaves) для высокой доступности
- **Nginx reverse proxy** - SSL/TLS терминация и балансировка нагрузки
- **Circuit breaker** - защита от каскадных отказов
- **Rate limiting** - ограничение частоты запросов
- **Health checks** - мониторинг состояния сервисов
- **Альтернативные порты** - 8080/8443/8001/8081 для решения конфликтов

- **PostgreSQL (Neon) + Redis** - надежное хранение и кеширование
- **Docker контейнеризация** - легкое развертывание и масштабирование
- **Улучшенный UI/UX** - современный интерфейс с эмодзи и HTML форматированием
- **Визуально привлекательный дизайн** - интуитивно понятная навигация
- **Расширенная информация о пакетах** - детальное описание бонусов и выгод
- **Улучшенные сообщения об ошибках** - понятные и информативные уведомления
- **Оптимизированный баланс отображения** - детальная информация о балансе и транзакциях

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
        NGINX_SSL --> APP[Telegram Bot App:8001]
        NGINX_HTTP --> APP
        APP --> CB[Circuit Breaker]
        CB --> RL[Rate Limiter]
    end

    subgraph "Cache Layer"
        RL --> RC[Redis Cluster]
        RC --> RM[Redis Master:7379]
        RC --> RS1[Redis Slave 1:7380]
        RC --> RS2[Redis Slave 2:7381]
        RC --> RR1[Redis Replica 1:7382]
        RC --> RR2[Redis Replica 2:7383]
        RC --> RR3[Redis Replica 3:7384]

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
        P3[8001: Webhook Port] --> WEBHOOK
        P4[8081: App Port] --> APP
        P5[7379: Redis Master] --> REDIS_M
        P6[7380: Redis Node 2] --> REDIS_N2
        P7[7381: Redis Node 3] --> REDIS_N3
        P8[7382: Redis Replica 1] --> REDIS_R1
        P9[7383: Redis Replica 2] --> REDIS_R2
        P10[7384: Redis Replica 3] --> REDIS_R3
    end
```

## 🚀 Быстрый старт v2.0

### Требования

- **Python 3.11+** - основная среда выполнения
- **Docker & Docker Compose** - контейнеризация
- **Redis Cluster** - кеширование и очереди
- **PostgreSQL (Neon)** - база данных
- **Nginx** - reverse proxy

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

# Настройка прав доступа
chmod 600 .env
chmod 600 ssl/*.pem
```

### 3. Конфигурация переменных окружения

Отредактируйте файл `.env` с учетом новых возможностей:

```env
# === Telegram Bot Configuration ===
TELEGRAM_TOKEN=your_telegram_bot_token_here
WEBHOOK_HOST=your-domain.com
WEBHOOK_PORT=8001
WEBHOOK_PATH=/webhook

# === Payment System - Heleket Configuration ===
MERCHANT_UUID=your_merchant_uuid_here
API_KEY=your_api_key_here
PAYMENT_TIMEOUT=300

# === Database Configuration (Neon PostgreSQL) ===
DATABASE_URL=postgresql+asyncpg://username:password@host.neon.tech/database?ssl=require
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=30

# === Redis Cluster Configuration ===
REDIS_MASTER_HOST=redis-node-1
REDIS_MASTER_PORT=7379
REDIS_SLAVE1_HOST=redis-node-2
REDIS_SLAVE1_PORT=7380
REDIS_SLAVE2_HOST=redis-node-3
REDIS_SLAVE2_PORT=7381
REDIS_PASSWORD=your_redis_password
REDIS_CLUSTER_ENABLED=True

# === Circuit Breaker Configuration ===
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60
CIRCUIT_BREAKER_EXPECTED_EXCEPTION=Exception

# === Rate Limiting Configuration ===
RATE_LIMIT_REQUESTS_PER_MINUTE=60
RATE_LIMIT_BURST=10

# === Session Management Configuration ===
SESSION_CACHE_TTL=1800
USER_CACHE_TTL=1800
PAYMENT_CACHE_TTL=900

# === Balance Service Configuration ===
BALANCE_SERVICE_ENABLED=True
BALANCE_PURCHASE_ENABLED=True
MIN_BALANCE_PURCHASE_AMOUNT=1
MAX_BALANCE_PURCHASE_AMOUNT=10000

# === Application Configuration ===
DEBUG=False
LOG_LEVEL=INFO
ENVIRONMENT=production
HEALTH_CHECK_INTERVAL=30

# === SSL Configuration ===
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
curl http://localhost:8001/health

# Проверка состояния Redis кластера
docker-compose exec redis-master redis-cli -a $REDIS_PASSWORD cluster nodes
```

### 5. Инициализация базы данных

```bash
# Применение миграций через Docker
docker-compose exec telegram-bot alembic upgrade head

# Проверка состояния миграций
docker-compose exec telegram-bot alembic current

# Проверка подключения к базе данных
docker-compose exec telegram-bot python -c "from config.settings import settings; print('DB connected' if settings.database_url else 'DB not configured')"
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

# Запуск с hot reload (для разработки)
python main.py --debug
```

### 7. Проверка работоспособности

```bash
# Проверка health checks
curl -k https://localhost:8443/health
curl http://localhost:8080/health
curl http://localhost:8001/health


# Проверка состояния сервисов
docker-compose ps


# Проверка логов
docker-compose logs telegram-bot --tail=20

# Проверка подключения к Redis
docker-compose exec redis-master redis-cli -a $REDIS_PASSWORD ping

# Проверка подключения к PostgreSQL
docker-compose exec telegram-bot python -c "from repositories.user_repository import UserRepository; import asyncio; print(asyncio.run(UserRepository().check_connection()))"
```

### 8. Настройка мониторинга

```bash
# Запуск мониторинга в отдельном терминале
docker-compose logs -f telegram-bot

# Проверка ресурсов
docker stats

# Проверка состояния Redis кластера
docker-compose exec redis-master redis-cli -a $REDIS_PASSWORD info cluster

## 📁 Структура проекта

```

telegram-bot/
├── alembic/                    # Миграции базы данных
│   ├── versions/              # Файлы миграций
│   ├── env.py                # Конфигурация Alembic
│   └── alembic.ini           # Настройки Alembic
├── config/                    # Конфигурация
│   ├── **init**.py
│   └── settings.py           # Настройки приложения
├── core/                     # Ядро приложения
│   ├── **init**.py
│   └── interfaces.py         # Интерфейсы для SOLID
├── handlers/                 # Обработчики
│   ├── **init**.py
│   └── message_handler.py    # Telegram команды
├── repositories/             # Репозитории
│   ├── **init**.py
│   └── user_repository.py    # Работа с PostgreSQL
├── services/                 # Бизнес-логика и микросервисы
│   ├── **init**.py
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
│   └── **init**.py
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
| telegram-bot   | 8001           | Основное приложение (webhook)     |
| telegram-bot   | 8081           | WebSocket порт                    |
| nginx          | 80, 443, 8080  | Reverse proxy с SSL               |
| redis-node-1   | 7379           | Redis master нода                 |
| redis-node-2   | 7380           | Redis node 2                      |
| redis-node-3   | 7381           | Redis node 3                      |
| redis-replica-1| 7382           | Redis replica 1                   |
| redis-replica-2| 7383           | Redis replica 2                   |
| redis-replica-3| 7384           | Redis replica 3                   |
| PostgreSQL     | 5432           | База данных (внешний Neon)        |

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

## 🏗️ Архитектурные улучшения и оптимизация

### Оптимизация handlers/message_handler.py

#### SOLID принципы в действии

- **Single Responsibility** - каждый метод отвечает за конкретную функциональность
- **Open/Closed** - расширяемость через новые callback обработчики без изменения существующего кода
- **Liskov Substitution** - все сервисы могут быть заменены на аналогичные без нарушения работы
- **Interface Segregation** - четкое разделение интерфейсов для разных типов операций
- **Dependency Inversion** - использование абстракций вместо конкретных реализаций

#### Новая архитектура обработчика

```python
class MessageHandler(EventHandlerInterface):
    """Обработчик сообщений с поддержкой сессий и кеширования"""
    
    async def handle_message(self, message: Message, bot: Bot) -> None:
        """Обработка текстового сообщения с управлением сессиями"""
        # Rate limiting проверка
        # Управление сессиями
        # Обработка сообщений
        
    async def handle_callback(self, callback: CallbackQuery, bot: Bot) -> None:
        """Обработка callback запросов с управлением сессиями"""
        # Rate limiting проверка
        # Маршрутизация callback
        # Обработка конкретных действий
```

### Сервисная архитектура

#### Новые сервисы

- **BalanceService** - управление балансом пользователей
- **StarPurchaseService** - покупка звезд с разными опциями
- **SessionCache** - управление пользовательскими сессиями
- **RateLimitCache** - защита от злоупотреблений
- **PaymentCache** - кеширование платежных данных

#### Улучшенные существующие сервисы

- **UserRepository** - добавлено кеширование
- **PaymentService** - интеграция с circuit breaker
- **UserCache** - оптимизированное кеширование

### Система кеширования

#### Многоуровневое кеширование

```python
# Иерархия кеша
1. User Cache - данные пользователей (30 мин)
2. Session Cache - сессии (30 мин)
3. Payment Cache - платежи (15 мин)
4. Rate Limit Cache - лимиты (1 мин)
```

#### Стратегии кеширования

- **Cache-Aside** - проверка кеша перед запросом к БД
- **Write-Through** - автоматическое обновление кеша при изменении данных
- **TTL** - автоматическое устаревание данных
- **Cache Invalidation** - принудительное очищение при необходимости

### Защита и надежность

#### Circuit Breaker

```python
# Автоматическая защита при сбоях
- Failure Threshold: 5 ошибок
- Recovery Timeout: 60 секунд
- Half-Open Attempts: 3
- Expected Exceptions: все исключения
```

#### Rate Limiting

```python
# Многоуровневая защита
- Messages: 10 запросов в минуту
- Callbacks: 20 запросов в минуту
- API: 10 запросов в минуту
- Payments: 2 запроса в минуту
```

### Производительность

#### Оптимизации

- **Async/await** - асинхронная обработка всех операций
- **Connection Pooling** - пул соединений с PostgreSQL
- **Redis Cluster** - распределенное кеширование
- **Batch Operations** - групповые операции с БД
- **Lazy Loading** - отложенная загрузка данных

#### Мониторинг производительности

- **Health Checks** - автоматическая проверка состояния
- **Metrics Collection** - сбор метрик производительности
- **Logging** - детальное логирование всех операций
- **Error Tracking** - отслеживание ошибок и аномалий

## 💳 Покупка звезд через Heleкет

### Процесс покупки с кешированием и защитами

```mermaid
sequenceDiagram
    participant User as Пользователь
    participant Bot as Telegram Bot
    participant Cache as Redis Cache
    participant CB as Circuit Breaker
    participant Heleket as Heleket API
    participant DB as PostgreSQL
    participant RL as Rate Limiter

    User->>Bot: Нажимает "Покупка Звезд"
    Bot->>RL: Проверка rate limiting
    RL->>Bot: Разрешение/Запрет
    Bot->>Cache: Проверка кеша пакетов
    Cache-->>Bot: Возвращает кешированные пакеты

    Bot->>User: Показывает пакеты звезд
    User->>Bot: Выбирает пакет
    Bot->>CB: Проверка состояния circuit breaker
    CB->>Bot: Разрешение/Запрет
    Bot->>Heleket: Создает счет на оплату
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

#### 🌟 Стандартные пакеты

- **100 звезд** - базовый пакет (+10 бонусных звезд, экономия 5%)
- **250 звезд** - стандартный пакет (+25 бонусных звезд, экономия 10%)
- **500 звезд** - расширенный пакет (+50 бонусных звезд, экономия 15%)
- **1000 звезд** - максимальный пакет (+100 бонусных звезд, экономия 20%)

#### 💎 Покупка с баланса

- **100 звезд** - 100 TON с баланса
- **250 звезд** - 250 TON с баланса
- **500 звезд** - 500 TON с баланса
- **1000 звезд** - 1000 TON с баланса
- **Своя сумма** - от 1 до 10000 звезд с баланса

#### 🎯 Быстрое пополнение

- **10 TON** - минимальное пополнение
- **50 TON** - быстрое пополнение
- **100 TON** - стандартное пополнение
- **500 TON** - максимальное пополнение
- **Своя сумма** - от 10 до 10000 TON

## 🎨 Улучшенный интерфейс пользователя v2.0

### Визуальные улучшения

Бот получил современный и привлекательный интерфейс с множеством визуальных улучшений:

- **Эмодзи иконки** - интуитивно понятные символы для каждого действия
- **HTML форматирование** - выделение важной информации жирным шрифтом и курсивом
- **Иерархическая структура меню** - четкая навигация между разделами
- **Цветовая схема** - согласованное использование цветов для разных типов сообщений
- **Адаптивные сообщения** - динамическое изменение контента в зависимости от контекста

### Новые функции интерфейса

#### 🌟 Улучшенное главное меню

- Современный дизайн с эмодзи
- Четкое описание основных функций
- Призыв к действию с визуальными акцентами
- Интуитивно понятная навигация

#### 💰 Расширенный экран баланса

- Детальная информация о балансе
- Доступные действия для пользователя
- Визуальное выделение важной информации
- Быстрый доступ к истории транзакций

#### ⭐ Улучшенный магазин звезд

- Описание пакетов с бонусами
- Информация об экономии
- Визуальное разделение пакетов
- Два режима покупки: с баланса и через платежную систему

#### 📊 История транзакций

- Просмотр всех операций за последние 30 дней
- Детальная информация о каждой транзакции
- Фильтрация по типам операций
- Визуальное оформление статусов

#### 🎯 Улучшенные сообщения об ошибках

- Понятные и информативные сообщения
- Визуальное выделение ошибок
- Рекомендации по решению проблем
- Предложения альтернативных действий

#### 🎉 Улучшенные успешные операции

- Праздничное оформление для успешных покупок
- Детальная информация о транзакции
- Благодарность пользователю
- Быстрый доступ к следующим действиям

### Система сессий

- **Управление состоянием** - автоматическое создание и управление сессиями пользователей
- **Кеширование данных** - хранение состояния в Redis для быстрого доступа
- **Восстановление сессий** - автоматическое восстановление прерванных действий
- **Множественные сессии** - поддержка нескольких активных сессий на одного пользователя

### Навигация и удобство использования

- **Инлайн-клавиатуры** - удобные кнопки для быстрого доступа к функциям
- **Иерархическое меню** - логичная структура навигации
- **Визуальные подсказки** - эмодзи для быстрого распознавания функций
- **Оптимизированная компоновка** - правильное расположение элементов интерфейса
- **Умная навигация** - автоматическое возвращение в предыдущие меню

### 🎛️ Система кнопок и Callback обработчиков v2.0

#### Архитектура обработчиков

Все callback обработчики полностью переработаны с использованием `InlineKeyboardBuilder` и строгого следования SOLID принципам:

```python
class CallbackHandler:
    """Расширенный обработчик callback запросов с поддержкой сессий"""
    
    async def handle_callback(self, callback: CallbackQuery, bot: Bot) -> None:
        """Основной метод обработки callback с полным циклом защиты"""
        # 1. Rate limiting проверка
        if not await self._check_rate_limit(callback.from_user.id):
            await callback.answer("❌ Превышен лимит запросов. Попробуйте позже.", show_alert=True)
            return
        
        # 2. Восстановление сессии
        session = await self._restore_session(callback.from_user.id)
        
        # 3. Маршрутизация callback
        await self._route_callback(callback, bot, session)
    
    async def _check_rate_limit(self, user_id: int) -> bool:
        """Проверка rate limiting с поддержкой разных типов действий"""
        return await self.rate_limit_cache.check_user_rate_limit(
            user_id, "callback", 20, 60
        )
```

#### Новая архитектура обработчиков

- **Модульная структура** - каждый тип обработчика в отдельном методе
- **Управление сессиями** - автоматическое создание и восстановление контекста
- **Централизованная маршрутизация** - единая точка входа для всех callback
- **Защита на всех уровнях** - rate limiting, circuit breaker, валидация

#### Основные категории callback обработчиков

##### 🏠 Главное меню

- `home` - возврат в главное меню
- `balance` - просмотр баланса и доступных действий
- `buy_stars` - покупка звезд (магазин)
- `help` - помощь и поддержка
- `settings` - настройки профиля

##### 💰 Баланс и управление

- `balance_main` - основной экран баланса
- `recharge` - пополнение баланса
- `recharge_heleket` - пополнение через Heleket
- `recharge_custom` - быстрое пополнение
- `balance_history` - история транзакций
- `transaction_{uuid}` - детальная информация о транзакции
- `back_to_balance` - возврат к экрану баланса

##### ⭐ Покупка звезд

- `buy_stars_main` - главный экран магазина
- `buy_stars_with_balance` - покупка с баланса
- `buy_stars_with_payment` - покупка через платежную систему
- `buy_100`, `buy_250`, `buy_500`, `buy_1000` - готовые пакеты
- `buy_100_balance`, `buy_250_balance`, `buy_500_balance`, `buy_1000_balance` - пакеты с баланса
- `custom_amount` - ввод своей суммы
- `custom_amount_balance` - ввод своей суммы для покупки с баланса
- `back_to_buy_stars` - возврат к магазину

##### 🔍 Проверка статусов

- `check_payment_{uuid}` - проверка статуса платежа
- `check_recharge_{uuid}` - проверка статуса пополнения
- `refresh_status_{uuid}` - обновление статуса

##### ❓ Помощь и поддержка

- `help_main` - экран помощи
- `help_faq` - часто задаваемые вопросы
- `create_ticket` - создание тикета поддержки
- `contact_admin` - контакт с администратором
- `back_to_help` - возврат к помощи

#### Улучшения в обработчиках v2.0

##### 🛡️ Расширенный Rate Limiting

- **Индивидуальные лимиты** - сообщения (10/мин), callback (20/мин), API (10/мин), платежи (2/мин)
- **Адаптивная блокировка** - временная блокировка с увеличением срока при повторных нарушениях
- **Глобальные и пользовательские лимиты** - защита от ботов и злоумышленников
- **Кеширование лимитов** - быстрая проверка без нагрузки на базу данных

##### 🔄 Улучшенные системы защиты

- **Circuit Breaker** - автоматическая защита при сбоях с логированием и восстановлением
- **Retry with Exponential Backoff** - умные повторные попытки с увеличением интервала
- **Graceful Degradation** - корректная работа при недоступности внешних сервисов
- **Circuit State Management** - визуальное отображение состояния защиты для пользователей

##### 🎯 Расширенная обработка ошибок

- **Категоризация ошибок** - сетевые, платежные, системные, пользовательские
- **Контекстные сообщения** - описание ошибки с учетом текущего состояния
- **Автоматические действия** - предложение альтернатив при ошибках
- **Логирование с контекстом** - полная информация для диагностики

##### 🚀 Оптимизация производительности

- **Многоуровневое кеширование** - User Cache, Payment Cache, Session Cache, Rate Limit Cache
- **Асинхронная обработка** - все операции используют async/await для максимальной производительности
- **Пакетные операции** - групповые запросы к базе данных для уменьшения нагрузки
- **Ленивая загрузка** - отложенная загрузка данных при необходимости

##### 📊 Улучшенный мониторинг

- **Детальное логирование** - каждый шаг обработки с таймингами
- **Метрики производительности** - отслеживание времени выполнения операций
- **Health Checks** - автоматическая проверка состояния всех сервисов
- **Аналитика использования** - отслеживание популярности функций и ошибок

#### Пример использования нового обработчика

```python
# Пример callback для покупки звезд
async def handle_buy_stars(self, callback: CallbackQuery, bot: Bot, session: UserSession) -> None:
    """Обработка покупки звезд с полным циклом защиты"""
    
    # Получение пакетов из кеша
    packages = await self.payment_cache.get_star_packages()
    
    # Создание клавиатуры с пакетами
    keyboard = InlineKeyboardBuilder()
    for package in packages:
        keyboard.button(
            text=f"⭐ {package.stars} звезд (+{package.bonus} бонусных)",
            callback_data=f"buy_{package.id}"
        )
    
    # Отправка сообщения с пакетами
    await callback.message.edit_text(
        "🌟 Выберите пакет звезд для покупки:",
        reply_markup=keyboard.as_markup()
    )
    
    # Обновление сессии
    session.current_state = "buying_stars"
    await self.session_cache.save_session(session)
```

### Обратная совместимость

Все изменения полностью совместимы с существующими функциями бота:

- Сохранены все callback обработчики
- Добавлены новые обработчики без удаления старых
- Улучшено визуальное оформление без изменения логики
- Сохранена работа всех существующих функций

## 📊 Мониторинг и Health Checks

### Health Check Endpoints

```bash
# Проверка общего состояния
curl -k https://localhost:8443/health
curl http://localhost:8080/health
curl http://localhost:8001/health

# Проверка состояния базы данных
curl -k https://localhost:8443/health/db
curl http://localhost:8001/health/db

# Проверка состояния Redis
curl -k https://localhost:8443/health/redis
curl http://localhost:8001/health/redis

# Проверка состояния платежной системы
curl -k https://localhost:8443/health/payment
curl http://localhost:8001/health/payment
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

docker-compose exec redis-node-1 redis-cli -a $REDIS_PASSWORD info replication
docker-compose exec redis-node-1 redis-cli -a $REDIS_PASSWORD cluster nodes

# Проверка PostgreSQL подключения
docker-compose exec telegram-bot python -c "from config.settings import settings; print('DB connected' if settings.database_url else 'DB not configured')"
```

## 🛠️ Переменные окружения

### Обязательные переменные

```env
# Telegram Bot Configuration
TELEGRAM_TOKEN=ваш_токен_бота от @BotFather
WEBHOOK_HOST=your-domain.com

WEBHOOK_PORT=8001
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






REDIS_MASTER_HOST=redis-node-1
REDIS_MASTER_PORT=7379
REDIS_SLAVE1_HOST=redis-node-2
REDIS_SLAVE1_PORT=7380
REDIS_SLAVE2_HOST=redis-node-3
REDIS_SLAVE2_PORT=7381
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


# Подключение к Redis master (node-1)
docker-compose exec redis-node-1 redis-cli -a $REDIS_PASSWORD


# Проверка репликации
docker-compose exec redis-node-1 redis-cli -a $REDIS_PASSWORD info replication


# Просмотр всех ключей
docker-compose exec redis-node-1 redis-cli -a $REDIS_PASSWORD keys "*"


# Очистка кеша
docker-compose exec redis-node-1 redis-cli -a $REDIS_PASSWORD flushall

# Проверка состояния кластера
docker-compose exec redis-node-1 redis-cli -a $REDIS_PASSWORD cluster nodes

# Проверка здоровья кластера
docker-compose exec redis-node-1 redis-cli -a $REDIS_PASSWORD cluster info
```

## 🔒 Безопасность v2.0

### 🛡️ Улучшенные меры защиты

#### Шифрование и соединения

- **SSL/TLS** - обязательное шифрование всех соединений через Nginx с поддержкой HTTP/2
- **PostgreSQL** - параметризованные запросы, SSL соединения, шифрование данных в покое
- **Redis** - аутентификация, шифрование соединений, разделение прав доступа
- **API ключи** - безопасное хранение в .env файлах с ротацией ключей

#### Защита от злоупотреблений

- **Rate limiting** - многоуровневая защита (Nginx + приложение + Redis)
- **Circuit breaker** - автоматическая защита от каскадных отказов с логированием
- **Input validation** - многоуровневая проверка всех входных данных
- **SQL Injection Protection** - параметризованные запросы и ORM
- **XSS Protection** - фильтрация HTML и экранирование данных
- **CSRF Protection** - токены для всех форм и callback обработчиков

#### Платежная безопасность

- **Heleket Integration** - безопасная обработка платежей через проверенного провайдера
- **Payment Validation** - проверка целостности платежных данных
- **Transaction Logging** - полное логирование всех транзакций
- **Fraud Detection** - алгоритмы обнаружения мошеннических операций

#### Инфраструктурная безопасность

- **Docker Security** - изолированные контейнеры, минимальные привилегии, регулярные обновления
- **Network Security** - изоляция сервисов, файрволы, VPN для доступа
- **Access Control** - RBAC (Role-Based Access Control) для внутренних сервисов
- **Secret Management** - безопасное хранение и доступ к секретам

### 📊 Мониторинг безопасности

#### Real-time мониторинг

- **Security Events Logging** - логирование всех событий безопасности
- **Intrusion Detection** - обнаружение подозрительных активностей
- **Anomaly Detection** - алгоритмы обнаружения аномалий в поведении пользователей
- **Performance Monitoring** - отслеживание производительности с точки зрения безопасности

#### Аудит и отчетность

- **Security Auditing** - регулярный аудит системы безопасности
- **Compliance Monitoring** - соответствие стандартам безопасности
- **Incident Response** - автоматическая реакция на инциденты безопасности
- **Backup and Recovery** - регулярное резервное копирование с шифрованием

### 🔐 Конфигурация безопасности

#### Environment variables

```env
# Security Configuration
SECURITY_ENABLED=True
ENCRYPTION_KEY_ROTATION_INTERVAL=86400  # 24 часа
RATE_LIMIT_ENABLED=True
CIRCUIT_BREAKER_ENABLED=True
INPUT_VALIDATION_STRICT=True
PAYMENT_VALIDATION_ENABLED=True
AUDIT_LOGGING_ENABLED=True
```

#### Docker security settings

```yaml
# Пример безопасной конфигурации Docker
services:
  telegram-bot:
    security_opt:
      - no-new-privileges:true
      - apparmor:telegram-bot-profile
    read_only: true
    tmpfs:
      - /tmp
      - /var/tmp
```

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

docker-compose exec redis-node-1 redis-cli -a $REDIS_PASSWORD ping


# Проверка репликации
docker-compose exec redis-node-1 redis-cli -a $REDIS_PASSWORD info replication




# Проверка подключения slave нод
docker-compose exec redis-replica-1 redis-cli -a $REDIS_PASSWORD info replication

# Проверка состояния Redis кластера
docker-compose exec redis-node-1 redis-cli -a $REDIS_PASSWORD cluster nodes

# Перезапуск Redis сервисов
docker-compose restart redis-node-1 redis-node-2 redis-node-3 redis-replica-1 redis-replica-2 redis-replica-3
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
netstat -tulpn | grep -E '8080|8443|8081|8001|5432|7379|7380|7381|7382|7383|7384'

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

2. Проверьте health checks: `curl -k https://localhost:8443/health` и `curl http://localhost:8001/health`
3. Проверьте переменные окружения в `.env`
4. Проверьте миграции: `docker-compose exec telegram-bot alembic current`

5. Проверьте подключение к Neon PostgreSQL
6. Проверьте Redis кластер: `docker-compose exec redis-node-1 redis-cli -a $REDIS_PASSWORD ping`
7. Создайте issue с описанием проблемы, логами и конфигурацией

## 📚 Дополнительные ресурсы

- [Aiogram Documentation](https://docs.aiogram.dev/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Heleket API Documentation](https://heleket.com/docs)
- [Neon PostgreSQL](https://neon.tech/docs)
- [Redis Cluster Documentation](https://redis.io/docs/manual/scaling/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)

- [Nginx SSL Configuration](https://nginx.org/en/docs/http/configuring_https_servers.html)
