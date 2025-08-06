# Telegram Bot with Payment System

Современный Telegram-бот с системой платной подписки, разработанный с использованием SOLID принципов и Docker контейнеризации.

## ✨ Особенности

- **SOLID принципы** - Четкое разделение ответственности
- **Асинхронная архитектура** - Высокая производительность на asyncpg
- **Docker контейнеризация** - Легкое развертывание
- **PostgreSQL + Redis** - Надежное хранение данных и кеширование
- **Nginx reverse proxy** - Безопасность и масштабируемость
- **Cloud native** - Работа с Neon PostgreSQL

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

# Database Configuration (Neon PostgreSQL)
DATABASE_URL=postgresql+asyncpg://user:password@host.neon.tech/database?ssl=require

# Redis Configuration
REDIS_URL=redis://redis:6379/0

# Application Configuration
DEBUG=False
LOG_LEVEL=INFO
```

### 3. Запуск через Docker

```bash
# Сборка и запуск
sudo docker-compose up -d

# Проверка статуса
sudo docker-compose ps

# Просмотр логов
sudo docker-compose logs app --tail=30
```

### 4. Запуск в development режиме

```bash
# Создание виртуального окружения
python -m venv venv
source venv/bin/activate  # Для Windows: venv\Scripts\activate

# Установка зависимостей
pip install -r requirements.txt

# Запуск
python main.py
```

## 📁 Структура проекта

```
telegram-bot/
├── config/                 # Конфигурация
│   ├── __init__.py
│   └── settings.py        # Настройки приложения
├── core/                  # Ядро приложения
│   ├── __init__.py
│   └── interfaces.py      # Интерфейсы для SOLID
├── repositories/          # Репозитории
│   ├── __init__.py
│   └── user_repository.py # Работа с PostgreSQL
├── services/              # Бизнес-логика
│   ├── __init__.py
│   ├── payment_service.py # Платежи
│   ├── ai_service.py     # AI интеграция
│   └── cache_service.py  # Redis кеширование
├── handlers/              # Обработчики
│   ├── __init__.py
│   └── message_handler.py # Telegram команды
├── utils/                 # Утилиты
│   └── __init__.py
├── nginx/                 # Nginx конфигурация
│   └── nginx.conf
├── docker-compose.yml    # Docker сервисы
├── Dockerfile            # Контейнер приложения
├── main.py              # Точка входа
├── requirements.txt     # Зависимости
└── README.md           # Документация
```

## 🔧 Сервисы Docker

| Сервис         | Порт           | Описание            |
| -------------- | -------------- | ------------------- |
| telegram-bot   | -              | Основное приложение |
| telegram-nginx | 80, 443        | Reverse proxy       |
| telegram-redis | 6380           | Кеширование         |
| PostgreSQL     | Внешний (Neon) | Основная БД         |

## 🛠️ Настройка переменных окружения

### Обязательные переменные

```env
# Telegram Bot
TELEGRAM_TOKEN=ваш_токен_бота

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
```

## 📊 Команды управления

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

# Запуск с hot reload
python main.py

# Проверка типов
mypy .

# Форматирование кода
black .
isort .
```

## 🔒 Безопасность

- **SSL/TLS** - Обязательное шифрование соединений
- **PostgreSQL** - Параметризованные запросы
- **API ключи** - Хранение в .env файлах
- **Rate limiting** - Ограничение запросов через Nginx
- **Input validation** - Проверка всех входных данных

## 🐛 Решение проблем

### Ошибка подключения к БД

```bash
# Проверьте DATABASE_URL формат
# Должен быть: postgresql+asyncpg://...

# Проверьте SSL параметры
# Используйте: ssl=require вместо sslmode=require
```

### Контейнер перезапускается

```bash
# Проверьте логи
sudo docker-compose logs app

# Пересборка
sudo docker-compose down
sudo docker-compose build --no-cache
sudo docker-compose up -d
```

## 📈 Мониторинг

```bash
# Проверка ресурсов
sudo docker stats

# Просмотр логов в реальном времени
sudo docker-compose logs -f app
```

## 🤝 Contributing

1. Fork репозитория
2. Создайте ветку: `git checkout -b feature/AmazingFeature`
3. Сделайте коммит: `git commit -m 'Add some AmazingFeature'`
4. Отправьте изменения: `git push origin feature/AmazingFeature`
5. Создайте Pull Request

## 📄 License

MIT License - см. файл LICENSE для деталей.

## 🆘 Поддержка

Если возникли проблемы:

1. Проверьте логи: `sudo docker-compose logs app`
2. Убедитесь в правильности .env файла
3. Проверьте подключение к Neon PostgreSQL
4. Создайте issue с описанием проблемы
