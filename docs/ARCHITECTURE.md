# 🏗️ Детальная архитектура Telegram Bot

## 📋 Содержание

- [🏗️ Общая архитектура](#️-общая-архитектура)
- [🧩 Компонентная архитектура](#-компонетная-архитектура)
- [💾 Структура базы данных](#-структура-базы-данных)
- [🔄 Потоки данных](#-потоки-данных)
- [🛡️ Паттерны проектирования](#️-паттерны-проектирования)
- [📈 Масштабируемость](#-масштабируемость)

## 🏗️ Общая архитектура

### Концепция Clean Architecture

```mermaid
graph TB
    subgraph "Presentation Layer"
        TG[Telegram API]
        REST[REST API]
        WEBHOOK[Webhook Handler]
    end

    subgraph "Application Layer"
        MH[Message Handler]
        PH[Payment Handler]
        PuH[Purchase Handler]
        BalH[Balance Handler]
        EH[Error Handler]
    end

    subgraph "Business Logic Layer"
        PS[Payment Service]
        BS[Balance Service]
        SPS[Star Purchase Service]
        FS[Fragment Service]
        RL[Rate Limiter]
        CS[Cache Service]
    end

    subgraph "Data Layer"
        UR[User Repository]
        BR[Balance Repository]
        DB[(Database)]
        CACHE[(Cache)]
    end

    TG --> MH
    REST --> MH
    WEBHOOK --> PS
    
    MH --> PS
    MH --> BS
    MH --> SPS
    MH --> FS
    MH --> RL
    MH --> EH
    
    PH --> PS
    PuH --> SPS
    BalH --> BS
    
    PS --> UR
    BS --> BR
    SPS --> UR
    SPS --> BR
    FS --> UR
    
    UR --> DB
    BR --> DB
    CS --> CACHE
    
    PS --> CS
    BS --> CS
    SPS --> CS
    RL --> CS
```

### Многоуровневая архитектура

```mermaid
graph TD
    subgraph "🎯 PRESENTATION LAYER"
        PL_TG[Telegram Bot]
        PL_REST[REST API]
        PL_WEBHOOK[Webhook Service]
    end
    
    subgraph "🔧 APPLICATION LAYER"
        AL_HANDLERS[Handlers]
        AL_CONTROLLERS[Controllers]
    end
    
    subgraph "⚙️ BUSINESS LOGIC LAYER"
        BLL_SERVICES[Services]
        BLL_VALIDATORS[Validators]
        BLL_PROCESSORS[Processors]
    end
    
    subgraph "🗄️ DATA ACCESS LAYER"
        DAL_REPOSITORIES[Repositories]
        DAL_ENTITIES[Entities]
    end
    
    subgraph "📦 INFRASTRUCTURE"
        INF_DB[PostgreSQL]
        INF_CACHE[Redis]
        INF_EXTERNAL[External APIs]
    end
    
    PL_TG --> AL_HANDLERS
    PL_REST --> AL_CONTROLLERS
    PL_WEBHOOK --> AL_HANDLERS
    
    AL_HANDLERS --> BLL_SERVICES
    AL_CONTROLLERS --> BLL_SERVICES
    
    BLL_SERVICES --> DAL_REPOSITORIES
    BLL_VALIDATORS --> BLL_SERVICES
    BLL_PROCESSORS --> BLL_SERVICES
    
    DAL_REPOSITORIES --> DAL_ENTITIES
    DAL_ENTITIES --> INF_DB
    BLL_SERVICES --> CS
    CS --> INF_CACHE
    
    BLL_SERVICES --> INF_EXTERNAL
```

## 🧩 Компонентная архитектура

### Handlers Layer

```mermaid
graph LR
    subgraph "🎯 HANDLERS LAYER"
        MH["📨 MessageHandler<br/>(aiogram integration)"]
        PH["💳 PaymentHandler<br/>(recharge management)"]
        PuH["🛒 PurchaseHandler<br/>(star purchases)"]
        BalH["💰 BalanceHandler<br/>(balance queries)"]
        EH["❌ ErrorHandler<br/>(error handling)"]
        BH["🔧 BaseHandler<br/>(common functionality)"]
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

### Services Layer

```mermaid
graph LR
    subgraph "⚙️ SERVICES LAYER"
        PS["💳 PaymentService<br/>(Heleket integration)"]
        BS["💰 BalanceService<br/>(balance management)"]
        SPS["⭐ StarPurchaseService<br/>(purchase logic)"]
        FS["💎 FragmentService<br/>(Fragment API)"]
        CS["🗄️ CacheService<br/>(Redis operations)"]
        RL["🚦 RateLimitService<br/>(throttling)"]
        HS["❤️ HealthService<br/>(monitoring)"]
        WS["🔌 WebSocketService<br/>(real-time)"]
    end
    
    PS --> CS
    BS --> CS
    SPS --> CS
    FS --> CS
    RL --> CS
    
    PS --> UR
    BS --> BR
    SPS --> UR
    SPS --> BR
    FS --> SPS
```

### Repository Layer

```mermaid
graph LR
    subgraph "📊 REPOSITORY LAYER"
        UR["👤 UserRepository<br/>(user operations)"]
        BR["💰 BalanceRepository<br/>(balance operations)"]
        TR["📊 TransactionRepository<br/>(transaction operations)"]
    end
    
    UR --> DB
    BR --> DB
    TR --> DB
```

## 💾 Структура базы данных

### Users Table

```sql
CREATE TABLE users (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(32),
    first_name VARCHAR(64),
    last_name VARCHAR(64),
    is_premium BOOLEAN DEFAULT FALSE,
    language_code VARCHAR(10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Balances Table

```sql
CREATE TABLE balances (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id),
    amount DECIMAL(10,2) DEFAULT 0.00,
    currency VARCHAR(10) DEFAULT 'TON',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id)
);
```

### Transactions Table

```sql
CREATE TYPE transaction_type AS ENUM ('purchase', 'refund', 'bonus', 'adjustment', 'recharge');
CREATE TYPE transaction_status AS ENUM ('pending', 'processing', 'completed', 'failed', 'cancelled', 'expired');

CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id),
    transaction_type transaction_type,
    status transaction_status,
    amount DECIMAL(10,2),
    currency VARCHAR(10) DEFAULT 'TON',
    description TEXT,
    external_id VARCHAR(255) UNIQUE,
    transaction_metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Индексы

```sql
-- Индексы для оптимизации запросов
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_transactions_user_id ON transactions(user_id);
CREATE INDEX idx_transactions_external_id ON transactions(external_id);
CREATE INDEX idx_transactions_created_at ON transactions(created_at);
CREATE INDEX idx_transactions_status ON transactions(status);
```

## 🔄 Потоки данных

### Поток покупки звезд через Fragment API

```mermaid
sequenceDiagram
    participant U as 👤 User
    participant TB as 🤖 Telegram Bot
    participant FS as 💎 Fragment Service
    participant F as 🌐 Fragment API
    participant DB as 🗄️ Database
    participant C as 📦 Cache

    U->>TB: /buy_stars_fragment 100
    TB->>FS: buy_stars(username, 100)
    FS->>DB: get_user_info(user_id)
    DB-->>FS: user_data
    FS->>C: check_rate_limit(user_id)
    C-->>FS: allowed
    FS->>F: buy_stars_without_kyc(username, 100)
    F-->>FS: purchase_result
    FS->>DB: create_transaction(completed)
    FS->>C: invalidate_user_cache(user_id)
    FS-->>TB: success/failure
    TB-->>U: ✅ Покупка успешна! +100 ⭐
```

### Поток пополнения баланса

```mermaid
sequenceDiagram
    participant U as 👤 User
    participant TB as 🤖 Telegram Bot
    participant PS as 💳 Payment Service
    participant H as 🏦 Heleket API
    participant WH as 🔗 Webhook Handler
    participant DB as 🗄️ Database
    participant C as 📦 Cache

    U->>TB: /recharge 100
    TB->>PS: create_recharge_invoice(user_id, 100)
    PS->>DB: create_transaction(pending)
    PS->>H: POST /create_invoice
    H-->>PS: invoice_url + uuid
    PS->>C: cache_payment(uuid, user_id)
    PS-->>TB: invoice_url
    TB-->>U: 💳 Ссылка для оплаты
    
    Note over U,H: Пользователь оплачивает счет
    
    H->>WH: POST /webhook/heleket
    WH->>C: get_payment_info(uuid)
    WH->>DB: update_transaction(completed)
    WH->>DB: update_user_balance(+100)
    WH->>C: invalidate_user_cache(user_id)
    WH->>TB: notify_payment_success(user_id)
    TB->>U: ✅ Пополнение успешно! +100 💰
```

## 🛡️ Паттерны проектирования

### Service Layer Pattern

```python
class StarPurchaseService(StarPurchaseServiceInterface):
    """Сервис для управления покупкой звезд"""
    
    def __init__(self, user_repository, balance_repository, payment_service):
        self.user_repository = user_repository
        self.balance_repository = balance_repository
        self.payment_service = payment_service
        self.fragment_service = FragmentService()  # Новый сервис
    
    async def create_star_purchase(self, user_id, amount, purchase_type="balance"):
        """Единая точка входа для всех типов покупок"""
        if purchase_type == "balance":
            return await self._create_star_purchase_with_balance(user_id, amount)
        elif purchase_type == "payment":
            return await self._create_star_purchase_with_payment(user_id, amount)
        elif purchase_type == "fragment":
            return await self._create_star_purchase_with_fragment(user_id, amount)
```

### Repository Pattern

```python
class UserRepository:
    """Репозиторий для работы с пользователями"""
    
    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение пользователя по ID с кешированием"""
        # Попытка получить из кеша
        if self.user_cache:
            cached_user = await self.user_cache.get_user(user_id)
            if cached_user:
                return cached_user
        
        # Получение из базы данных
        query = select(User).where(User.user_id == user_id)
        result = await self.session.execute(query)
        user = result.scalar_one_or_none()
        
        if user and self.user_cache:
            # Сохранение в кеш
            await self.user_cache.cache_user(user_id, user.to_dict())
        
        return user.to_dict() if user else None
```

### Circuit Breaker Pattern

```python
class CircuitBreaker:
    """Circuit Breaker для внешних API"""
    
    def __init__(self, failure_threshold=5, timeout=60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    async def call(self, func, *args, **kwargs):
        """Вызов функции с Circuit Breaker"""
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
```

### Rate Limiting Pattern

```python
class RateLimitService:
    """Сервис для ограничения частоты запросов"""
    
    async def check_rate_limit(self, key: str, limit: int, window: int) -> bool:
        """Проверка лимита запросов для ключа"""
        current_time = int(time.time())
        window_key = f"rate_limit:{key}:{current_time // window}"
        
        # Получение текущего счетчика
        current_count = await self.redis_client.get(window_key)
        if current_count is None:
            # Установка нового счетчика с TTL
            await self.redis_client.setex(window_key, window, 1)
            return True
        
        current_count = int(current_count)
        if current_count >= limit:
            return False
        
        # Увеличение счетчика
        await self.redis_client.incr(window_key)
        return True
```

## 📈 Масштабируемость

### Горизонтальное масштабирование

```mermaid
graph TB
    subgraph "Load Balancer"
        LB[Nginx Load Balancer]
    end
    
    subgraph "Application Cluster"
        APP1[App Instance 1]
        APP2[App Instance 2]
        APP3[App Instance 3]
    end
    
    subgraph "Database Layer"
        PG_PRIMARY[PostgreSQL Primary]
        PG_REPLICA1[Replica 1]
        PG_REPLICA2[Replica 2]
    end
    
    subgraph "Cache Cluster"
        REDIS_CLUSTER[Redis Cluster]
    end
    
    LB --> APP1
    LB --> APP2
    LB --> APP3
    
    APP1 --> PG_PRIMARY
    APP2 --> PG_REPLICA1
    APP3 --> PG_REPLICA2
    
    APP1 --> REDIS_CLUSTER
    APP2 --> REDIS_CLUSTER
    APP3 --> REDIS_CLUSTER
    
    PG_PRIMARY -.-> PG_REPLICA1
    PG_PRIMARY -.-> PG_REPLICA2
```

### Вертикальное масштабирование

```mermaid
graph TB
    subgraph "Enhanced Single Instance"
        APP[Enhanced App]
        subgraph "Connection Pooling"
            DB_POOL[Database Pool]
            CACHE_POOL[Cache Pool]
        end
        subgraph "Async Processing"
            TASK_QUEUE[Task Queue]
            WORKER_POOL[Worker Pool]
        end
    end
    
    APP --> DB_POOL
    APP --> CACHE_POOL
    APP --> TASK_QUEUE
    TASK_QUEUE --> WORKER_POOL
```

### Auto Scaling

```yaml
# docker-compose.scale.yml
version: '3.8'
services:
  app:
    image: telegram-bot:latest
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
      restart_policy:
        condition: on-failure
    environment:
      - REDIS_URL=redis://redis-cluster:7000
      - DATABASE_URL=postgresql://user:pass@postgres-primary:5432/db

  redis-cluster:
    image: redis:7-alpine
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '0.2'
          memory: 256M
```