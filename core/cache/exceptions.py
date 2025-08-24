"""
Кастомные исключения для системы кеширования

Предоставляет иерархию исключений для обработки различных
ситуаций в работе с кешем.
"""

from typing import Any, Optional


class CacheError(Exception):
    """Базовое исключение для всех ошибок кеширования"""

    def __init__(self, message: str, key: Optional[str] = None, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.key = key
        self.details = details or {}

    def __str__(self) -> str:
        parts = [self.message]
        if self.key:
            parts.append(f"Key: {self.key}")
        if self.details:
            parts.append(f"Details: {self.details}")
        return " | ".join(parts)


class CacheConnectionError(CacheError):
    """Ошибка подключения к Redis или другому хранилищу кеша"""

    def __init__(self, message: str = "Cache connection failed", host: Optional[str] = None,
                 port: Optional[int] = None, details: Optional[dict] = None):
        super().__init__(message, details=details)
        self.host = host
        self.port = port


class CacheSerializationError(CacheError):
    """Ошибка сериализации/десериализации данных"""

    def __init__(self, message: str = "Data serialization failed", data: Optional[Any] = None,
                 operation: Optional[str] = None, details: Optional[dict] = None):
        super().__init__(message, details=details)
        self.data = data
        self.operation = operation


class CacheKeyError(CacheError):
    """Ошибка работы с ключами кеша"""

    def __init__(self, message: str = "Invalid cache key", key: Optional[str] = None,
                 details: Optional[dict] = None):
        super().__init__(message, key=key, details=details)


class CacheValueError(CacheError):
    """Ошибка в значении кеша"""

    def __init__(self, message: str = "Invalid cache value", key: Optional[str] = None,
                 value: Optional[Any] = None, details: Optional[dict] = None):
        super().__init__(message, key=key, details=details)
        self.value = value


class CacheTimeoutError(CacheError):
    """Ошибка таймаута операции кеширования"""

    def __init__(self, message: str = "Cache operation timeout", operation: Optional[str] = None,
                 timeout: Optional[float] = None, details: Optional[dict] = None):
        super().__init__(message, details=details)
        self.operation = operation
        self.timeout = timeout


class CacheQuotaExceededError(CacheError):
    """Превышение квоты или лимита кеша"""

    def __init__(self, message: str = "Cache quota exceeded", quota_type: Optional[str] = None,
                 current_usage: Optional[int] = None, limit: Optional[int] = None,
                 details: Optional[dict] = None):
        super().__init__(message, details=details)
        self.quota_type = quota_type
        self.current_usage = current_usage
        self.limit = limit


class CacheClusterError(CacheError):
    """Ошибка в работе с Redis кластером"""

    def __init__(self, message: str = "Redis cluster operation failed",
                 cluster_info: Optional[dict] = None, details: Optional[dict] = None):
        super().__init__(message, details=details)
        self.cluster_info = cluster_info or {}


class CacheGracefulDegradationError(CacheError):
    """Ошибка graceful degradation - кеш недоступен, используется fallback"""

    def __init__(self, message: str = "Cache unavailable, using fallback mode",
                 original_error: Optional[Exception] = None, details: Optional[dict] = None):
        super().__init__(message, details=details)
        self.original_error = original_error