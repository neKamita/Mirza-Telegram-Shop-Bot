"""
Абстрактный базовый класс для всех сервисов кеширования

Предоставляет унифицированную архитектуру с:
- Абстрактными методами для основных операций
- Унифицированной обработкой Redis ошибок
- Graceful degradation паттерном
- Логированием операций
- Поддержкой TTL и сериализации
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set
from datetime import datetime, timedelta
from threading import Lock

from .redis_client import RedisClient, RedisConfig
from .serializers import CacheSerializer
from .exceptions import (
    CacheError,
    CacheConnectionError,
    CacheSerializationError,
    CacheKeyError,
    CacheValueError,
    CacheGracefulDegradationError
)


logger = logging.getLogger(__name__)


@dataclass
class CacheMetrics:
    """Метрики производительности кеша"""

    hits: int = 0
    misses: int = 0
    errors: int = 0
    local_cache_hits: int = 0
    redis_operations: int = 0
    average_response_time: float = 0.0

    @property
    def hit_rate(self) -> float:
        """Процент попаданий в кеш"""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0

    def reset(self):
        """Сброс метрик"""
        self.hits = 0
        self.misses = 0
        self.errors = 0
        self.local_cache_hits = 0
        self.redis_operations = 0
        self.average_response_time = 0.0


@dataclass
class LocalCacheEntry:
    """Запись локального кеша"""

    data: Any
    created_at: float
    ttl: int
    access_count: int = 0
    last_access: float = 0.0


class LocalCache:
    """
    Локальное кэширование для graceful degradation

    Thread-safe реализация локального кеша с TTL и LRU eviction.
    """

    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cache: Dict[str, LocalCacheEntry] = {}
        self.lock = Lock()
        self.metrics = CacheMetrics()

    def get(self, key: str) -> Optional[Any]:
        """Получение данных из локального кеша"""
        with self.lock:
            self._cleanup_expired()

            if key in self.cache:
                entry = self.cache[key]
                entry.access_count += 1
                entry.last_access = time.time()
                self.metrics.local_cache_hits += 1
                return entry.data

            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Сохранение данных в локальный кеш"""
        with self.lock:
            self._cleanup_expired()

            # LRU eviction если достигнут лимит
            if len(self.cache) >= self.max_size:
                self._evict_lru()

            ttl_value = ttl if ttl is not None else self.default_ttl
            entry = LocalCacheEntry(
                data=value,
                created_at=time.time(),
                ttl=ttl_value,
                last_access=time.time()
            )

            self.cache[key] = entry
            return True

    def delete(self, key: str) -> bool:
        """Удаление ключа из локального кеша"""
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                return True
            return False

    def clear(self):
        """Очистка всего локального кеша"""
        with self.lock:
            self.cache.clear()

    def _cleanup_expired(self):
        """Очистка устаревших записей"""
        current_time = time.time()
        expired_keys = []

        for key, entry in self.cache.items():
            if current_time - entry.created_at > entry.ttl:
                expired_keys.append(key)

        for key in expired_keys:
            del self.cache[key]

    def _evict_lru(self):
        """Удаление наименее недавно используемых записей (LRU)"""
        if not self.cache:
            return

        # Находим записи с самым старым last_access
        entries = [(k, v) for k, v in self.cache.items()]
        entries.sort(key=lambda x: x[1].last_access)

        # Удаляем 10% от максимального размера
        to_remove = max(1, int(self.max_size * 0.1))
        for i in range(to_remove):
            if entries:
                key, _ = entries.pop(0)
                del self.cache[key]


class BaseCache(ABC):
    """
    Абстрактный базовый класс для всех сервисов кеширования

    Предоставляет унифицированную архитектуру с:
    - Абстрактными методами для основных операций
    - Унифицированной обработкой Redis ошибок
    - Graceful degradation паттерном
    - Логированием операций
    - Поддержкой TTL и сериализации
    """

    def __init__(self,
                 redis_client: Optional[RedisClient] = None,
                 serializer: Optional[CacheSerializer] = None,
                 enable_local_cache: bool = True,
                 local_cache_ttl: int = 300,
                 local_cache_size: int = 1000):
        """
        Args:
            redis_client: Redis клиент. Если None, будет использован глобальный
            serializer: Сериализатор данных. Если None, будет использован по умолчанию
            enable_local_cache: Включить локальное кеширование для graceful degradation
            local_cache_ttl: TTL для локального кеша в секундах
            local_cache_size: Максимальный размер локального кеша
        """
        self.redis_client = redis_client
        self.serializer = serializer or CacheSerializer()
        self.enable_local_cache = enable_local_cache
        self.local_cache = LocalCache(local_cache_size, local_cache_ttl) if enable_local_cache else None

        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.metrics = CacheMetrics()

        # Настройки префиксов и TTL
        self._cache_prefix = ""
        self._default_ttl = 3600

        self.logger.info(f"{self.__class__.__name__} initialized with local_cache={enable_local_cache}")

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """
        Получение значения из кеша

        Args:
            key: Ключ

        Returns:
            Значение или None если ключ не найден
        """
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Сохранение значения в кеш

        Args:
            key: Ключ
            value: Значение
            ttl: Время жизни в секундах

        Returns:
            True если успешно сохранено
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        Удаление значения из кеша

        Args:
            key: Ключ

        Returns:
            True если успешно удалено
        """
        pass

    async def exists(self, key: str) -> bool:
        """
        Проверка существования ключа

        Args:
            key: Ключ

        Returns:
            True если ключ существует
        """
        try:
            return await self.get(key) is not None
        except Exception:
            return False

    async def expire(self, key: str, ttl: int) -> bool:
        """
        Установка TTL для существующего ключа

        Args:
            key: Ключ
            ttl: Время жизни в секундах

        Returns:
            True если успешно установлено
        """
        try:
            if self.redis_client:
                await self.redis_client.execute_operation('expire', self._make_key(key), ttl)
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error setting TTL for key {key}: {e}")
            return False

    async def ttl(self, key: str) -> int:
        """
        Получение оставшегося времени жизни ключа

        Args:
            key: Ключ

        Returns:
            TTL в секундах или -1 если ключ не существует
        """
        try:
            if self.redis_client:
                return await self.redis_client.execute_operation('ttl', self._make_key(key))
            return -1
        except Exception as e:
            self.logger.error(f"Error getting TTL for key {key}: {e}")
            return -1

    async def clear(self) -> bool:
        """
        Очистка всего кеша (только Redis)

        Returns:
            True если успешно очищено
        """
        try:
            if self.redis_client:
                pattern = f"{self._cache_prefix}*"
                keys = await self.redis_client.execute_operation('keys', pattern)
                if keys:
                    await self.redis_client.execute_operation('delete', *keys)
                self.logger.info(f"Cleared {len(keys) if keys else 0} keys from Redis")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error clearing cache: {e}")
            return False

    def _make_key(self, key: str) -> str:
        """
        Формирование полного ключа с префиксом

        Args:
            key: Базовый ключ

        Returns:
            Полный ключ с префиксом
        """
        if self._cache_prefix:
            return f"{self._cache_prefix}:{key}"
        return key

    async def _get_from_redis(self, key: str) -> Optional[str]:
        """
        Получение сырых данных из Redis

        Args:
            key: Ключ

        Returns:
            Сырые данные из Redis или None
        """
        try:
            if not self.redis_client:
                return None

            return await self.redis_client.execute_operation('get', self._make_key(key))

        except CacheConnectionError as e:
            self.logger.warning(f"Redis connection error for key {key}: {e}")
            raise CacheGracefulDegradationError(
                f"Redis unavailable for key {key}",
                original_error=e
            ) from e
        except Exception as e:
            self.logger.error(f"Error getting from Redis for key {key}: {e}")
            self.metrics.errors += 1
            return None

    async def _set_in_redis(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """
        Сохранение сырых данных в Redis

        Args:
            key: Ключ
            value: Сериализованное значение
            ttl: Время жизни

        Returns:
            True если успешно сохранено
        """
        try:
            if not self.redis_client:
                return False

            actual_ttl = ttl if ttl is not None else self._default_ttl

            if actual_ttl > 0:
                await self.redis_client.execute_operation('setex', self._make_key(key), actual_ttl, value)
            else:
                await self.redis_client.execute_operation('set', self._make_key(key), value)

            self.metrics.redis_operations += 1
            return True

        except CacheConnectionError as e:
            self.logger.warning(f"Redis connection error for key {key}: {e}")
            raise CacheGracefulDegradationError(
                f"Redis unavailable for key {key}",
                original_error=e
            ) from e
        except Exception as e:
            self.logger.error(f"Error setting in Redis for key {key}: {e}")
            self.metrics.errors += 1
            return False

    async def _delete_from_redis(self, key: str) -> bool:
        """
        Удаление ключа из Redis

        Args:
            key: Ключ

        Returns:
            True если успешно удалено
        """
        try:
            if not self.redis_client:
                return False

            await self.redis_client.execute_operation('delete', self._make_key(key))
            return True

        except CacheConnectionError as e:
            self.logger.warning(f"Redis connection error for key {key}: {e}")
            raise CacheGracefulDegradationError(
                f"Redis unavailable for key {key}",
                original_error=e
            ) from e
        except Exception as e:
            self.logger.error(f"Error deleting from Redis for key {key}: {e}")
            self.metrics.errors += 1
            return False

    def _get_from_local_cache(self, key: str) -> Optional[Any]:
        """
        Получение данных из локального кеша

        Args:
            key: Ключ

        Returns:
            Данные или None
        """
        if self.local_cache:
            return self.local_cache.get(self._make_key(key))
        return None

    def _set_in_local_cache(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Сохранение данных в локальный кеш

        Args:
            key: Ключ
            value: Значение
            ttl: Время жизни

        Returns:
            True если успешно сохранено
        """
        if self.local_cache:
            actual_ttl = ttl if ttl is not None else self._default_ttl
            return self.local_cache.set(self._make_key(key), value, actual_ttl)
        return False

    def _delete_from_local_cache(self, key: str) -> bool:
        """
        Удаление ключа из локального кеша

        Args:
            key: Ключ

        Returns:
            True если успешно удалено
        """
        if self.local_cache:
            return self.local_cache.delete(self._make_key(key))
        return False

    def get_metrics(self) -> CacheMetrics:
        """
        Получение метрик производительности

        Returns:
            Метрики кеша
        """
        return self.metrics

    def reset_metrics(self):
        """Сброс метрик производительности"""
        self.metrics.reset()

    async def health_check(self) -> Dict[str, Any]:
        """
        Проверка здоровья кеша

        Returns:
            Статус здоровья компонентов
        """
        health = {
            'redis_connected': False,
            'local_cache_enabled': self.enable_local_cache,
            'local_cache_size': len(self.local_cache.cache) if self.local_cache else 0,
            'metrics': {
                'hits': self.metrics.hits,
                'misses': self.metrics.misses,
                'hit_rate': self.metrics.hit_rate,
                'errors': self.metrics.errors
            }
        }

        if self.redis_client:
            try:
                health['redis_connected'] = await self.redis_client.ping()
            except Exception as e:
                health['redis_error'] = str(e)

        return health

    def set_cache_prefix(self, prefix: str):
        """
        Установка префикса для ключей

        Args:
            prefix: Префикс для ключей
        """
        self._cache_prefix = prefix

    def set_default_ttl(self, ttl: int):
        """
        Установка TTL по умолчанию

        Args:
            ttl: Время жизни по умолчанию в секундах
        """
        self._default_ttl = ttl