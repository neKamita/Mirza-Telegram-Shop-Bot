# 🚀 Документация по развертыванию

## Обзор развертывания

Данный документ описывает процессы развертывания, CI/CD пайплайны и инфраструктуру для Telegram бота с системой платежей и Fragment интеграцией.

## 🏗️ Архитектура развертывания

```mermaid
graph TB
    subgraph "🌐 External Network"
        INET[Internet]
        TG_API[Telegram API]
        HELEKET[Heleket API]
        FRAGMENT[Fragment API]
    end

    subgraph "🔒 Cloudflare"
        CF[Cloudflare Tunnel]
        CF_SSL[SSL Termination]
        CF_DNS[DNS Management]
    end

    subgraph "🔒 DMZ Network"
        NGINX[nginx:reverse proxy]
    end

    subgraph "🏠 Internal Network (bot-network)"
        subgraph "Application Layer"
            APP[telegram-bot:app]
            WEBHOOK[webhook-service:uvicorn]
        end

        subgraph "Database Layer"
            PG[(PostgreSQL:17.5)]
            ALEMBIC[Alembic Migrations]
        end

        subgraph "Cache Layer"
            R1[redis-node-1:6379]
            R2[redis-node-2:6380]
            R3[redis-node-3:6381]
            RR1[redis-replica-1:6382]
            RR2[redis-replica-2:6383]
            RR3[redis-replica-3:6384]
        end

        subgraph "Fragment Integration"
            CHROME[Chrome Browser]
            COOKIES[Cookie Manager]
        end
    end

    INET --> CF
    CF --> NGINX
    TG_API --> CF
    HELEKET --> CF
    FRAGMENT --> CF

    NGINX --> APP
    NGINX --> WEBHOOK

    APP --> PG
    WEBHOOK --> PG
    ALEMBIC --> PG

    APP --> R1
    WEBHOOK --> R1

    R1 -.-> RR1
    R2 -.-> RR2
    R3 -.-> RR3

    APP --> CHROME
    CHROME --> FRAGMENT
    COOKIES --> CHROME
```

## 🐳 Docker архитектура

### Схема контейнеров

```mermaid
graph TB
    subgraph "🌐 External Network"
        INET[Internet]
        TG_API[Telegram API]
        HELEKET[Heleket API]
    end

    subgraph "🔒 DMZ Network"
        NGINX[nginx:latest]
    end

    subgraph "🏠 Internal Network (bot-network)"
        subgraph "Application Tier"
            APP[app:python3.11]
            WEBHOOK[webhook:python3.11]
        end

        subgraph "Database Tier"
            PG[db:postgresql:17.5]
        end

        subgraph "Cache Tier"
            R1[redis-node-1:redis:7]
            R2[redis-node-2:redis:7]
            R3[redis-node-3:redis:7]
            RR1[redis-replica-1:redis:7]
            RR2[redis-replica-2:redis:7]
            RR3[redis-replica-3:redis:7]
        end

        subgraph "Utilities"
            RC[redis-cluster-creator]
            RM[redis-cluster-monitor]
        end
    end

    INET --> NGINX
    TG_API --> NGINX
    HELEKET --> NGINX

    NGINX --> APP
    NGINX --> WEBHOOK

    APP --> PG
    WEBHOOK --> PG

    APP --> R1
    WEBHOOK --> R1

    R1 -.-> RR1
    R2 -.-> RR2
    R3 -.-> RR3

    RC -.-> R1
    RC -.-> R2
    RC -.-> R3

    RM -.-> R1
    RM -.-> R2
    RM -.-> R3
```

### Порты и сервисы

```mermaid
graph LR
    subgraph "🌐 External Ports"
        P80[":80 HTTP"]
        P443[":443 HTTPS"]
        P8081[":8081 WebSocket"]
    end

    subgraph "🔒 Internal Ports"
        P8000[":8000 Bot App"]
        P8001[":8001 Webhook"]
        P5433[":5433 PostgreSQL"]
        P7379[":7379 Redis-1"]
        P7380[":7380 Redis-2"]
        P7381[":7381 Redis-3"]
        P7382[":7382 Redis-R1"]
        P7383[":7383 Redis-R2"]
        P7384[":7384 Redis-R3"]
        P9090[":9090 Prometheus"]
        P3000[":3000 Grafana"]
    end

    P80 --> NGINX
    P443 --> NGINX
    P8081 --> NGINX

    NGINX --> P8000
    P8000 --> APP

    NGINX --> P8001
    P8001 --> WEBHOOK

    APP --> P5433
    WEBHOOK --> P5433

    APP --> P7379
    WEBHOOK --> P7379
```

## 🚀 Быстрое развертывание

### Предварительные требования

```bash
# Системные требования
- Docker Engine 20.10+
- Docker Compose 2.0+
- 4GB RAM минимум
- 2 CPU cores минимум
- 20GB свободного места

# Установка Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### Локальная разработка

#### 1. Клонирование репозитория

```bash
git clone https://github.com/your-org/Mirza-Telegram-Shop-Bot.git
cd Mirza-Telegram-Shop-Bot
```

#### 2. Настройка переменных окружения

```bash
cp .env.example .env
nano .env
```

**Обязательные переменные для разработки:**

```env
# Telegram Bot
TELEGRAM_TOKEN=your_bot_token_here

# Database (локальная PostgreSQL)
DATABASE_URL=postgresql://postgres:password@localhost:5433/telegram_bot

# Redis (одиночный узел для разработки)
REDIS_URL=redis://localhost:7379
REDIS_CLUSTER_ENABLED=false
REDIS_PASSWORD=your_redis_password

# SSL (самоподписанный для разработки)
SSL_CERT_PATH=./ssl/cert.pem
SSL_KEY_PATH=./ssl/key.pem

# Fragment API (опционально)
FRAGMENT_SEED_PHRASE=your_seed_phrase
FRAGMENT_COOKIES=your_cookies_json

# Webhook (для разработки localhost)
WEBHOOK_ENABLED=false
WEBHOOK_HOST=localhost
WEBHOOK_PORT=8001

# Environment
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG
```

#### 3. Генерация SSL сертификатов для разработки

```bash
# Создание директории для сертификатов
mkdir -p ssl

# Генерация самоподписанного сертификата
openssl req -x509 -newkey rsa:4096 -keyout ssl/key.pem -out ssl/cert.pem -days 365 -nodes \
  -subj "/C=RU/ST=Moscow/L=Moscow/O=Dev/OU=Dev/CN=localhost"

# Создание цепочки сертификатов
cp ssl/cert.pem ssl/chain.pem
```

#### 4. Запуск в режиме разработки

```bash
# Запуск только необходимых сервисов
docker-compose up -d db redis-node-1 app

# Просмотр логов
docker-compose logs -f app

# Остановка
docker-compose down
```

### Production развертывание

#### 1. Подготовка production сервера

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка необходимых пакетов
sudo apt install -y curl wget git ufw

# Настройка firewall
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

# Настройка системных параметров для Redis кластера
sudo sysctl vm.overcommit_memory=1
sudo sysctl vm.swappiness=10
sudo sysctl vm.max_map_count=262144

# Сохранение параметров
echo 'vm.overcommit_memory=1' | sudo tee -a /etc/sysctl.conf
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
echo 'vm.max_map_count=262144' | sudo tee -a /etc/sysctl.conf
```

#### 2. Настройка переменных окружения для production

```bash
# Копирование и редактирование
cp .env.example .env.production
nano .env.production
```

**Production переменные окружения:**

```env
# Environment
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO

# Database - Neon PostgreSQL
DATABASE_URL=postgresql+asyncpg://neondb_owner:password@ep-misty-fire-a1t4znca-pooler.ap-southeast-1.aws.neon.tech/neondb?ssl=require

# Redis Cluster
REDIS_CLUSTER_ENABLED=true
REDIS_CLUSTER_NODES=redis-node-1:7379,redis-node-2:7380,redis-node-3:7381
REDIS_PASSWORD=secure_redis_password_here

# SSL Certificates
SSL_CERT_PATH=/app/ssl/cert.pem
SSL_KEY_PATH=/app/ssl/key.pem

# Cloudflare Tunnel
CLOUDFLARE_TUNNEL_TOKEN=your_tunnel_token
PRODUCTION_DOMAIN=your-domain.com
ENABLE_HTTPS_REDIRECT=true

# Fragment API
FRAGMENT_SEED_PHRASE=your_production_seed_phrase
FRAGMENT_COOKIES=your_production_cookies
FRAGMENT_AUTO_COOKIE_REFRESH=true
FRAGMENT_COOKIE_REFRESH_INTERVAL=1800

# Payment System
MERCHANT_UUID=your_merchant_uuid
API_KEY=your_api_key

# Webhook
WEBHOOK_ENABLED=true
WEBHOOK_HOST=your-domain.com
WEBHOOK_PORT=443
WEBHOOK_SECRET=secure_webhook_secret

# Telegram Bot
TELEGRAM_TOKEN=your_bot_token

# Rate Limiting (production values)
RATE_LIMIT_API=10
RATE_LIMIT_PAYMENT=2
RATE_LIMIT_USER_MESSAGES=30
RATE_LIMIT_GLOBAL_MESSAGES=1000
```

#### 3. Получение SSL сертификатов

**Вариант 1: Let's Encrypt (рекомендуется)**

```bash
# Установка certbot
sudo apt install -y certbot

# Получение wildcard сертификата (если есть домен)
sudo certbot certonly --manual --preferred-challenges=dns -d your-domain.com -d *.your-domain.com

# Копирование сертификатов
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem ssl/chain.pem
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem ssl/key.pem
sudo cp /etc/letsencrypt/live/your-domain.com/cert.pem ssl/cert.pem

# Настройка прав
sudo chown 1000:1000 ssl/*
```

**Вариант 2: Из существующих сертификатов**

```bash
# Копирование ваших сертификатов
cp /path/to/your/cert.pem ssl/cert.pem
cp /path/to/your/key.pem ssl/key.pem
cp /path/to/your/chain.pem ssl/chain.pem

# Настройка прав
chown 1000:1000 ssl/*
```

#### 4. Запуск production развертывания

```bash
# Копирование production переменных
cp .env.production .env

# Запуск всех сервисов
docker-compose up -d

# Проверка статуса
docker-compose ps

# Просмотр логов
docker-compose logs -f

# Проверка здоровья кластера Redis
docker-compose exec redis-node-1 redis-cli -p 7379 -a $REDIS_PASSWORD cluster nodes
```

## 🔄 CI/CD Pipeline

### GitOps процесс

```mermaid
gitGraph
    commit id: "Initial"
    branch develop
    checkout develop
    commit id: "Feature A"
    commit id: "Feature B"
    checkout main
    merge develop
    commit id: "Release v1.0"
    branch hotfix
    checkout hotfix
    commit id: "Critical Fix"
    checkout main
    merge hotfix
    commit id: "Release v1.0.1"
```

### Deployment Pipeline

```mermaid
flowchart TD
    A[📝 Code Commit] --> B[🔍 Code Analysis]
    B --> C[🧪 Unit Tests]
    C --> D[🔨 Build Docker Images]
    D --> E[🔐 Security Scan]
    E --> F[📦 Push to Registry]

    F --> G{🌿 Branch?}
    G -->|develop| H[🧪 Deploy to Staging]
    G -->|main| I[🚀 Deploy to Production]

    H --> J[🔍 Integration Tests]
    J --> K[🧪 End-to-End Tests]
    K --> L[✅ Staging Validation]

    I --> M[🔄 Blue-Green Deployment]
    M --> N[🔍 Health Checks]
    N --> O[📊 Monitoring]
    O --> P[✅ Production Validation]

    L --> Q[📧 Notification]
    P --> Q

    Q --> R[🚀 Rollback if needed]
    R --> S[🔄 Redeploy]
```

### GitHub Actions CI/CD

#### `.github/workflows/deploy.yml`

```yaml
name: Deploy

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
    - name: Run tests
      run: |
        python -m pytest tests/ -v --cov=.
    - name: Security scan
      uses: github/super-linter@v5
      env:
        DEFAULT_BRANCH: main
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
    - name: Checkout
      uses: actions/checkout@v4
    - name: Log in to Container Registry
      uses: docker/login-action@v3
      with:
        registry: ${{ env.REGISTRY }}
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}
    - name: Extract metadata
      id: meta
      uses: docker/metadata-action@v5
      with:
        images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
    - name: Build and push Docker image
      uses: docker/build-push-action@v5
      with:
        context: .
        push: true
        tags: ${{ steps.meta.outputs.tags }}
        labels: ${{ steps.meta.outputs.labels }}

  deploy-staging:
    needs: build
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/develop'
    steps:
    - name: Deploy to staging
      run: |
        echo "Deploy to staging server"
        # Add your deployment commands here

  deploy-production:
    needs: build
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
    - name: Deploy to production
      run: |
        echo "Deploy to production server"
        # Add your deployment commands here
```

## 🗄️ Миграции базы данных (Alembic)

### Структура миграций

```
alembic/
├── alembic.ini
├── env.py
├── script.py.mako
└── versions/
    ├── 5751e048eb6f_add_balance_and_transaction_tables.py
    ├── dfbd1f676ffe_add_is_premium_field_to_users_table.py
    └── f0809b2c3fbc_remove_is_premium_field_from_users_table.py
```

### Работа с миграциями

#### Создание новой миграции

```bash
# Активация виртуального окружения (если используется)
source venv/bin/activate

# Генерация миграции на основе изменений в моделях
alembic revision --autogenerate -m "Add new feature"

# Применение миграций
alembic upgrade head
```

#### В Docker контейнере

```bash
# Создание миграции
docker-compose run --rm app alembic revision --autogenerate -m "Add new table"

# Применение миграций
docker-compose run --rm app alembic upgrade head

# Проверка текущего состояния
docker-compose run --rm app alembic current

# Просмотр истории миграций
docker-compose run --rm app alembic history
```

#### Production миграции

```bash
# Резервное копирование перед миграцией
docker-compose exec db pg_dump -U postgres telegram_bot > backup_$(date +%Y%m%d_%H%M%S).sql

# Применение миграций
docker-compose run --rm app alembic upgrade head

# Проверка после миграции
docker-compose run --rm app alembic current
```

### Конфигурация Alembic

**alembic.ini:**
```ini
[alembic]
script_location = alembic
sqlalchemy.url = postgresql+asyncpg://user:password@host:port/database

[loggers]
keys = root,sqlalchemy,alembic

[logger_root]
level = WARNING
handlers = console

[logger_alembic]
level = INFO
handlers =
```

## 📊 Мониторинг и логирование

### Архитектура мониторинга

```mermaid
graph TB
    subgraph "📊 Monitoring Stack"
        PROMETHEUS[Prometheus]
        GRAFANA[Grafana]
        NODE_EXPORTER[Node Exporter]
        REDIS_EXPORTER[Redis Exporter]
        POSTGRES_EXPORTER[PostgreSQL Exporter]
    end

    subgraph "📈 Application Metrics"
        APP[Bot Application]
        WEBHOOK[Webhook Service]
        NGINX[nginx]
    end

    subgraph "🚨 Alerting"
        ALERTMANAGER[Alertmanager]
        SLACK[Slack]
        EMAIL[Email]
        TELEGRAM[Telegram Bot]
    end

    APP --> PROMETHEUS
    WEBHOOK --> PROMETHEUS
    NGINX --> PROMETHEUS

    NODE_EXPORTER --> PROMETHEUS
    REDIS_EXPORTER --> PROMETHEUS
    POSTGRES_EXPORTER --> PROMETHEUS

    PROMETHEUS --> GRAFANA
    PROMETHEUS --> ALERTMANAGER

    ALERTMANAGER --> SLACK
    ALERTMANAGER --> EMAIL
    ALERTMANAGER --> TELEGRAM
```

### Настройка мониторинга

#### Docker Compose для мониторинга

```yaml
version: '3.8'
services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
    networks:
      - monitoring

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana_data:/var/lib/grafana
    networks:
      - monitoring

  node-exporter:
    image: prom/node-exporter:latest
    ports:
      - "9100:9100"
    networks:
      - monitoring

  redis-exporter:
    image: oliver006/redis_exporter:latest
    ports:
      - "9121:9121"
    environment:
      - REDIS_ADDR=redis://redis-node-1:7379
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    networks:
      - monitoring
```

#### Ключевые метрики для отслеживания

```prometheus
# Application Metrics
- Количество активных пользователей
- Количество обработанных сообщений
- Время отклика API
- Количество ошибок платежей
- Использование Fragment API

# System Metrics
- CPU usage всех контейнеров
- Memory usage
- Disk I/O
- Network I/O

# Redis Cluster Metrics
- Количество подключений
- Использование памяти
- Количество операций в секунду
- Статус кластера

# Database Metrics
- Количество активных подключений
- Время выполнения запросов
- Размер базы данных
- Количество deadlock'ов
```

### Логирование

#### Структура логов

```
logs/
├── app.log              # Основное логирование приложения
├── webhook.log          # Логи webhook сервиса
├── nginx_access.log     # Доступ к nginx
├── nginx_error.log      # Ошибки nginx
├── redis_cluster.log    # Логи Redis кластера
├── fragment.log         # Логи Fragment интеграции
└── cloudflared.log      # Логи Cloudflare tunnel
```

#### Конфигурация логирования

**Логирование приложения:**
```python
import logging
from logging.handlers import RotatingFileHandler

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(
            'logs/app.log',
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        ),
        logging.StreamHandler()
    ]
)
```

#### Централизованное логирование

```bash
# Использование ELK стека для продакшена
docker run -d --name elasticsearch -p 9200:9200 -p 9300:9300 elasticsearch:7.10.0
docker run -d --name logstash -p 5044:5044 logstash:7.10.0
docker run -d --name kibana -p 5601:5601 kibana:7.10.0

# Конфигурация Filebeat для сбора логов
filebeat.modules:
- module: docker
  containers:
    ids:
      - '*'
    path: /var/lib/docker/containers
    json.keys_under_root: true
    json.overwrite_keys: true

output.elasticsearch:
  hosts: ["elasticsearch:9200"]
```

## 🔄 Стратегии развертывания

### Blue-Green Deployment

```mermaid
sequenceDiagram
    participant LB as Load Balancer
    participant BLUE as Blue Environment
    participant GREEN as Green Environment
    participant MON as Monitoring

    Note over BLUE: Current Production
    Note over GREEN: Idle

    LB->>BLUE: 100% Traffic

    Note over GREEN: Deploy New Version
    GREEN->>GREEN: Health Checks
    GREEN->>MON: Metrics Validation

    LB->>GREEN: 10% Traffic (Canary)
    LB->>BLUE: 90% Traffic

    MON->>MON: Monitor Metrics

    alt Success
        LB->>GREEN: 100% Traffic
        Note over BLUE: Becomes Idle
    else Failure
        LB->>BLUE: 100% Traffic
        Note over GREEN: Rollback
    end
```

### Rolling Deployment

```mermaid
graph TD
    A[Start Deployment] --> B[Update Instance 1]
    B --> C{Health Check 1}
    C -->|✅ Pass| D[Update Instance 2]
    C -->|❌ Fail| E[Rollback Instance 1]

    D --> F{Health Check 2}
    F -->|✅ Pass| G[Update Instance 3]
    F -->|❌ Fail| H[Rollback Instance 2]

    G --> I{Health Check 3}
    I -->|✅ Pass| J[Deployment Complete]
    I -->|❌ Fail| K[Rollback Instance 3]

    E --> L[Deployment Failed]
    H --> L
    K --> L

    L --> M[Alert Team]
    J --> N[Update Load Balancer]
```

### Обновление без простоя

```bash
# Blue-Green deployment script
#!/bin/bash

# Переменные
BLUE_PORT=8000
GREEN_PORT=8001
LOAD_BALANCER=nginx

echo "=== Blue-Green Deployment Started ==="

# Проверка текущей активной среды
if curl -f http://localhost:$BLUE_PORT/health > /dev/null; then
    ACTIVE=blue
    INACTIVE=green
    ACTIVE_PORT=$BLUE_PORT
    INACTIVE_PORT=$GREEN_PORT
else
    ACTIVE=green
    INACTIVE=blue
    ACTIVE_PORT=$GREEN_PORT
    INACTIVE_PORT=$BLUE_PORT
fi

echo "Active environment: $ACTIVE (port $ACTIVE_PORT)"
echo "Inactive environment: $INACTIVE (port $INACTIVE_PORT)"

# Запуск новой версии в неактивной среде
echo "Deploying new version to $INACTIVE environment..."
docker-compose up -d app_$INACTIVE webhook_$INACTIVE

# Ожидание готовности
echo "Waiting for $INACTIVE environment to be ready..."
for i in {1..30}; do
    if curl -f http://localhost:$INACTIVE_PORT/health > /dev/null; then
        echo "$INACTIVE environment is ready!"
        break
    fi
    sleep 10
done

# Проверка здоровья новой среды
echo "Running health checks on $INACTIVE environment..."
# Добавить дополнительные проверки здесь

# Переключение трафика
echo "Switching traffic to $INACTIVE environment..."
# Обновление nginx upstream или load balancer configuration

# Финализация
echo "Traffic switched successfully!"
echo "Old $ACTIVE environment can be stopped or kept for rollback"

# Остановка старой среды через некоторое время
# docker-compose stop app_$ACTIVE webhook_$ACTIVE

echo "=== Blue-Green Deployment Completed ==="
```

## 📈 Масштабирование

### Горизонтальное масштабирование

```mermaid
graph TB
    subgraph "🔄 Load Balancer"
        LB[nginx Load Balancer]
    end

    subgraph "🚀 Application Instances"
        APP1[Bot App 1]
        APP2[Bot App 2]
        APP3[Bot App 3]
        APP4[Bot App 4]
    end

    subgraph "🗄️ Database Cluster"
        MASTER[(PostgreSQL Master)]
        SLAVE1[(PostgreSQL Slave 1)]
        SLAVE2[(PostgreSQL Slave 2)]
    end

    subgraph "🔴 Redis Cluster"
        R1[Redis Node 1]
        R2[Redis Node 2]
        R3[Redis Node 3]
        R4[Redis Node 4]
        R5[Redis Node 5]
        R6[Redis Node 6]
    end

    LB --> APP1
    LB --> APP2
    LB --> APP3
    LB --> APP4

    APP1 --> MASTER
    APP2 --> MASTER
    APP3 --> MASTER
    APP4 --> MASTER

    MASTER --> SLAVE1
    MASTER --> SLAVE2

    APP1 --> R1
    APP2 --> R2
    APP3 --> R3
    APP4 --> R4
```

### Настройка масштабирования

#### Docker Swarm режим

```bash
# Инициализация Swarm
docker swarm init

# Создание overlay сети
docker network create --driver overlay bot-network

# Развертывание стека
docker stack deploy -c docker-compose.swarm.yml telegram-bot

# Масштабирование сервисов
docker service scale telegram-bot_app=3
docker service scale telegram-bot_webhook=2

# Проверка статуса
docker service ls
docker service ps telegram-bot_app
```

#### Kubernetes развертывание

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: telegram-bot
spec:
  replicas: 3
  selector:
    matchLabels:
      app: telegram-bot
  template:
    metadata:
      labels:
        app: telegram-bot
    spec:
      containers:
      - name: telegram-bot
        image: telegram-bot:latest
        env:
        - name: DATABASE_URL
          value: "postgresql://..."
        - name: REDIS_URL
          value: "redis://..."
        ports:
        - containerPort: 8000
        resources:
          limits:
            cpu: 500m
            memory: 512Mi
          requests:
            cpu: 250m
            memory: 256Mi
---
apiVersion: v1
kind: Service
metadata:
  name: telegram-bot-service
spec:
  selector:
    app: telegram-bot
  ports:
    - port: 80
      targetPort: 8000
  type: LoadBalancer
```

### Автомасштабирование

#### На основе CPU/Memory

```yaml
# HorizontalPodAutoscaler для Kubernetes
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: telegram-bot-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: telegram-bot
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

#### На основе кастомных метрик

```yaml
# Автомасштабирование на основе количества сообщений
metrics:
- type: Pods
    pods:
      metric:
        name: telegram_messages_per_second
      target:
        type: AverageValue
        averageValue: 100
```

## 🔐 Безопасность

### Security Pipeline

```mermaid
flowchart TD
    A[📝 Code Commit] --> B[🔍 SAST Scan]
    B --> C[📦 Build Image]
    C --> D[🔐 Image Scan]
    D --> E[🧪 Security Tests]
    E --> F[📋 Compliance Check]
    F --> G[🚀 Deploy]

    G --> H[🔍 DAST Scan]
    H --> I[🛡️ Runtime Security]
    I --> J[📊 Security Monitoring]

    B -->|❌ Vulnerabilities| K[🚫 Block Deployment]
    D -->|❌ Critical Issues| K
    E -->|❌ Test Failures| K
    F -->|❌ Non-Compliant| K

    K --> L[📧 Security Team Notification]
    L --> M[🔧 Fix Issues]
    M --> A
```

### Защита инфраструктуры

#### Network Security

```bash
# Настройка firewall
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80
sudo ufw allow 443
sudo ufw --force enable

# Docker security
docker run --security-opt no-new-privileges \
           --cap-drop ALL \
           --cap-add NET_BIND_SERVICE \
           --read-only \
           --tmpfs /tmp \
           telegram-bot:latest
```

#### SSL/TLS конфигурация

```nginx
# Modern SSL configuration
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:...;
ssl_prefer_server_ciphers off;
ssl_session_cache shared:SSL:50m;
ssl_session_timeout 1d;

# Security headers
add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
```

#### Secrets Management

```bash
# Использование Docker secrets
echo "db_password" | docker secret create db_password -
echo "redis_password" | docker secret create redis_password -
echo "telegram_token" | docker secret create telegram_token -

# В docker-compose.yml
version: '3.8'
services:
  app:
    secrets:
      - db_password
      - redis_password
      - telegram_token
```

#### Rate Limiting и DDoS защита

```nginx
# Rate limiting zones
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=webhook:10m rate=30r/m;
limit_conn_zone $binary_remote_addr zone=conn_limit:10m;

# DDoS protection
limit_req zone=api burst=20 nodelay;
limit_req zone=webhook burst=10 nodelay;
limit_conn conn_limit 10;

# Whitelist для админов
geo $admin {
    default 0;
    192.168.1.0/24 1;  # Админская сеть
}

# Блокировка подозрительного трафика
if ($http_user_agent ~* "bad_bot") {
    return 403;
}
```

## 💾 Резервное копирование

### Стратегия резервного копирования

```mermaid
graph TB
    subgraph "🗄️ Database Backup"
        PG_MASTER[(PostgreSQL Master)]
        PG_BACKUP[Backup Container]
        S3[(AWS S3 / MinIO)]
    end

    subgraph "🔴 Redis Backup"
        REDIS_CLUSTER[Redis Cluster]
        REDIS_BACKUP[Redis Backup Script]
        S3_REDIS[(S3 Redis Backups)]
    end

    subgraph "📁 Configuration Backup"
        CONFIGS[Configuration Files]
        GIT[(Git Repository)]
        VAULT[(HashiCorp Vault)]
    end

    subgraph "📊 Monitoring"
        MONITORING[Backup Monitoring]
        ALERTS[Alert System]
    end

    PG_MASTER --> PG_BACKUP
    PG_BACKUP --> S3

    REDIS_CLUSTER --> REDIS_BACKUP
    REDIS_BACKUP --> S3_REDIS

    CONFIGS --> GIT
    CONFIGS --> VAULT

    S3 --> MONITORING
    S3_REDIS --> MONITORING
    GIT --> MONITORING
    VAULT --> MONITORING

    MONITORING --> ALERTS
```

### Настройка резервного копирования

#### PostgreSQL Backup

```bash
# Создание скрипта резервного копирования
cat > backup-postgres.sh << 'EOF'
#!/bin/bash

# Переменные
BACKUP_DIR="/opt/backups/postgres"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="telegram_bot_$DATE.sql.gz"
S3_BUCKET="s3://telegram-bot-backups/postgres/"

# Создание директории
mkdir -p $BACKUP_DIR

# Резервное копирование
docker-compose exec -T db pg_dump -U postgres telegram_bot | gzip > $BACKUP_DIR/$BACKUP_NAME

# Загрузка в S3
aws s3 cp $BACKUP_DIR/$BACKUP_NAME $S3_BUCKET

# Очистка старых бэкапов (оставляем последние 7 дней)
find $BACKUP_DIR -name "*.sql.gz" -mtime +7 -delete

# Логирование
echo "$(date) - PostgreSQL backup completed: $BACKUP_NAME" >> /var/log/backup.log
EOF

# Настройка cron
echo "0 2 * * * /opt/scripts/backup-postgres.sh" | crontab -
```

#### Redis Backup

```bash
# Скрипт резервного копирования Redis кластера
cat > backup-redis.sh << 'EOF'
#!/bin/bash

BACKUP_DIR="/opt/backups/redis"
DATE=$(date +%Y%m%d_%H%M%S)
S3_BUCKET="s3://telegram-bot-backups/redis/"

mkdir -p $BACKUP_DIR

# Резервное копирование каждого узла Redis
for i in {1..6}; do
    NODE="redis-node-$i"
    if [ $i -gt 3 ]; then
        NODE="redis-replica-$((i-3))"
    fi

    echo "Backing up $NODE..."
    docker-compose exec $NODE redis-cli -a $REDIS_PASSWORD SAVE

    # Копирование RDB файла
    docker cp telegram-bot_$NODE:/data/dump.rdb $BACKUP_DIR/${NODE}_$DATE.rdb

    # Сжатие и загрузка в S3
    gzip $BACKUP_DIR/${NODE}_$DATE.rdb
    aws s3 cp $BACKUP_DIR/${NODE}_$DATE.rdb.gz $S3_BUCKET
done

# Очистка
find $BACKUP_DIR -name "*.rdb.gz" -mtime +7 -delete

echo "$(date) - Redis cluster backup completed" >> /var/log/backup.log
EOF

# Настройка cron
echo "30 2 * * * /opt/scripts/backup-redis.sh" | crontab -
```

#### Автоматизированное тестирование восстановления

```bash
# Скрипт тестирования восстановления
cat > test-restore.sh << 'EOF'
#!/bin/bash

echo "=== Testing Backup Restore ==="

# Тестирование PostgreSQL
echo "Testing PostgreSQL restore..."
LATEST_BACKUP=$(aws s3 ls s3://telegram-bot-backups/postgres/ | sort | tail -n 1 | awk '{print $4}')
aws s3 cp s3://telegram-bot-backups/postgres/$LATEST_BACKUP /tmp/test_restore.sql.gz
gunzip /tmp/test_restore.sql.gz

# Создание тестовой базы
docker-compose exec db createdb -U postgres test_restore
docker-compose exec -T db psql -U postgres test_restore < /tmp/test_restore.sql

# Проверка
docker-compose exec db psql -U postgres test_restore -c "SELECT COUNT(*) FROM users;"

echo "PostgreSQL restore test completed"

# Тестирование Redis
echo "Testing Redis restore..."
LATEST_REDIS=$(aws s3 ls s3://telegram-bot-backups/redis/ | grep redis-node-1 | sort | tail -n 1 | awk '{print $4}')
aws s3 cp s3://telegram-bot-backups/redis/$LATEST_REDIS /tmp/test_redis.rdb.gz
gunzip /tmp/test_redis.rdb.gz

# Запуск тестового Redis
docker run -d --name test-redis -p 6380:6379 -v /tmp/test_redis.rdb:/data/dump.rdb redis:7 redis-server /etc/redis/redis.conf
sleep 5
docker exec test-redis redis-cli ping
docker stop test-redis && docker rm test-redis

echo "Redis restore test completed"
echo "=== Restore Tests Completed ==="
EOF
```

## 🔄 Обновление без простоя

### Zero-Downtime Deployment

```mermaid
sequenceDiagram
    participant LB as Load Balancer
    participant OLD as Old Version
    participant NEW as New Version
    participant DB as Database
    participant MON as Monitoring

    LB->>OLD: 100% Traffic
    OLD->>DB: Active Connections

    Note over NEW: Deploy New Version
    NEW->>NEW: Health Checks
    NEW->>DB: Test Connections

    LB->>NEW: 5% Traffic (Canary)
    LB->>OLD: 95% Traffic

    MON->>MON: Monitor Error Rates
    MON->>MON: Monitor Performance

    alt Success Metrics
        LB->>NEW: 25% Traffic
        LB->>OLD: 75% Traffic

        MON->>MON: Continue Monitoring

        LB->>NEW: 50% Traffic
        LB->>OLD: 50% Traffic

        LB->>NEW: 100% Traffic
        Note over OLD: Graceful Shutdown
    else Poor Metrics
        LB->>OLD: 100% Traffic
        Note over NEW: Rollback
    end
```

### Практическая реализация

```bash
# Скрипт zero-downtime deployment
#!/bin/bash

set -e

echo "=== Zero-Downtime Deployment Started ==="

# Переменные
APP_NAME=telegram-bot
OLD_VERSION=$(docker-compose ps app | grep app | awk '{print $2}' | cut -d: -f2)
NEW_VERSION=$(git rev-parse --short HEAD)

echo "Current version: $OLD_VERSION"
echo "New version: $NEW_VERSION"

# Создание нового образа
echo "Building new image..."
docker build -t $APP_NAME:$NEW_VERSION .

# Запуск новой версии рядом со старой
echo "Starting new version..."
docker run -d --name $APP_NAME-new-$NEW_VERSION \
  --network $APP_NAME \
  -e DATABASE_URL=$DATABASE_URL \
  -e REDIS_URL=$REDIS_URL \
  -p 8001:8000 \
  $APP_NAME:$NEW_VERSION

# Ожидание готовности
echo "Waiting for new version to be ready..."
for i in {1..30}; do
    if curl -f http://localhost:8001/health > /dev/null; then
        echo "New version is ready!"
        break
    fi
    sleep 5
done

# Постепенное переключение трафика (если используется load balancer)
echo "Gradually switching traffic..."

# Для nginx с upstream
# nginx -s reload  # Перезагрузка конфигурации

# Для Docker Swarm
# docker service update --image $APP_NAME:$NEW_VERSION $APP_NAME

# Мониторинг в течение 5 минут
echo "Monitoring for 5 minutes..."
sleep 300

# Проверка метрик
ERROR_RATE=$(curl -s http://localhost:8001/metrics | grep error_rate | cut -d' ' -f2)
RESPONSE_TIME=$(curl -s http://localhost:8001/metrics | grep response_time | cut -d' ' -f2)

if (( $(echo "$ERROR_RATE > 0.05" | bc -l) )) || (( $(echo "$RESPONSE_TIME > 2.0" | bc -l) )); then
    echo "Poor metrics detected, rolling back..."
    docker stop $APP_NAME-new-$NEW_VERSION
    docker rm $APP_NAME-new-$NEW_VERSION
    exit 1
fi

# Полное переключение
echo "Switching all traffic to new version..."
# Обновление load balancer configuration

# Остановка старой версии
echo "Stopping old version..."
docker-compose stop app
docker-compose rm -f app

# Переименование нового контейнера
docker rename $APP_NAME-new-$NEW_VERSION $APP_NAME-app

# Обновление docker-compose.yml с новой версией
sed -i "s/$OLD_VERSION/$NEW_VERSION/g" docker-compose.yml

echo "=== Zero-Downtime Deployment Completed ==="
```

### Rollback стратегия

```bash
# Скрипт rollback
#!/bin/bash

echo "=== Rollback Started ==="

# Получение предыдущей версии
PREVIOUS_VERSION=$(docker images $APP_NAME --format "{{.Repository}}:{{.Tag}}" | sed -n 2p)

if [ -z "$PREVIOUS_VERSION" ]; then
    echo "No previous version found!"
    exit 1
fi

echo "Rolling back to: $PREVIOUS_VERSION"

# Запуск предыдущей версии
docker run -d --name $APP_NAME-rollback \
  --network $APP_NAME \
  -e DATABASE_URL=$DATABASE_URL \
  -e REDIS_URL=$REDIS_URL \
  -p 8002:8000 \
  $PREVIOUS_VERSION

# Переключение трафика обратно
echo "Switching traffic back..."
# Обновление load balancer

# Остановка проблемной версии
docker-compose stop app
docker-compose rm -f app

# Переименование rollback контейнера
docker rename $APP_NAME-rollback $APP_NAME-app

echo "=== Rollback Completed ==="
```

## 🔧 Диагностика и устранение неисправностей

### Общие проблемы и решения

#### Redis кластер не формируется

```bash
# Проверка состояния узлов
docker-compose exec redis-node-1 redis-cli -p 7379 -a $REDIS_PASSWORD cluster nodes

# Пересоздание кластера
docker-compose down
docker volume rm telegram-bot_redis_node_1_data telegram-bot_redis_node_2_data telegram-bot_redis_node_3_data
docker-compose up -d redis-node-1 redis-node-2 redis-node-3 redis-replica-1 redis-replica-2 redis-replica-3
docker-compose exec redis-cluster-creator bash

# Ручное создание кластера
redis-cli --cluster create redis-node-1:7379 redis-node-2:7380 redis-node-3:7381 redis-replica-1:7382 redis-replica-2:7383 redis-replica-3:7384 --cluster-replicas 1 -a $REDIS_PASSWORD
```

#### Приложение не может подключиться к базе данных

```bash
# Проверка подключения
docker-compose exec app python -c "import asyncio; from repositories.user_repository import UserRepository; import os; repo = UserRepository(os.getenv('DATABASE_URL')); asyncio.run(repo.create_tables())"

# Проверка логов базы данных
docker-compose logs db

# Проверка переменных окружения
docker-compose exec app env | grep DATABASE

# Тестирование подключения вручную
docker-compose exec db psql -U postgres -d telegram_bot -c "SELECT version();"
```

#### Cloudflare tunnel не работает

```bash
# Проверка состояния tunnel
docker-compose logs cloudflared

# Перезапуск tunnel
docker-compose restart cloudflared

# Проверка credentials
docker-compose exec cloudflared cloudflared tunnel list

# Ручное тестирование
docker-compose exec cloudflared cloudflared tunnel ping telegram-bot-tunnel
```

#### Высокое потребление памяти

```bash
# Проверка потребления памяти контейнерами
docker stats

# Очистка неиспользуемых ресурсов
docker system prune -f

# Проверка Redis памяти
docker-compose exec redis-node-1 redis-cli -a $REDIS_PASSWORD info memory

# Оптимизация Redis
docker-compose exec redis-node-1 redis-cli -a $REDIS_PASSWORD config set maxmemory 1gb
docker-compose exec redis-node-1 redis-cli -a $REDIS_PASSWORD config set maxmemory-policy allkeys-lru
```

### Мониторинг производительности

```bash
# Тестирование производительности API
ab -n 1000 -c 10 http://localhost:8080/health

# Тестирование Redis производительности
docker-compose exec redis-node-1 redis-cli -a $REDIS_PASSWORD --eval perf_test.lua

# Мониторинг сетевых подключений
netstat -tunlp | grep :8000

# Проверка дискового пространства
df -h
docker system df
```

### Логи и отладка

```bash
# Просмотр логов всех сервисов
docker-compose logs -f

# Просмотр логов конкретного сервиса
docker-compose logs -f app

# Поиск ошибок в логах
docker-compose logs | grep -i error

# Детальное логирование
docker-compose exec app tail -f /app/logs/app.log

# Сбор диагностической информации
docker system info
docker version
docker-compose version
uname -a
```

## 📋 Контрольный список развертывания

- [ ] **Подготовка инфраструктуры**
  - [ ] Сервер соответствует системным требованиям
  - [ ] Docker и Docker Compose установлены
  - [ ] Firewall настроен
  - [ ] Системные параметры оптимизированы

- [ ] **Безопасность**
  - [ ] SSL сертификаты получены и установлены
  - [ ] Переменные окружения настроены
  - [ ] Secrets не хранятся в коде
  - [ ] Firewall правила применены

- [ ] **Конфигурация**
  - [ ] `.env` файл настроен для целевой среды
  - [ ] Cloudflare tunnel настроен
  - [ ] Fragment API credentials настроены
  - [ ] Rate limiting параметры оптимизированы

- [ ] **База данных**
  - [ ] PostgreSQL развернута и доступна
  - [ ] Миграции Alembic применены
  - [ ] Резервное копирование настроено
  - [ ] Мониторинг подключений настроен

- [ ] **Redis кластер**
  - [ ] Все узлы запущены и здоровы
  - [ ] Кластер правильно сформирован
  - [ ] Пароль аутентификации настроен
  - [ ] Репликация работает корректно

- [ ] **Тестирование**
  - [ ] Приложение запускается без ошибок
  - [ ] API endpoints доступны
  - [ ] Webhook endpoints работают
  - [ ] Fragment интеграция функционирует

- [ ] **Мониторинг**
  - [ ] Метрики собираются
  - [ ] Логи записываются
  - [ ] Оповещения настроены
  - [ ] Dashboard доступен

- [ ] **Документация**
  - [ ] Runbook обновлен
  - [ ] Контакты поддержки указаны
  - [ ] Процедуры восстановления документированы
  - [ ] Изменения залогированы

## 📞 Поддержка и контакты

### Команды поддержки

```bash
# Быстрая диагностика
docker-compose ps                    # Статус всех сервисов
docker-compose logs -f --tail=100    # Последние 100 строк логов
docker stats                        # Использование ресурсов
docker system df                    # Использование диска

# Экстренная остановка
docker-compose down -v              # Остановка с удалением volumes
docker system prune -f              # Очистка неиспользуемых ресурсов

# Резервное копирование перед изменениями
docker-compose exec db pg_dump -U postgres telegram_bot > emergency_backup_$(date +%Y%m%d_%H%M%S).sql
```

### Контакты

- **Техническая поддержка:** @Mirza
- **Мониторинг алерты:** monitoring@your-domain.com
- **Безопасность:** security@your-domain.com
- **Документация:** https://github.com/your-org/Mirza-Telegram-Shop-Bot/wiki

---

**Эта документация обеспечивает надежное и безопасное развертывание системы в различных средах. Регулярно обновляйте документацию при внесении изменений в инфраструктуру.**
