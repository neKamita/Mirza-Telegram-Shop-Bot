# 🚀 Документация по развертыванию

## Обзор развертывания

Данный документ описывает процессы развертывания, CI/CD пайплайны и инфраструктуру для Telegram бота с системой платежей.

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
            PG[db:postgresql:15]
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
    end
    
    subgraph "🔒 Internal Ports"
        P8001[":8001 Webhook"]
        P5432[":5432 PostgreSQL"]
        P7379[":7379 Redis-1"]
        P7380[":7380 Redis-2"]
        P7381[":7381 Redis-3"]
        P9090[":9090 Prometheus"]
        P3000[":3000 Grafana"]
    end
    
    P80 --> NGINX
    P443 --> NGINX
    
    NGINX --> P8001
    P8001 --> WEBHOOK
    
    APP --> P5432
    WEBHOOK --> P5432
    
    APP --> P7379
    WEBHOOK --> P7379
    
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
    J --> K[📊 Performance Tests]
    K --> L[✅ Staging Validation]
    
    I --> M[🔄 Blue-Green Deployment]
    M --> N[🔍 Health Checks]
    N --> O[📈 Monitoring]
    O --> P[✅ Production Validation]
    
    L --> Q[📧 Notification]
    P --> Q
    
```

## 🌍 Среды развертывания

### Конфигурация сред

```mermaid
graph TB
    subgraph "🧪 Development Environment"
        DEV_APP[Bot App]
        DEV_DB[(SQLite)]
        DEV_REDIS[(Redis Single)]
    end
    
    subgraph "🔬 Staging Environment"
        STAGE_LB[Load Balancer]
        STAGE_APP1[Bot App 1]
        STAGE_APP2[Bot App 2]
        STAGE_DB[(PostgreSQL)]
        STAGE_REDIS[(Redis Cluster)]
    end
    
    subgraph "🚀 Production Environment"
        PROD_LB[Load Balancer + SSL]
        PROD_APP1[Bot App 1]
        PROD_APP2[Bot App 2]
        PROD_APP3[Bot App 3]
        PROD_DB_M[(PostgreSQL Master)]
        PROD_DB_S1[(PostgreSQL Slave 1)]
        PROD_DB_S2[(PostgreSQL Slave 2)]
        PROD_REDIS[(Redis HA Cluster)]
        PROD_MON[Monitoring Stack]
    end
    
    DEV_APP --> DEV_DB
    DEV_APP --> DEV_REDIS
    
    STAGE_LB --> STAGE_APP1
    STAGE_LB --> STAGE_APP2
    STAGE_APP1 --> STAGE_DB
    STAGE_APP2 --> STAGE_DB
    STAGE_APP1 --> STAGE_REDIS
    STAGE_APP2 --> STAGE_REDIS
    
    PROD_LB --> PROD_APP1
    PROD_LB --> PROD_APP2
    PROD_LB --> PROD_APP3
    PROD_APP1 --> PROD_DB_M
    PROD_APP2 --> PROD_DB_M
    PROD_APP3 --> PROD_DB_M
    PROD_DB_M --> PROD_DB_S1
    PROD_DB_M --> PROD_DB_S2
    PROD_APP1 --> PROD_REDIS
    PROD_APP2 --> PROD_REDIS
    PROD_APP3 --> PROD_REDIS
    
```

## 🔧 Конфигурация инфраструктуры

### Terraform модули

```mermaid
graph TD
    subgraph "🏗️ Infrastructure as Code"
        TF[Terraform Main]
        
        subgraph "📦 Modules"
            VPC[VPC Module]
            EC2[EC2 Module]
            RDS[RDS Module]
            REDIS[ElastiCache Module]
            LB[Load Balancer Module]
            SEC[Security Groups Module]
        end
        
        subgraph "🔐 Secrets"
            VAULT[HashiCorp Vault]
            SSM[AWS SSM]
            K8S_SEC[Kubernetes Secrets]
        end
    end
    
    TF --> VPC
    TF --> EC2
    TF --> RDS
    TF --> REDIS
    TF --> LB
    TF --> SEC
    
    EC2 --> VAULT
    RDS --> SSM
    REDIS --> K8S_SEC
    
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
    
```

## 📊 Мониторинг развертывания

### Deployment Metrics

```mermaid
graph TB
    subgraph "📈 Deployment Metrics"
        DT[Deployment Time]
        SR[Success Rate]
        RB[Rollback Rate]
        MTTR[Mean Time To Recovery]
    end
    
    subgraph "🔍 Health Metrics"
        CPU[CPU Usage]
        MEM[Memory Usage]
        DISK[Disk Usage]
        NET[Network I/O]
    end
    
    subgraph "📊 Application Metrics"
        REQ[Request Rate]
        LAT[Latency]
        ERR[Error Rate]
        SAT[Saturation]
    end
    
    subgraph "🚨 Alerts"
        SLACK[Slack Notifications]
        EMAIL[Email Alerts]
        PAGER[PagerDuty]
    end
    
    DT --> SLACK
    SR --> EMAIL
    RB --> PAGER
    
    CPU --> SLACK
    MEM --> EMAIL
    ERR --> PAGER
    
```

## 🔐 Безопасность развертывания

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
    
```

---

**Документация по развертыванию обеспечивает надежное и безопасное развертывание системы в различных средах.**
### Cloudflare Интеграция

#### Требуемые API разрешения

Для создания туннелей и управления Cloudflare требуются следующие API токены:

**Zone API Token (для DNS управления):**
- `Zone:Zone:Read` - чтение информации о зонах
- `Zone:DNS:Edit` - управление DNS записями
- `Tunnel:Create` - создание туннелей
- `Tunnel:Read` - чтение конфигурации туннелей
- `Tunnel:Edit` - редактирование туннелей

**Account API Token (для tunnel credentials):**
- `Account:Cloudflare Tunnel:Edit` - управление туннелями на уровне аккаунта
- `Account:Zone:Read` - чтение зон на уровне аккаунта

#### Получение cloudflared-cert.pem

Сертификат создается автоматически при создании туннеля:

```bash
# Установка cloudflared
brew install cloudflare/cloudflare/cloudflared

# Вход в Cloudflare
cloudflared tunnel login

# Создание туннеля
cloudflared tunnel create telegram-bot-tunnel

# Сертификат будет сохранен в ~/.cloudflared/
ls ~/.cloudflared/*.pem

# Копирование в проект
cp ~/.cloudflared/*.pem cloudflare/cloudflared-cert.pem
```

#### Структура файлов

```
cloudflare/
├── cloudflared-cert.pem              # Origin сертификат (из ~/.cloudflared/)
├── cloudflared-credentials.json       # Реальные credentials (исключен из Git)
├── cloudflared-credentials.json.example  # Шаблон credentials (в Git)
├── cloudflared.json                   # Реальная конфигурация tunnel (исключен из Git)
└── cloudflared.json.example           # Шаблон конфигурации tunnel (в Git)
```

#### Переменные окружения

```env
# Cloudflare Tunnel Configuration
CLOUDFLARE_TUNNEL_TOKEN=your_cloudflare_tunnel_token
PRODUCTION_DOMAIN=your-domain.com
ENABLE_HTTPS_REDIRECT=True
```

#### Безопасность

- ✅ **Реальные файлы** с credentials исключены из `.gitignore`
- ✅ **Шаблонные файлы** используются для настройки новых окружений
- ✅ **Никогда не коммитте** файлы без `.example` расширения
- ✅ **Храните** `cloudflared-cert.pem` в безопасном месте

