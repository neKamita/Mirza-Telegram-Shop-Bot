# Telegram Bot с Покупкой Звезд

Современный Telegram-бот для покупки звезд через интеграцию с платежной системой Heleket. Проект построен с использованием асинхронной архитектуры и миграций Alembic.

## ✨ Особенности

- **Без премиум-ограничений** - все функции доступны всем пользователям
- **Асинхронная архитектура** - высокая производительность на asyncpg
- **Alembic миграции** - управление схемой базы данных
- **Docker контейнеризация** - легкое развертывание
- **PostgreSQL + Redis** - надежное хранение данных и кеширование
- **Nginx reverse proxy** - безопасность и масштабируемость
- **Cloud native** - работа с Neon PostgreSQL

## 🏗️ Архитектура

```mermaid
graph TB
    subgraph "Telegram Bot"
        A[Telegram API] --> B[Bot Dispatcher]
        B --> C[Message Handler]
        C --> D[User Repository]
        C --> E[Payment Service]
    end

    subgraph "Data Layer"
        D --> F[(PostgreSQL)]
        D --> G[(Redis Cache)]
    end

    subgraph "External Services"
        E --> H[Heleket API]
    end

    subgraph "Infrastructure"
        I[Alembic] --> F
        J[Docker] --> B
        K[Nginx] --> B
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
cp .env.example .env
```

Отредактируйте файл `.env`:

```env
# Telegram Bot Configuration
TELEGRAM_TOKEN=your_telegram_bot_token_here

# Payment System - Heleket Configuration
MERCHANT_UUID=your_merchant_uuid_here
API_KEY=your_api_key_here

# Database Configuration
DATABASE_URL=postgresql+asyncpg://username:password@host.neon.tech/database?ssl=require

# Redis Configuration
REDIS_URL=redis://localhost:6379

# Application Configuration
DEBUG=False
LOG_LEVEL=INFO
```

### 3. Инициализация базы данных

```bash
# Создание первой миграции
alembic revision --autogenerate -m "Initial migration"

# Применение миграций
alembic upgrade head
```

### 4. Запуск через Docker

```bash
# Сборка и запуск
sudo docker-compose up -d

# Проверка статуса
sudo docker-compose ps

# Просмотр логов
sudo docker-compose logs app --tail=30
```

### 5. Запуск в development режиме

```bash
# Создание виртуального окружения
python -m venv venv
source venv/bin/activate  # Для Windows: venv\Scripts\activate

# Установка зависимостей
pip install -r requirements.txt

# Применение миграций
alembic upgrade head

# Запуск
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
├── services/                 # Бизнес-логика
│   ├── __init__.py
│   ├── payment_service.py    # Интеграция с Heleket
│   └── cache_service.py      # Redis кеширование
├── utils/                    # Утилиты
│   └── __init__.py
├── nginx/                    # Nginx конфигурация
│   └── nginx.conf
├── docker-compose.yml        # Docker сервисы
├── Dockerfile               # Контейнер приложения
├── main.py                  # Точка входа
├── requirements.txt         # Зависимости
└── README.md               # Документация
```

## 🔄 Управление миграциями

### Создание новой миграции

```bash
# Автоматическое создание миграции на основе изменений моделей
alembic revision --autogenerate -m "Add new table"

# Ручное создание миграции
alembic revision -m "Manual migration"
```

### Применение миграций

```bash
# Применить все миграции
alembic upgrade head

# Применить конкретную миграцию
alembic upgrade +1

# Применить до конкретной ревизии
alembic upgrade abc123
```

### Откат миграций

```bash
# Откатить последнюю миграцию
alembic downgrade -1

# Откатить до конкретной ревизии
alembic downgrade abc123

# Полный откат
alembic downgrade base
```

### Просмотр состояния

```bash
# Текущая версия
alembic current

# История миграций
alembic history

# Показать SQL для миграции
alembic upgrade head --sql
```

## 💳 Покупка звезд через Heleket

### Процесс покупки

```mermaid
sequenceDiagram
    participant User as Пользователь
    participant Bot as Telegram Bot
    participant Heleket as Heleket API
    participant DB as PostgreSQL

    User->>Bot: Нажимает "Покупка Звезд"
    Bot->>User: Показывает пакеты звезд
    User->>Bot: Выбирает пакет
    Bot->>Heleket: Создает счет на оплату
    Heleket->>Bot: Возвращает ссылку на оплату
    Bot->>User: Отправляет ссылку на оплату
    User->>Heleket: Оплачивает счет
    User->>Bot: Проверяет статус оплаты
    Bot->>Heleket: Проверяет статус счета
    Heleket->>Bot: Подтверждает оплату
    Bot->>DB: Обновляет баланс пользователя
    Bot->>User: Подтверждает покупку
```

### Доступные пакеты

- **100 звезд** - базовый пакет
- **250 звезд** - стандартный пакет
- **500 звезд** - расширенный пакет
- **1000 звезд** - максимальный пакет
- **Своя сумма** - индивидуальная покупка

## 🔧 Сервисы Docker

| Сервис         | Порт           | Описание            |
| -------------- | -------------- | ------------------- |
| telegram-bot   | -              | Основное приложение |
| telegram-nginx | 80, 443        | Reverse proxy       |
| telegram-redis | 6380           | Кеширование         |
| PostgreSQL     | Внешний (Neon) | Основная БД         |

## 🛠️ Переменные окружения

### Обязательные переменные

```env
# Telegram Bot
TELEGRAM_TOKEN=ваш_токен_бота от @BotFather

# Payment System
MERCHANT_UUID=ваш_merchant_uuid от Heleket
API_KEY=ваш_api_key от Heleket

# Database (Neon PostgreSQL)
DATABASE_URL=postgresql+asyncpg://username:password@host.neon.tech/database?ssl=require

# Redis
REDIS_URL=redis://redis:6379/0
```

### Опциональные переменные

```env
# Application
DEBUG=False
LOG_LEVEL=INFO
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

## 🎯 Команды для разработки

### Docker команды

```bash
# Запуск
sudo docker-compose up -d

# Остановка
sudo docker-compose down

# Перезапуск
sudo docker-compose restart

# Логи
sudo docker-compose logs app --tail=50

# Пересборка
sudo docker-compose build --no-cache
sudo docker-compose up -d
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
```

### Alembic команды

```bash
# Инициализация Alembic (если еще не инициализирован)
alembic init alembic

# Создание миграции
alembic revision --autogenerate -m "Description"

# Применение миграций
alembic upgrade head

# Просмотр истории
alembic history --verbose
```

## 🔒 Безопасность

- **SSL/TLS** - обязательное шифрование соединений
- **PostgreSQL** - параметризованные запросы
- **API ключи** - хранение в .env файлах
- **Rate limiting** - ограничение запросов через Nginx
- **Input validation** - проверка всех входных данных
- **Payment security** - безопасная обработка платежей через Heleket

## 🐛 Решение проблем

### Контейнер перезапускается

```bash
# Проверьте логи
sudo docker-compose logs app

# Проверьте миграции
alembic current

# Пересборка
sudo docker-compose down
sudo docker-compose build --no-cache
sudo docker-compose up -d
```

### Проблемы с базой данных

```bash
# Проверка подключения
alembic current

# Применение отсутствующих миграций
alembic upgrade head

# Сброс базы (осторожно!)
alembic downgrade base
alembic upgrade head
```

### Проблемы с платежами

```bash
# Проверьте переменные окружения
echo $MERCHANT_UUID
echo $API_KEY

# Проверьте логи приложения
sudo docker-compose logs app --tail=100
```

## 📈 Мониторинг

```bash
# Проверка ресурсов
sudo docker stats

# Просмотр логов в реальном времени
sudo docker-compose logs -f app

# Проверка состояния базы данных
alembic current
alembic history
```

## 🤝 Contributing

1. Fork репозитория
2. Создайте ветку: `git checkout -b feature/AmazingFeature`
3. Создайте миграцию при необходимости: `alembic revision --autogenerate -m "Add feature"`
4. Сделайте коммит: `git commit -m 'Add some AmazingFeature'`
5. Отправьте изменения: `git push origin feature/AmazingFeature`
6. Создайте Pull Request

## 📄 License

MIT License - см. файл LICENSE для деталей.

## 🆘 Поддержка

Если возникли проблемы:

1. Проверьте логи: `sudo docker-compose logs app`
2. Убедитесь в правильности .env файла
3. Проверьте миграции: `alembic current`
4. Проверьте подключение к Neon PostgreSQL
5. Создайте issue с описанием проблемы и логами

## 📚 Дополнительные ресурсы

- [Aiogram Documentation](https://docs.aiogram.dev/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Heleket API Documentation](https://heleket.com/docs)
- [Neon PostgreSQL](https://neon.tech/docs)
