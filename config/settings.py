"""
Конфигурационные настройки приложения
"""
import os
from typing import Optional


class Settings:
    """Класс конфигурации приложения"""

    def __init__(self):
        # Telegram Bot
        self.telegram_token: str = os.getenv("TELEGRAM_TOKEN", "")

        # Payment System - Heleket
        self.merchant_uuid: str = os.getenv("MERCHANT_UUID", "")
        self.api_key: str = os.getenv("API_KEY", "")

        # Database - Neon PostgreSQL
        self.database_url: str = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/telegram_bot")
        self.database_pool_size: int = int(os.getenv("DATABASE_POOL_SIZE", "10"))
        self.database_max_overflow: int = int(os.getenv("DATABASE_MAX_OVERFLOW", "20"))

        # Redis
        self.redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis_db: int = int(os.getenv("REDIS_DB", "0"))

        # Nginx/Proxy
        self.proxy_url: str = os.getenv("PROXY_URL", "")

        # Application
        self.debug: bool = os.getenv("DEBUG", "False").lower() == "true"
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")


# Глобальный экземпляр настроек
settings = Settings()
