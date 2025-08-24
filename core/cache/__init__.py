"""
Единая система кеширования для Telegram Shop Bot
Фаза 1 рефакторинга - базовая инфраструктура

Архитектура:
- base_cache.py: Абстрактный базовый класс для всех сервисов кеширования
- redis_client.py: Унифицированный Redis клиент с поддержкой кластера
- serializers.py: Единые сериализаторы JSON с валидацией
- exceptions.py: Кастомные исключения для кеширования
"""

from .base_cache import BaseCache
from .redis_client import RedisClient, RedisConfig
from .serializers import CacheSerializer
from .exceptions import (
    CacheError,
    CacheConnectionError,
    CacheSerializationError,
    CacheKeyError,
    CacheValueError
)

__all__ = [
    'BaseCache',
    'RedisClient',
    'RedisConfig',
    'CacheSerializer',
    'CacheError',
    'CacheConnectionError',
    'CacheSerializationError',
    'CacheKeyError',
    'CacheValueError'
]