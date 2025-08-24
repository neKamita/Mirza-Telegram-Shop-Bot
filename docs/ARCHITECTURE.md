# 🏗️ Детальная архитектура Telegram Bot

## 📋 Содержание

- [🏗️ Общая архитектура](#️-общая-архитектура)
- [🧩 Компонентная архитектура](#-компонетная-архитектура)
- [📝 Централизованное форматирование](#-централизованное-форматирование)
- [🔗 Интеграция utils и services](#-интеграция-utils-и-services)
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

    subgraph "Utils Layer"
        MF[Message Formatter]
        MT[Message Templates]
        RM[Rate Limit Messages]
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

    PS --> MF
    BS --> MF
    SPS --> MF
    FS --> MF
    MF --> MT

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

## 📝 Централизованное форматирование

### 4.1 MessageFormatter
- Единый класс для форматирования всех типов сообщений
- Интегрирован в BalanceService и PaymentService
- Обеспечивает консистентность интерфейса

### 4.2 MessageTemplate
- Централизованные шаблоны сообщений
- Единые константы эмодзи и статусов
- Устранение дублирования HTML форматирования

## 🔗 Интеграция utils и services

### Архитектурный поток данных

```mermaid
graph TD
    subgraph "🛠️ Utils Layer"
        MF["📨 MessageFormatter<br/>(центральное форматирование)"]
        MT["📝 MessageTemplates<br/>(шаблоны и константы)"]
        RM["⚡ RateLimitMessages<br/>(сообщения ограничений)"]
    end

    subgraph "⚙️ Services Layer"
        PS["💳 PaymentService<br/>(пополнение баланса)"]
        BS["💰 BalanceService<br/>(запросы баланса)"]
        SPS["⭐ StarPurchaseService<br/>(покупка звезд)"]
        FS["💎 FragmentService<br/>(Fragment API)"]
    end

    subgraph "🎯 Handlers Layer"
        PH["💳 PaymentHandler<br/>(обработка платежей)"]
        BalH["💰 BalanceHandler<br/>(запросы баланса)"]
        PuH["🛒 PurchaseHandler<br/>(покупки)"]
        MH["📨 MessageHandler<br/>(общее управление)"]
    end

    MF --> MT
    MF --> RM

    PS --> MF
    BS --> MF
    SPS --> MF
    FS --> MF

    PS --> PH
    BS --> BalH
    SPS --> PuH
    MH --> PS
    MH --> BS
    MH --> SPS

    PH --> MH
    BalH --> MH
    PuH --> MH
```

### Принципы интеграции

- **Единая точка форматирования**: Все сообщения проходят через MessageFormatter
- **Опциональная зависимость**: Services могут работать без MessageFormatter (fallback)
- **Консистентность интерфейса**: Единые шаблоны для всех типов сообщений
- **Отделение логики**: Форматирование отделено от бизнес-логики
- **Расширяемость**: Легкое добавление новых типов сообщений

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
    subgraph "⚙️ SERVICES LAYER (МОДУЛЬНАЯ ОРГАНИЗАЦИЯ)"
        subgraph "🗄️ cache/"
            UC["👤 UserCache<br/>(кеш пользователей)"]
            PC["💳 PaymentCache<br/>(кеш платежей)"]
            RLC["🚦 RateLimitCache<br/>(ограничения запросов)"]
            SC["📦 SessionCache<br/>(кеш сессий)"]
        end

        subgraph "💰 payment/"
            PS["💳 PaymentService<br/>(платежи Heleket)"]
            BS["💰 BalanceService<br/>(баланс + форматирование)"]
            SPS["⭐ StarPurchaseService<br/>(покупка звезд)"]
        end

        subgraph "🔗 webhooks/"
            WH["🔗 WebhookHandler<br/>(обработка вебхуков)"]
            WA["🌐 WebhookApp<br/>(FastAPI приложение)"]
        end

        subgraph "🏗️ infrastructure/"
            HS["❤️ HealthService<br/>(мониторинг)"]
            CB["🔄 CircuitBreaker<br/>(предохранитель)"]
            WS["🔌 WebSocketService<br/>(WebSocket)"]
            FCM["⚙️ FragmentCookieManager<br/>(куки Fragment)"]
        end

        subgraph "💎 fragment/"
            FS["💎 FragmentService<br/>(Fragment API)"]
        end
    end

    subgraph "🛠️ UTILS INTEGRATION"
        MF["📨 MessageFormatter<br/>(центральное форматирование)"]
        MT["📝 MessageTemplates<br/>(шаблоны)"]
    end

    PS --> CS
    BS --> CS
    SPS --> CS
    FS --> CS
    RLC --> CS

    PS --> UR
    BS --> BR
    SPS --> UR
    SPS --> BR
    FS --> SPS

    PS --> MF
    BS --> MF
    MF --> MT
```

#### Новые методы в BalanceService

```python
class BalanceService:
    def __init__(self, message_formatter: Optional[MessageFormatter] = None):
        self.message_formatter = message_formatter

    async def get_balance_with_formatting(self, user_id: int) -> str:
        """Получение баланса с форматированием через MessageFormatter"""
        balance = await self.get_balance(user_id)
        return self.message_formatter.format_balance_message(balance)

    async def get_transaction_history_formatted(self, user_id: int) -> str:
        """История транзакций с централизованным форматированием"""
        transactions = await self.get_transaction_history(user_id)
        return self.message_formatter.format_transaction_history(transactions)
```

#### Новые методы в PaymentService

```python
class PaymentService:
    def __init__(self, message_formatter: Optional[MessageFormatter] = None):
        self.message_formatter = message_formatter

    async def create_recharge_invoice_formatted(self, user_id: int, amount: float) -> str:
        """Создание счета на пополнение с форматированием"""
        invoice = await self.create_recharge_invoice(user_id, amount)
        return self.message_formatter.format_payment_invoice(invoice)

    async def get_payment_status_formatted(self, payment_id: str) -> str:
        """Статус платежа с централизованным форматированием"""
        status = await self.get_payment_status(payment_id)
        return self.message_formatter.format_payment_status(status)
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
    participant MF as 📨 MessageFormatter

    U->>TB: /recharge 100
    TB->>PS: create_recharge_invoice(user_id, 100)
    PS->>DB: create_transaction(pending)
    PS->>H: POST /create_invoice
    H-->>PS: invoice_url + uuid
    PS->>MF: format_payment_invoice(invoice_data)
    MF-->>PS: formatted_message
    PS->>C: cache_payment(uuid, user_id)
    PS-->>TB: formatted_message
    TB-->>U: 💳 Ссылка для оплаты

    Note over U,H: Пользователь оплачивает счет

    H->>WH: POST /webhook/heleket
    WH->>C: get_payment_info(uuid)
    WH->>DB: update_transaction(completed)
    WH->>DB: update_user_balance(+100)
    WH->>C: invalidate_user_cache(user_id)
    WH->>PS: get_payment_status_formatted(uuid)
    PS->>MF: format_payment_status(success)
    MF-->>PS: success_message
    PS-->>WH: success_message
    WH->>TB: notify_payment_success(user_id, success_message)
    TB->>U: ✅ Пополнение успешно! +100 💰
```

### Поток запроса баланса с централизованным форматированием

```mermaid
sequenceDiagram
    participant U as 👤 User
    participant TB as 🤖 Telegram Bot
    participant BalH as 💰 Balance Handler
    participant BS as 💰 Balance Service
    participant DB as 🗄️ Database
    participant C as 📦 Cache
    participant MF as 📨 MessageFormatter
    participant MT as 📝 MessageTemplates

    U->>TB: /balance
    TB->>BalH: handle_balance_request(user_id)
    BalH->>BS: get_balance_with_formatting(user_id)
    BS->>DB: get_user_balance(user_id)
    DB-->>BS: balance_data
    BS->>C: cache_balance(user_id, balance_data)
    BS->>MF: format_balance_message(balance_data)
    MF->>MT: get_balance_template()
    MT-->>MF: template_string
    MF-->>BS: formatted_balance
    BS-->>BalH: formatted_balance
    BalH-->>TB: formatted_balance
    TB-->>U: 💰 Ваш баланс: 150.00 TON

    Note over MF,MT: Централизованное форматирование обеспечивает<br/>консистентность всех сообщений
```

## 🛡️ Паттерны проектирования

### Centralized Formatting Pattern

```python
class MessageFormatter:
    """Централизованный класс для форматирования сообщений"""

    def __init__(self, message_templates: MessageTemplates):
        self.templates = message_templates

    def format_balance_message(self, balance: Dict[str, Any]) -> str:
        """Форматирование сообщения о балансе"""
        template = self.templates.BALANCE_MESSAGE
        return template.format(
            amount=balance['amount'],
            currency=balance['currency'],
            emoji=self.templates.EMOJI['money']
        )

    def format_payment_status(self, status: str, amount: float = None) -> str:
        """Форматирование статуса платежа"""
        templates = {
            'success': self.templates.PAYMENT_SUCCESS,
            'pending': self.templates.PAYMENT_PENDING,
            'failed': self.templates.PAYMENT_FAILED
        }
        template = templates.get(status, self.templates.PAYMENT_UNKNOWN)
        return template.format(
            amount=amount or 0,
            emoji=self.templates.EMOJI['success']
        )

class BalanceService:
    """Сервис с опциональной интеграцией MessageFormatter"""

    def __init__(self, message_formatter: Optional[MessageFormatter] = None):
        self.message_formatter = message_formatter

    async def get_balance_with_formatting(self, user_id: int) -> str:
        """Получение баланса с форматированием (опционально)"""
        balance = await self.get_balance(user_id)

        if self.message_formatter:
            return self.message_formatter.format_balance_message(balance)

        # Fallback к простому форматированию
        return f"Баланс: {balance['amount']} {balance['currency']}"

    async def get_balance_raw(self, user_id: int) -> Dict[str, Any]:
        """Получение баланса без форматирования"""
        return await self.get_balance(user_id)
```

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
### Cloudflare Интеграция

#### Компоненты архитектуры

```mermaid
graph TB
    subgraph "Cloudflare Layer"
        CF_T[Cloudflare Tunnel]
        CF_W[Cloudflare Workers]
        CF_DNS[Cloudflare DNS]
    end
    
    subgraph "Application Layer"
        NGINX[Load Balancer]
        APP[Telegram Bot App]
        WEBHOOK[Webhook Service]
    end
    
    subgraph "External Services"
        TG[Telegram API]
        HELEKET[Heleket API]
        FRAGMENT[Fragment API]
    end
    
    CF_DNS --> CF_T
    CF_T --> NGINX
    CF_T --> CF_W
    
    NGINX --> APP
    NGINX --> WEBHOOK
    
    APP --> TG
    WEBHOOK --> HELEKET
    APP --> FRAGMENT
    
    CF_W --> APP
```

#### Архитектура туннеля

```mermaid
graph LR
    subgraph "Cloudflare Network"
        CF_EDGE[Cloudflare Edge]
        CF_NETWORK[Cloudflare Network]
    end
    
    subgraph "Tunnel Components"
        CF_AGENT[cloudflared Agent]
        CF_TUNNEL[Argo Tunnel]
        CF_ORIGIN[Origin Server]
    end
    
    CF_EDGE --> CF_AGENT
    CF_AGENT --> CF_TUNNEL
    CF_TUNNEL --> CF_NETWORK
    CF_NETWORK --> CF_ORIGIN
```

#### Настройка безопасности

```mermaid
graph TD
    subgraph "Security Layers"
        CF_SSL[SSL/TLS Termination]
        CF_WAF[Web Application Firewall]
        CF_DDOS[DDoS Protection]
        CF_RATE[Rate Limiting]
    end
    
    subgraph "Application Security"
        APP_AUTH[Authentication]
        APP_VALID[Input Validation]
        APP_RATE[Application Rate Limiting]
    end
    
    CF_SSL --> CF_WAF
    CF_WAF --> CF_DDOS
    CF_DDOS --> CF_RATE
    
    CF_RATE --> APP_AUTH
    APP_AUTH --> APP_VALID
    APP_VALID --> APP_RATE
```
### BaseCache Pattern

```mermaid
graph TB
    subgraph "BaseCache Architecture"
        BC[BaseCache<br/>Абстрактный базовый класс]
        BC --> LCache[LocalCache<br/>Локальное кеширование]
        BC --> RClient[RedisClient<br/>Redis взаимодействие]
        BC --> Serial[CacheSerializer<br/>Сериализация данных]
        BC --> Except[CacheExceptions<br/>Обработка ошибок]

        LCache --> LRU[LRU Eviction<br/>Алгоритм вытеснения]
        LCache --> TTL[TTL Management<br/>Управление временем жизни]

        RClient --> Circuit[Circuit Breaker<br/>Предохранитель]
        RClient --> Retry[Retry Logic<br/>Повторные попытки]
        RClient --> Health[Health Check<br/>Проверка здоровья]
    end

    subgraph "Cache Implementations"
        SC[SessionCache<br/>Кеш сессий]
        UC[UserCache<br/>Кеш пользователей]
        PC[PaymentCache<br/>Кеш платежей]
        RLC[RateLimitCache<br/>Ограничение запросов]

        SC --> BC
        UC --> BC
        PC --> BC
        RLC --> BC
    end

    subgraph "Graceful Degradation"
        BC --> GD[Graceful Degradation<br/>Graceful деградация]
        GD --> Local[Локальный кеш fallback]
        GD --> Error[Обработка ошибок]
        GD --> Metrics[Метрики производительности]
    end

    classDef abstract fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef component fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef feature fill:#e8f5e8,stroke:#2e7d32,stroke-width:2px

    class BC abstract
    class SC,UC,PC,RLC component
    class LCache,RClient,Serial,Except,GD feature
```

#### Принципы BaseCache

- **Единая архитектура**: Все сервисы кеширования наследуются от BaseCache
- **Унифицированные операции**: Стандартные методы get/set/delete/exists
- **Graceful degradation**: Автоматический fallback на локальный кеш
- **Метрики производительности**: Встроенный мониторинг hit/miss rate
- **Обработка ошибок**: Централизованная обработка Redis ошибок
- **Circuit Breaker**: Защита от cascade failures
- **Health checks**: Мониторинг здоровья компонентов

#### Преимущества BaseCache

```python
# Пример использования BaseCache
class MyCache(BaseCache):
    def __init__(self, redis_client, **kwargs):
        super().__init__(redis_client, **kwargs)
        self._cache_prefix = "my_service"

    async def get(self, key: str) -> Optional[Any]:
        return await self._get_from_redis(key)  # Унаследованный метод

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        return await self._set_in_redis(key, value, ttl)  # Унаследованный метод

    async def delete(self, key: str) -> bool:
        return await self._delete_from_redis(key)  # Унаследованный метод
```

### BalanceService Components Architecture

```mermaid
graph TD
    subgraph "BalanceService Architecture"
        BS[BalanceService<br/>Оркестратор]

        subgraph "Core Components"
            BM[BalanceManager<br/>Управление балансом]
            TM[TransactionManager<br/>Управление транзакциями]
            BF[BalanceFormatter<br/>Форматирование сообщений]
        end

        subgraph "Dependencies"
            BR[BalanceRepository<br/>Репозиторий баланса]
            UC[UserCache<br/>Кеш пользователей]
            MF[MessageFormatter<br/>Форматтер сообщений]
        end

        BS --> BM
        BS --> TM
        BS --> BF

        BM --> BR
        BM --> UC

        TM --> BR
        TM --> UC

        BF --> MF
    end

    subgraph "SOLID Principles"
        SRP["🔹 SRP<br/>Single Responsibility"]
        OCP["🔹 OCP<br/>Open/Closed"]
        LSP["🔹 LSP<br/>Liskov Substitution"]
        ISP["🔹 ISP<br/>Interface Segregation"]
        DIP["🔹 DIP<br/>Dependency Inversion"]

        BM --> SRP
        BS --> OCP
        BF --> LSP
        TM --> ISP
        BM --> DIP
        TM --> DIP
        BF --> DIP
    end

    classDef orchestrator fill:#e3f2fd,stroke:#1976d2,stroke-width:2px
    classDef component fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    classDef dependency fill:#e8f5e8,stroke:#388e3c,stroke-width:2px
    classDef principle fill:#fff3e0,stroke:#f57c00,stroke-width:2px

    class BS orchestrator
    class BM,TM,BF component
    class BR,UC,MF dependency
    class SRP,OCP,LSP,ISP,DIP principle
```

#### BalanceService Components

1. **BalanceManager** (129 строк)
   - Управление балансом пользователей
   - Cache-Aside паттерн для производительности
   - Проверка достаточности средств
   - Обновление баланса с инвалидацией кеша

2. **TransactionManager** (200 строк)
   - Полный жизненный цикл транзакций
   - Создание, завершение, отмена транзакций
   - Валидация транзакционных данных
   - Управление статусами транзакций

3. **BalanceFormatter** (250 строк)
   - Централизованное форматирование сообщений
   - Опциональная интеграция с MessageFormatter
   - Fallback сообщения при ошибках
   - Консистентность интерфейса пользователя

#### Преимущества модульной архитектуры

- **Тестируемость**: Каждый компонент можно тестировать отдельно
- **Поддерживаемость**: Изменения в одном компоненте не затрагивают другие
- **Расширяемость**: Легко добавлять новые функции в соответствующие компоненты
- **Читаемость**: Код организован логически, легче понимать ответственность
- **Переиспользование**: Компоненты могут использоваться другими сервисами

