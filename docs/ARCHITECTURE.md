# 🏗️ Детальная архитектура Telegram Shop Bot

## 📋 Содержание

- [🏗️ Общая архитектура](#️-общая-архитектура)
- [🧩 Компонентная архитектура](#-компонетная-архитектура)
- [💾 Структура базы данных](#-структура-базы-данных)
- [🔄 Потоки данных](#-потоки-данных)
- [🛡️ Паттерны проектирования](#️-паттерны-проектирования)
- [📈 Масштабируемость](#-масштабируемость)
- [🐳 Docker и развертывание](#-docker-и-развертывание)
- [🔧 Конфигурация и настройки](#-конфигурация-и-настройки)

## 🏗️ Общая архитектура

### Концепция Clean Architecture

Проект следует принципам чистой архитектуры (Clean Architecture) с четким разделением ответственности между слоями. Каждый слой имеет строго определенные обязанности и интерфейсы взаимодействия.

```mermaid
graph TB
    subgraph "Presentation Layer"
        TG[Telegram Bot API]
        REST[REST API]
        WEBHOOK[Webhook Handler]
        FASTAPI[FastAPI Server]
    end

    subgraph "Application Layer"
        MH[Message Handler]
        PH[Payment Handler]
        PuH[Purchase Handler]
        BalH[Balance Handler]
        EH[Error Handler]
        BH[Base Handler]
    end

    subgraph "Business Logic Layer"
        PS[Payment Service]
        BS[Balance Service]
        SPS[Star Purchase Service]
        FS[Fragment Service]
        FCM[Fragment Cookie Manager]
        RL[Advanced Rate Limiter]
        CS[Circuit Breaker]
        HS[Health Service]
        WS[Webhook Service]
    end

    subgraph "Data Access Layer"
        UR[User Repository]
        BR[Balance Repository]
        DB[PostgreSQL Database]
    end

    subgraph "Infrastructure Layer"
        RC[Redis Cluster]
        UC[User Cache]
        PC[Payment Cache]
        SC[Session Cache]
        RLC[Rate Limit Cache]
        EXTERNAL[External APIs]
    end

    TG --> MH
    REST --> FASTAPI
    WEBHOOK --> WS
    FASTAPI --> WS

    MH --> PH
    MH --> PuH
    MH --> BalH
    MH --> EH
    MH --> BH

    PH --> PS
    PuH --> SPS
    BalH --> BS
    EH --> BH

    PS --> UR
    BS --> BR
    SPS --> UR
    SPS --> BR
    FS --> FCM
    SPS --> FS

    UR --> DB
    BR --> DB

    PS --> PC
    BS --> UC
    SPS --> PC
    RL --> RLC
    WS --> SC

    PC --> RC
    UC --> RC
    SC --> RC
    RLC --> RC

    FS --> EXTERNAL
    PS --> EXTERNAL
    WS --> EXTERNAL
```

### Многоуровневая архитектура

Архитектура проекта построена на многоуровневом подходе с четким разделением ответственности:

```mermaid
graph TD
    subgraph "🎯 PRESENTATION LAYER"
        PL_TG[Telegram Bot Interface]
        PL_REST[REST API Endpoints]
        PL_WEBHOOK[Webhook Endpoints]
        PL_FASTAPI[FastAPI Application]
    end

    subgraph "🔧 APPLICATION LAYER"
        AL_HANDLERS[Telegram Handlers]
        AL_CONTROLLERS[API Controllers]
        AL_VALIDATORS[Input Validators]
        AL_FORMATTERS[Response Formatters]
    end

    subgraph "⚙️ BUSINESS LOGIC LAYER"
        BLL_SERVICES[Core Services]
        BLL_PROCESSORS[Business Processors]
        BLL_VALIDATORS[Business Rules]
        BLL_MANAGERS[Resource Managers]
    end

    subgraph "🗄️ DATA ACCESS LAYER"
        DAL_REPOSITORIES[Data Repositories]
        DAL_MODELS[Domain Models]
        DAL_MAPPERS[Data Mappers]
    end

    subgraph "🏗️ INFRASTRUCTURE LAYER"
        INF_DB[PostgreSQL with SQLAlchemy]
        INF_CACHE[Redis Cluster]
        INF_EXTERNAL[External API Clients]
        INF_LOGGING[Logging System]
        INF_METRICS[Metrics & Monitoring]
    end

    PL_TG --> AL_HANDLERS
    PL_REST --> AL_CONTROLLERS
    PL_WEBHOOK --> AL_CONTROLLERS
    PL_FASTAPI --> AL_CONTROLLERS

    AL_HANDLERS --> BLL_SERVICES
    AL_CONTROLLERS --> BLL_SERVICES
    AL_VALIDATORS --> BLL_VALIDATORS
    AL_FORMATTERS --> BLL_SERVICES

    BLL_SERVICES --> DAL_REPOSITORIES
    BLL_PROCESSORS --> DAL_REPOSITORIES
    BLL_VALIDATORS --> DAL_REPOSITORIES
    BLL_MANAGERS --> DAL_REPOSITORIES

    DAL_REPOSITORIES --> DAL_MODELS
    DAL_MODELS --> INF_DB
    DAL_MAPPERS --> INF_DB

    BLL_SERVICES --> INF_CACHE
    BLL_SERVICES --> INF_EXTERNAL
    BLL_SERVICES --> INF_LOGGING
    BLL_SERVICES --> INF_METRICS
```

### Архитектура кэширования

Проект использует многоуровневую систему кэширования для оптимизации производительности:

```mermaid
graph LR
    subgraph "Cache Types"
        UC[User Cache]
        PC[Payment Cache]
        SC[Session Cache]
        RLC[Rate Limit Cache]
    end

    subgraph "Cache Strategy"
        L1[Local Cache<br/>TTL: 5min]
        L2[Redis Cache<br/>TTL: 30min-24h]
        DB[(Database)]
    end

    subgraph "Cache Operations"
        READ[Cache Read]
        WRITE[Cache Write]
        INVALIDATE[Cache Invalidate]
    end

    UC --> L1
    PC --> L1
    SC --> L1
    RLC --> L1

    L1 --> L2
    L2 --> DB

    READ --> L1
    WRITE --> L1
    INVALIDATE --> L1
```

## 🧩 Компонентная архитектура

### Handler Layer (Обработчики)

```mermaid
graph LR
    subgraph "🎯 HANDLER LAYER"
        MH["📨 MessageHandler<br/>(центральный диспетчер)"]
        PH["💳 PaymentHandler<br/>(платежи и пополнения)"]
        PuH["🛒 PurchaseHandler<br/>(покупки звезд)"]
        BalH["💰 BalanceHandler<br/>(баланс и история)"]
        EH["❌ ErrorHandler<br/>(обработка ошибок)"]
        BH["🔧 BaseHandler<br/>(базовая функциональность)"]
    end

    MH --> PH
    MH --> PuH
    MH --> BalH
    MH --> EH
    MH --> BH

    PH --> BH
    PuH --> BH
    BalH --> BH
    EH --> BH
```

### Service Layer (Сервисы бизнес-логики)

```mermaid
graph LR
    subgraph "⚙️ SERVICE LAYER"
        PS["💳 PaymentService<br/>(Heleket API)"]
        BS["💰 BalanceService<br/>(управление балансом)"]
        SPS["⭐ StarPurchaseService<br/>(покупки звезд)"]
        FS["💎 FragmentService<br/>(Fragment API)"]
        FCM["🍪 FragmentCookieManager<br/>(управление cookies)"]
        ARL["🚦 AdvancedRateLimiter<br/>(ограничение частоты)"]
        CB["🔌 CircuitBreaker<br/>(защита от сбоев)"]
        HS["❤️ HealthService<br/>(мониторинг здоровья)"]
        WS["🔗 WebhookService<br/>(обработка webhook)"]
    end

    PS --> BS
    SPS --> BS
    SPS --> FS
    FS --> FCM
    ARL --> CB
    WS --> HS
```

### Repository Layer (Репозитории данных)

```mermaid
graph LR
    subgraph "📊 REPOSITORY LAYER"
        UR["👤 UserRepository<br/>(пользователи)"]
        BR["💰 BalanceRepository<br/>(баланс и транзакции)"]
    end

    UR --> BR
```

### Cache Layer (Слой кэширования)

```mermaid
graph LR
    subgraph "🗄️ CACHE LAYER"
        UC["👤 UserCache<br/>(кэш пользователей)"]
        PC["💳 PaymentCache<br/>(кэш платежей)"]
        SC["🔗 SessionCache<br/>(кэш сессий)"]
        RLC["🚦 RateLimitCache<br/>(кэш ограничений)"]
        BC["🔧 BaseCache<br/>(базовый кэш)"]
    end

    UC --> BC
    PC --> BC
    SC --> BC
    RLC --> BC
```

## 💾 Структура базы данных

### Основные таблицы

```sql
-- Пользователи
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    user_id BIGINT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Балансы пользователей
CREATE TABLE balances (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE UNIQUE,
    amount DECIMAL(10,2) DEFAULT 0.00,
    currency VARCHAR(3) DEFAULT 'TON',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Транзакции
CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    transaction_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    amount DECIMAL(10,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'TON',
    description TEXT,
    external_id VARCHAR(100) UNIQUE,
    transaction_metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Индексы для оптимизации
CREATE INDEX idx_users_user_id ON users(user_id);
CREATE INDEX idx_balances_user_id ON balances(user_id);
CREATE INDEX idx_transactions_user_id ON transactions(user_id);
CREATE INDEX idx_transactions_external_id ON transactions(external_id);
CREATE INDEX idx_transactions_status ON transactions(status);
CREATE INDEX idx_transactions_created_at ON transactions(created_at);
```

### Связи между таблицами

```mermaid
erDiagram
    users ||--o{ balances : has
    users ||--o{ transactions : has

    users {
        integer id PK
        bigint user_id UK
        timestamp created_at
    }

    balances {
        integer id PK
        bigint user_id FK
        decimal amount
        varchar currency
        timestamp updated_at
        timestamp created_at
    }

    transactions {
        integer id PK
        bigint user_id FK
        varchar transaction_type
        varchar status
        decimal amount
        varchar currency
        text description
        varchar external_id UK
        jsonb transaction_metadata
        timestamp created_at
        timestamp updated_at
    }
```

## 🔄 Потоки данных

### Поток покупки звезд через баланс

```mermaid
sequenceDiagram
    participant U as 👤 Пользователь
    participant TB as 🤖 Telegram Bot
    participant MH as 📨 MessageHandler
    participant PuH as 🛒 PurchaseHandler
    participant SPS as ⭐ StarPurchaseService
    participant BS as 💰 BalanceService
    participant BR as 💰 BalanceRepository
    participant DB as 🗄️ PostgreSQL
    participant UC as 🗄️ UserCache
    participant RC as 📦 Redis Cluster

    U->>TB: /buy_stars 100
    TB->>MH: handle_message()
    MH->>PuH: buy_stars_preset()
    PuH->>SPS: create_star_purchase()
    SPS->>BS: get_user_balance()
    BS->>UC: get_user_balance()
    UC->>RC: GET user_balance:123
    RC-->>UC: cached_balance
    UC-->>BS: balance_data
    BS-->>SPS: balance_info

    SPS->>BS: check_balance_sufficiency()
    BS-->>SPS: sufficient

    SPS->>BR: create_transaction(purchase)
    BR->>DB: INSERT transaction
    DB-->>BR: transaction_id

    SPS->>BS: update_user_balance(-100)
    BS->>BR: update_balance()
    BR->>DB: UPDATE balance
    BS->>UC: update_user_balance()
    UC->>RC: SET user_balance:123

    SPS->>BR: update_transaction_status(completed)
    BR->>DB: UPDATE transaction

    SPS-->>PuH: success
    PuH-->>MH: success
    MH-->>TB: success
    TB-->>U: ✅ Звезды куплены!
```

### Поток пополнения баланса

```mermaid
sequenceDiagram
    participant U as 👤 Пользователь
    participant TB as 🤖 Telegram Bot
    participant MH as 📨 MessageHandler
    participant PH as 💳 PaymentHandler
    participant PS as 💳 PaymentService
    participant H as 🏦 Heleket API
    participant WS as 🔗 WebhookService
    participant BS as 💰 BalanceService
    participant DB as 🗄️ PostgreSQL
    participant PC as 🗄️ PaymentCache
    participant RC as 📦 Redis Cluster

    U->>TB: /recharge 50
    TB->>MH: handle_message()
    MH->>PH: create_recharge()
    PH->>PS: create_recharge_invoice()
    PS->>H: POST /create_invoice
    H-->>PS: invoice_url + uuid
    PS->>PC: cache_payment_details()
    PC->>RC: SET payment:uuid
    PS-->>PH: invoice_data
    PH-->>MH: invoice_url
    MH-->>TB: invoice_url
    TB-->>U: 💳 Ссылка для оплаты

    Note over U,H: Пользователь оплачивает счет

    H->>WS: POST /webhook/heleket
    WS->>PC: get_payment_details(uuid)
    PC->>RC: GET payment:uuid
    RC-->>PC: payment_info
    WS->>BS: process_recharge()
    BS->>BS: update_user_balance(+50)
    BS->>DB: UPDATE balance
    BS->>PC: invalidate_payment_cache()
    PC->>RC: DEL payment:uuid
    WS-->>H: OK

    WS-->>TB: payment_success
    TB-->>U: ✅ Баланс пополнен!
```

### Поток покупки звезд через Fragment API

```mermaid
sequenceDiagram
    participant U as 👤 Пользователь
    participant TB as 🤖 Telegram Bot
    participant MH as 📨 MessageHandler
    participant PuH as 🛒 PurchaseHandler
    participant SPS as ⭐ StarPurchaseService
    participant FS as 💎 FragmentService
    participant FCM as 🍪 FragmentCookieManager
    participant F as 🌐 Fragment API
    participant DB as 🗄️ PostgreSQL

    U->>TB: /buy_stars_fragment 100
    TB->>MH: handle_message()
    MH->>PuH: buy_stars_fragment()
    PuH->>SPS: create_star_purchase_fragment()
    SPS->>FS: buy_stars_without_kyc()
    FS->>FCM: refresh_cookies_if_needed()
    FCM->>F: check_cookie_validity()
    F-->>FCM: cookie_status

    alt Cookies expired
        FCM->>F: authenticate_and_get_cookies()
        F-->>FCM: new_cookies
        FCM->>FCM: save_cookies_to_file()
    end

    FS->>F: buy_stars_without_kyc()
    F-->>FS: purchase_result
    FS-->>SPS: success

    SPS->>DB: create_transaction()
    SPS-->>PuH: success
    PuH-->>MH: success
    MH-->>TB: success
    TB-->>U: ✅ Звезды куплены через Fragment!
```

## 🛡️ Паттерны проектирования

### SOLID принципы в архитектуре

#### 1. Single Responsibility Principle (SRP)
Каждый класс имеет одну ответственность:

```python
class PaymentService(PaymentInterface):
    """Отвечает только за платежи через Heleket API"""

class BalanceService(BalanceServiceInterface):
    """Отвечает только за управление балансом"""

class UserRepository(DatabaseInterface):
    """Отвечает только за доступ к данным пользователей"""
```

#### 2. Open/Closed Principle (OCP)
Классы открыты для расширения, закрыты для модификации:

```python
class BaseHandler:
    """Базовый обработчик с основной функциональностью"""

class MessageHandler(BaseHandler):
    """Расширяет базовый обработчик для Telegram сообщений"""

class PaymentHandler(BaseHandler):
    """Расширяет базовый обработчик для платежей"""
```

#### 3. Liskov Substitution Principle (LSP)
Объекты могут быть заменены экземплярами их подтипов:

```python
class DatabaseInterface(ABC):
    @abstractmethod
    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        pass

class UserRepository(DatabaseInterface):
    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        # Реализация для PostgreSQL
        pass
```

#### 4. Interface Segregation Principle (ISP)
Клиенты не должны зависеть от интерфейсов, которые они не используют:

```python
class PaymentInterface(ABC):
    @abstractmethod
    async def create_invoice(self, amount: str, currency: str, order_id: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def check_payment(self, invoice_uuid: str) -> Dict[str, Any]:
        pass

class BalanceServiceInterface(ABC):
    @abstractmethod
    async def get_user_balance(self, user_id: int) -> Dict[str, Any]:
        pass
```

#### 5. Dependency Inversion Principle (DIP)
Высокий уровень модулей не должен зависеть от низкого уровня:

```python
class BalanceService:
    def __init__(self, user_repository: DatabaseInterface, balance_repository: DatabaseInterface):
        self.user_repository = user_repository
        self.balance_repository = balance_repository
```

### Repository Pattern

```python
class UserRepository:
    """Репозиторий для работы с пользователями"""

    def __init__(self, database_url: str, user_cache: Optional[UserCache] = None):
        self.database_url = database_url
        self.user_cache = user_cache

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        # Сначала проверяем кэш
        if self.user_cache:
            cached_user = await self.user_cache.get_user_profile(user_id)
            if cached_user:
                return cached_user

        # Если нет в кэше, получаем из базы
        async with self.async_session() as session:
            stmt = select(User).where(User.user_id == user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if user:
                user_data = {
                    "id": user.id,
                    "user_id": user.user_id,
                    "created_at": user.created_at.isoformat()
                }

                # Кешируем результат
                if self.user_cache:
                    await self.user_cache.cache_user_profile(user_id, user_data)

                return user_data

        return None
```

### Cache-Aside Pattern

```python
class BalanceService:
    """Сервис баланса с кэшированием"""

    async def get_user_balance(self, user_id: int) -> Dict[str, Any]:
        # Сначала пытаемся получить из кэша
        if self.user_cache:
            cached_balance = await self.user_cache.get_user_balance(user_id)
            if cached_balance is not None:
                return {
                    "user_id": user_id,
                    "balance": cached_balance,
                    "currency": "TON",
                    "source": "cache"
                }

        # Если в кэше нет, получаем из базы данных
        balance_data = await self.balance_repository.get_user_balance(user_id)
        if balance_data:
            # Кешируем результат
            if self.user_cache:
                await self.user_cache.cache_user_balance(user_id, int(balance_data["balance"]))

            balance_data["source"] = "database"
            return balance_data
        else:
            # Если баланса нет, создаем его
            await self.balance_repository.create_user_balance(user_id, 0)
            return {
                "user_id": user_id,
                "balance": 0,
                "currency": "TON",
                "source": "database"
            }
```

### Circuit Breaker Pattern

```python
class CircuitBreaker:
    """Circuit Breaker для защиты от сбоев внешних API"""

    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    async def call(self, func, *args, **kwargs):
        """Вызов функции с защитой Circuit Breaker"""
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "HALF_OPEN"
            else:
                raise CircuitBreakerOpenException("Circuit breaker is open")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e

    def _on_success(self):
        """Обработка успешного вызова"""
        self.failure_count = 0
        self.state = "CLOSED"

    def _on_failure(self):
        """Обработка неудачного вызова"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
```

### Strategy Pattern для платежей

```python
class PaymentStrategy(ABC):
    """Базовая стратегия платежей"""

    @abstractmethod
    async def process_payment(self, amount: float, user_id: int) -> Dict[str, Any]:
        pass

class HeleketPaymentStrategy(PaymentStrategy):
    """Стратегия платежей через Heleket"""

    async def process_payment(self, amount: float, user_id: int) -> Dict[str, Any]:
        # Реализация платежа через Heleket
        pass

class BalancePaymentStrategy(PaymentStrategy):
    """Стратегия платежей с баланса"""

    async def process_payment(self, amount: float, user_id: int) -> Dict[str, Any]:
        # Реализация платежа с баланса
        pass

class PaymentProcessor:
    """Процессор платежей с выбором стратегии"""

    def __init__(self):
        self.strategies = {
            "heleket": HeleketPaymentStrategy(),
            "balance": BalancePaymentStrategy(),
            "fragment": FragmentPaymentStrategy()
        }

    async def process(self, payment_type: str, amount: float, user_id: int) -> Dict[str, Any]:
        strategy = self.strategies.get(payment_type)
        if not strategy:
            raise ValueError(f"Unknown payment type: {payment_type}")

        return await strategy.process_payment(amount, user_id)
```

## 📈 Масштабируемость

### Горизонтальное масштабирование

```mermaid
graph TB
    subgraph "Load Balancer Layer"
        NGINX[NGINX Load Balancer]
        CLOUDFLARE[Cloudflare Load Balancer]
    end

    subgraph "Application Layer"
        APP1[App Instance 1]
        APP2[App Instance 2]
        APP3[App Instance 3]
        APP4[App Instance 4]
    end

    subgraph "Database Layer"
        PG_MASTER[PostgreSQL Master]
        PG_SLAVE1[Slave 1]
        PG_SLAVE2[Slave 2]
        PG_SLAVE3[Slave 3]
    end

    subgraph "Cache Layer"
        REDIS_MASTER[Redis Master]
        REDIS_SLAVE1[Redis Slave 1]
        REDIS_SLAVE2[Redis Slave 2]
        REDIS_SENTINEL[Redis Sentinel]
    end

    subgraph "External Services"
        TG_BOT[Telegram Bot API]
        HELEKET[Heleket API]
        FRAGMENT[Fragment API]
    end

    CLOUDFLARE --> NGINX
    NGINX --> APP1
    NGINX --> APP2
    NGINX --> APP3
    NGINX --> APP4

    APP1 --> PG_MASTER
    APP2 --> PG_SLAVE1
    APP3 --> PG_SLAVE2
    APP4 --> PG_SLAVE3

    PG_MASTER -.-> PG_SLAVE1
    PG_MASTER -.-> PG_SLAVE2
    PG_MASTER -.-> PG_SLAVE3

    APP1 --> REDIS_MASTER
    APP2 --> REDIS_MASTER
    APP3 --> REDIS_MASTER
    APP4 --> REDIS_MASTER

    REDIS_MASTER -.-> REDIS_SLAVE1
    REDIS_MASTER -.-> REDIS_SLAVE2
    REDIS_SENTINEL -.-> REDIS_MASTER

    APP1 --> TG_BOT
    APP2 --> TG_BOT
    APP3 --> TG_BOT
    APP4 --> TG_BOT

    APP1 --> HELEKET
    APP2 --> HELEKET
    APP3 --> HELEKET
    APP4 --> HELEKET

    APP1 --> FRAGMENT
    APP2 --> FRAGMENT
    APP3 --> FRAGMENT
    APP4 --> FRAGMENT
```

### Вертикальное масштабирование

```mermaid
graph TB
    subgraph "Single Enhanced Instance"
        APP[Enhanced App Server]
        subgraph "Connection Pooling"
            DB_POOL[Database Connection Pool]
            REDIS_POOL[Redis Connection Pool]
            API_POOL[External API Pool]
        end
        subgraph "Async Processing"
            TASK_QUEUE[Task Queue]
            WORKER_POOL[Worker Pool]
            BG_JOBS[Background Jobs]
        end
        subgraph "Caching Layers"
            L1_CACHE[L1 Local Cache]
            L2_CACHE[L2 Redis Cache]
            CDN_CACHE[CDN Cache]
        end
    end

    subgraph "Infrastructure"
        DB[(PostgreSQL)]
        REDIS[(Redis Cluster)]
        EXTERNAL[External APIs]
        MONITORING[Monitoring]
        LOGGING[Logging]
    end

    APP --> DB_POOL
    APP --> REDIS_POOL
    APP --> API_POOL

    APP --> TASK_QUEUE
    TASK_QUEUE --> WORKER_POOL
    APP --> BG_JOBS

    APP --> L1_CACHE
    L1_CACHE --> L2_CACHE
    L2_CACHE --> CDN_CACHE

    DB_POOL --> DB
    REDIS_POOL --> REDIS
    API_POOL --> EXTERNAL

    APP --> MONITORING
    APP --> LOGGING
    WORKER_POOL --> MONITORING
    BG_JOBS --> LOGGING
```

### Redis Cluster Architecture

```mermaid
graph TB
    subgraph "Redis Cluster"
        MASTER1[Master 1<br/>Slots 0-5460]
        MASTER2[Master 2<br/>Slots 5461-10922]
        MASTER3[Master 3<br/>Slots 10923-16383]

        SLAVE1_1[Slave 1.1]
        SLAVE1_2[Slave 1.2]
        SLAVE2_1[Slave 2.1]
        SLAVE2_2[Slave 2.2]
        SLAVE3_1[Slave 3.1]
        SLAVE3_2[Slave 3.2]
    end

    subgraph "Application Layer"
        APP1[App 1]
        APP2[App 2]
        APP3[App 3]
    end

    subgraph "Cache Types"
        USER_CACHE[User Cache]
        PAYMENT_CACHE[Payment Cache]
        SESSION_CACHE[Session Cache]
        RATE_LIMIT_CACHE[Rate Limit Cache]
    end

    APP1 --> MASTER1
    APP1 --> MASTER2
    APP1 --> MASTER3

    APP2 --> MASTER1
    APP2 --> MASTER2
    APP2 --> MASTER3

    APP3 --> MASTER1
    APP3 --> MASTER2
    APP3 --> MASTER3

    MASTER1 -.-> SLAVE1_1
    MASTER1 -.-> SLAVE1_2
    MASTER2 -.-> SLAVE2_1
    MASTER2 -.-> SLAVE2_2
    MASTER3 -.-> SLAVE3_1
    MASTER3 -.-> SLAVE3_2

    USER_CACHE --> MASTER1
    PAYMENT_CACHE --> MASTER2
    SESSION_CACHE --> MASTER3
    RATE_LIMIT_CACHE --> MASTER1
```

## 🐳 Docker и развертывание

### Docker Compose Architecture

```yaml
version: '3.8'
services:
  app:
    build: .
    environment:
      - TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
    ports:
      - "8001:8001"
    depends_on:
      - postgres
      - redis
    volumes:
      - ./logs:/app/logs

  postgres:
    image: postgres:15
    environment:
      - POSTGRES_DB=telegram_bot
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/ssl/certs
    depends_on:
      - app

volumes:
  postgres_data:
  redis_data:
```

### Cloudflare Integration

```mermaid
graph TB
    subgraph "Cloudflare Edge"
        CF_EDGE[Cloudflare Edge Network]
        CF_DNS[Cloudflare DNS]
        CF_WAF[Web Application Firewall]
        CF_SSL[SSL/TLS Termination]
        CF_DDOS[DDoS Protection]
        CF_RATE[Rate Limiting]
    end

    subgraph "Application Infrastructure"
        CF_TUNNEL[Cloudflare Tunnel]
        NGINX[NGINX Reverse Proxy]
        APP[Telegram Bot App]
        WEBHOOK[Webhook Service]
    end

    subgraph "External Services"
        TG[Telegram API]
        HELEKET[Heleket API]
        FRAGMENT[Fragment API]
    end

    CF_DNS --> CF_EDGE
    CF_EDGE --> CF_WAF
    CF_WAF --> CF_SSL
    CF_SSL --> CF_DDOS
    CF_DDOS --> CF_RATE
    CF_RATE --> CF_TUNNEL

    CF_TUNNEL --> NGINX
    NGINX --> APP
    NGINX --> WEBHOOK

    APP --> TG
    WEBHOOK --> HELEKET
    APP --> FRAGMENT
```

## 🔧 Конфигурация и настройки

### Основные компоненты конфигурации

```python
class Settings:
    """Централизованная конфигурация приложения"""

    # Telegram Bot
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "")

    # Database - PostgreSQL
    database_url: str = f"postgresql+asyncpg://user:pass@localhost:5432/db"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # Redis Configuration
    redis_url: str = "redis://redis-node-1:7379"
    redis_cluster_nodes: str = "redis-node-1:7379,redis-node-2:7380"
    is_redis_cluster: bool = False

    # External APIs
    merchant_uuid: str = os.getenv("MERCHANT_UUID", "")
    api_key: str = os.getenv("API_KEY", "")
    fragment_seed_phrase: str = os.getenv("FRAGMENT_SEED_PHRASE", "")

    # Webhook Configuration
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8001
    production_domain: str = ""

    # Cache TTL Settings
    cache_ttl_user: int = 1800      # 30 минут
    cache_ttl_payment: int = 900    # 15 минут
    cache_ttl_session: int = 1800   # 30 минут
    cache_ttl_rate_limit: int = 60  # 1 минута

    # Rate Limiting
    rate_limit_user_messages: int = 30     # 30 сообщений/мин
    rate_limit_user_operations: int = 20   # 20 операций/мин
    rate_limit_user_payments: int = 5      # 5 платежей/мин

# Глобальный экземпляр настроек
settings = Settings()
```

### Переменные окружения

```bash
# Обязательные переменные
TELEGRAM_TOKEN=your_telegram_bot_token
DATABASE_URL=postgresql://user:password@host:port/database
REDIS_URL=redis://host:port

# Платежная система
MERCHANT_UUID=your_heleket_merchant_uuid
API_KEY=your_heleket_api_key

# Fragment API
FRAGMENT_SEED_PHRASE=your_24_words_seed_phrase
FRAGMENT_COOKIES=cookies_data

# Производственная среда
PRODUCTION_DOMAIN=your-domain.com
WEBHOOK_SECRET=your_webhook_secret

# Опциональные настройки
DEBUG=false
LOG_LEVEL=INFO
REDIS_CLUSTER_ENABLED=false
```

---

*Последнее обновление: 27 августа 2025 г.*
*Версия архитектуры: 2.0*
