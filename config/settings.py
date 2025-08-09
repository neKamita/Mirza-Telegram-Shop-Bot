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
        database_url = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/telegram_bot")
        # Заменяем 'postgresql://' на 'postgresql+asyncpg://' для asyncpg драйвера
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        # Обработка SSL параметров для asyncpg
        if "localhost" in database_url or "127.0.0.1" in database_url:
            # Убираем sslmode для локальной разработки
            database_url = database_url.replace("?sslmode=require", "")
            database_url = database_url.replace("&sslmode=require", "")
            database_url = database_url.replace("sslmode=require", "")
        else:
            # Для production (Neon) используем ssl=true вместо sslmode
            if "sslmode=require" in database_url:
                database_url = database_url.replace("sslmode=require", "ssl=true")

        self.database_url: str = database_url
        self.database_pool_size: int = int(os.getenv("DATABASE_POOL_SIZE", "10"))
        self.database_max_overflow: int = int(os.getenv("DATABASE_MAX_OVERFLOW", "20"))

        # Redis Configuration
        self.redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis_cluster_url: str = os.getenv("REDIS_CLUSTER_URL", "redis://localhost:6379")
        self.redis_password: str = os.getenv("REDIS_PASSWORD", "")
        self.redis_db: int = int(os.getenv("REDIS_DB", "0"))

        # SSL Configuration
        self.ssl_cert_path: str = os.getenv("SSL_CERT_PATH", "./ssl/cert.pem")
        self.ssl_key_path: str = os.getenv("SSL_KEY_PATH", "./ssl/key.pem")
        self.ssl_ca_path: str = os.getenv("SSL_CA_PATH", "./ssl/ca.pem")

        # WebSocket Configuration
        self.websocket_port: int = int(os.getenv("WEBSOCKET_PORT", "8080"))
        self.websocket_host: str = os.getenv("WEBSOCKET_HOST", "0.0.0.0")

        # Cache Configuration
        self.cache_ttl_user: int = int(os.getenv("CACHE_TTL_USER", "1800"))
        self.cache_ttl_session: int = int(os.getenv("CACHE_TTL_SESSION", "1800"))
        self.cache_ttl_payment: int = int(os.getenv("CACHE_TTL_PAYMENT", "900"))
        self.cache_ttl_invoice: int = int(os.getenv("CACHE_TTL_INVOICE", "1800"))
        self.cache_ttl_payment_status: int = int(os.getenv("CACHE_TTL_PAYMENT_STATUS", "900"))
        self.cache_ttl_rate_limit: int = int(os.getenv("CACHE_TTL_RATE_LIMIT", "60"))

        # Rate Limiting Configuration
        self.rate_limit_api: int = int(os.getenv("RATE_LIMIT_API", "10"))
        self.rate_limit_payment: int = int(os.getenv("RATE_LIMIT_PAYMENT", "2"))
        self.rate_limit_websocket: int = int(os.getenv("RATE_LIMIT_WEBSOCKET", "5"))

        # Nginx/Proxy
        self.proxy_url: str = os.getenv("PROXY_URL", "")

        # Application
        self.debug: bool = os.getenv("DEBUG", "False").lower() == "true"
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        self.environment: str = os.getenv("ENVIRONMENT", "development")


# Глобальный экземпляр настроек
settings = Settings()
