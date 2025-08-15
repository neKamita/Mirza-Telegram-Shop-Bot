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
        self.redis_url: str = os.getenv("REDIS_URL", "redis://redis-node-1:7379")
        self.redis_cluster_url: str = os.getenv("REDIS_CLUSTER_URL", "redis://redis-node-1:7379")
        self.redis_cluster_nodes: str = os.getenv("REDIS_CLUSTER_NODES", "redis-node-1:7379,redis-node-2:7380,redis-node-3:7381")
        self.redis_cluster_enabled: bool = os.getenv("REDIS_CLUSTER_ENABLED", "False").lower() == "true"
        self.redis_password: str = os.getenv("REDIS_PASSWORD", "")
        self.redis_db: int = int(os.getenv("REDIS_DB", "0"))

        # Определяем, используем ли мы Redis кластер
        self.is_redis_cluster = self.redis_cluster_enabled

        # Redis Client Configuration
        self.redis_timeout: float = float(os.getenv("REDIS_TIMEOUT", "5.0"))
        self.redis_retry_on_timeout: bool = os.getenv("REDIS_RETRY_ON_TIMEOUT", "True").lower() == "true"
        self.redis_max_connections: int = int(os.getenv("REDIS_MAX_CONNECTIONS", "100"))
        self.redis_socket_timeout: float = float(os.getenv("REDIS_SOCKET_TIMEOUT", "5.0"))
        self.redis_socket_connect_timeout: float = float(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "10.0"))
        self.redis_health_check_interval: int = int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30"))
        self.redis_retry_attempts: int = int(os.getenv("REDIS_RETRY_ATTEMPTS", "3"))
        self.redis_retry_backoff_factor: float = float(os.getenv("REDIS_RETRY_BACKOFF_FACTOR", "1.0"))
        self.redis_circuit_breaker_threshold: int = int(os.getenv("REDIS_CIRCUIT_BREAKER_THRESHOLD", "2"))
        self.redis_circuit_breaker_timeout: int = int(os.getenv("REDIS_CIRCUIT_BREAKER_TIMEOUT", "15"))
        self.redis_local_cache_enabled: bool = os.getenv("REDIS_LOCAL_CACHE_ENABLED", "True").lower() == "true"
        self.redis_local_cache_ttl: int = int(os.getenv("REDIS_LOCAL_CACHE_TTL", "300"))

        # SSL Configuration
        self.ssl_cert_path: str = os.getenv("SSL_CERT_PATH", "./ssl/cert.pem")
        self.ssl_key_path: str = os.getenv("SSL_KEY_PATH", "./ssl/key.pem")
        self.ssl_ca_path: str = os.getenv("SSL_CA_PATH", "./ssl/ca.pem")

        # WebSocket Configuration
        self.websocket_port: int = int(os.getenv("WEBSOCKET_PORT", "8080"))
        self.websocket_host: str = os.getenv("WEBSOCKET_HOST", "0.0.0.0")

        # Balance Service Configuration
        self.balance_service_enabled: bool = os.getenv("BALANCE_SERVICE_ENABLED", "True").lower() == "true"
        self.min_purchase_amount: int = int(os.getenv("MIN_PURCHASE_AMOUNT", "1"))
        self.max_purchase_amount: int = int(os.getenv("MAX_PURCHASE_AMOUNT", "100000"))
        self.default_currency: str = os.getenv("DEFAULT_CURRENCY", "TON")

        # Balance Purchase Configuration
        self.balance_purchase_enabled: bool = os.getenv("BALANCE_PURCHASE_ENABLED", "True").lower() == "true"
        self.min_balance_purchase_amount: int = int(os.getenv("MIN_BALANCE_PURCHASE_AMOUNT", "1"))
        self.max_balance_purchase_amount: int = int(os.getenv("MAX_BALANCE_PURCHASE_AMOUNT", "10000"))
        self.balance_purchase_currency: str = os.getenv("BALANCE_PURCHASE_CURRENCY", "TON")

        # Balance Notifications Configuration
        self.balance_notifications_enabled: bool = os.getenv("BALANCE_NOTIFICATIONS_ENABLED", "True").lower() == "true"
        self.purchase_notification_template: str = os.getenv("PURCHASE_NOTIFICATION_TEMPLATE",
            "✅ Покупка успешна!\n\n"
            "⭐ Куплено звезд: {stars_count}\n"
            "💰 Баланс до: {old_balance:.2f} {currency}\n"
            "💰 Баланс после: {new_balance:.2f} {currency}\n\n"
            "Спасибо за покупку!")
        self.insufficient_funds_template: str = os.getenv("INSUFFICIENT_FUNDS_TEMPLATE",
            "❌ Недостаточно средств!\n\n"
            "💰 Ваш баланс: {balance:.2f} {currency}\n"
            "💸 Требуется: {required_amount:.2f} {currency}\n\n"
            "Пополните баланс для покупки звезд.")

        # Balance Recharge Configuration
        self.balance_recharge_enabled: bool = os.getenv("BALANCE_RECHARGE_ENABLED", "True").lower() == "true"
        self.min_recharge_amount: float = float(os.getenv("MIN_RECHARGE_AMOUNT", "10.0"))
        self.max_recharge_amount: float = float(os.getenv("MAX_RECHARGE_AMOUNT", "10000.0"))
        self.recharge_currency: str = os.getenv("RECHARGE_CURRENCY", "TON")
        self.recharge_description: str = os.getenv("RECHARGE_DESCRIPTION", "Пополнение баланса")
        self.recharge_transaction_type: str = os.getenv("RECHARGE_TRANSACTION_TYPE", "recharge")

        # Webhook Configuration
        self.webhook_secret: str = os.getenv("WEBHOOK_SECRET", "")
        self.webhook_path: str = os.getenv("WEBHOOK_PATH", "/webhook/heleket")
        self.webhook_host: str = os.getenv("WEBHOOK_HOST", "0.0.0.0")
        self.webhook_port: int = int(os.getenv("WEBHOOK_PORT", "8001"))
        self.webhook_enabled: bool = os.getenv("WEBHOOK_ENABLED", "True").lower() == "true"

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
