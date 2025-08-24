"""
Rate Limit Cache Service - миграция на новую единую архитектуру кеширования BaseCache
Сокращение с 389 строк до ~120-150 строк с сохранением полной функциональности
"""

import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from core.cache.base_cache import BaseCache
from core.cache.redis_client import RedisClient, get_default_client
from core.cache.exceptions import CacheGracefulDegradationError
from config.settings import settings


logger = logging.getLogger(__name__)


class RateLimitCacheService(BaseCache):
    """
    Сервис кеширования rate limit с наследованием от BaseCache
    Специализированная реализация для sliding window rate limiting с автоматическими метриками
    """

    def __init__(self,
                 redis_client: Optional[RedisClient] = None,
                 enable_local_cache: Optional[bool] = None,
                 local_cache_ttl: Optional[int] = None):
        """
        Args:
            redis_client: Redis клиент. Если None, используется клиент по умолчанию
            enable_local_cache: Включить локальное кеширование. Если None, берется из настроек
            local_cache_ttl: TTL для локального кеша. Если None, берется из настроек
        """
        # Настройки для rate limiting
        enable_local = enable_local_cache if enable_local_cache is not None else settings.redis_local_cache_enabled
        local_ttl = local_cache_ttl if local_cache_ttl is not None else settings.redis_local_cache_ttl

        # Инициализируем базовый класс
        super().__init__(
            redis_client=redis_client or get_default_client(),
            enable_local_cache=enable_local,
            local_cache_ttl=local_ttl,
            local_cache_size=1000
        )

        # Настройки префиксов для rate limiting
        self.set_cache_prefix("rate_limit")
        self.set_default_ttl(settings.cache_ttl_rate_limit)

        # Специфические префиксы для разных типов rate limiting
        self.RATE_LIMIT_PREFIX = ""
        self.GLOBAL_RATE_LIMIT_PREFIX = "global:"
        self.USER_RATE_LIMIT_PREFIX = "user:"
        self.ACTION_RATE_LIMIT_PREFIX = "action:"

        self.logger.info(f"RateLimitCacheService initialized with local_cache={enable_local}")

    async def get(self, key: str) -> Optional[Any]:
        """Получение значения из кеша с поддержкой graceful degradation"""
        try:
            return await super().get(key)
        except CacheGracefulDegradationError:
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Сохранение значения в кеш с поддержкой graceful degradation"""
        try:
            return await super().set(key, value, ttl)
        except CacheGracefulDegradationError:
            return True  # Graceful degradation - считаем успешным

    async def delete(self, key: str) -> bool:
        """Удаление значения из кеша с поддержкой graceful degradation"""
        try:
            return await super().delete(key)
        except CacheGracefulDegradationError:
            return True  # Graceful degradation - считаем успешным

    # Специфические методы для rate limiting

    async def check_rate_limit(self, identifier: str, action: str, limit: int, window: int = 60) -> bool:
        """Проверка rate limit для идентификатора и действия"""
        try:
            key = f"{self.RATE_LIMIT_PREFIX}{identifier}:{action}"
            current_time = int(time.time())

            # Удаляем старые записи
            await self._cleanup_old_entries(key, current_time, window)

            # Получаем текущее количество
            count = await self._get_list_length(key)

            if count >= limit:
                self.logger.warning(f"Rate limit exceeded for {identifier} on action {action}")
                return False

            # Добавляем новую запись
            await self._push_to_list(key, str(current_time))
            await self._expire_key(key, window)

            return True

        except CacheGracefulDegradationError:
            return True  # Graceful degradation - разрешаем запрос
        except Exception as e:
            self.logger.error(f"Error checking rate limit for {identifier}:{action}: {e}")
            return True

    async def check_global_rate_limit(self, action: str, limit: int, window: int = 60) -> bool:
        """Проверка глобального rate limit"""
        try:
            key = f"{self.GLOBAL_RATE_LIMIT_PREFIX}{action}"
            current_time = int(time.time())

            await self._cleanup_old_entries(key, current_time, window)
            count = await self._get_list_length(key)

            if count >= limit:
                self.logger.warning(f"Global rate limit exceeded for action {action}")
                return False

            await self._push_to_list(key, str(current_time))
            await self._expire_key(key, window)

            return True

        except CacheGracefulDegradationError:
            return True
        except Exception as e:
            self.logger.error(f"Error checking global rate limit for {action}: {e}")
            return True

    async def check_user_rate_limit(self, user_id: int, action: str, limit: int, window: int = 60) -> bool:
        """Проверка rate limit для конкретного пользователя"""
        try:
            key = f"{self.USER_RATE_LIMIT_PREFIX}{user_id}:{action}"
            current_time = int(time.time())

            await self._cleanup_old_entries(key, current_time, window)
            count = await self._get_list_length(key)

            if count >= limit:
                self.logger.warning(f"User rate limit exceeded for {user_id} on action {action}")
                return False

            await self._push_to_list(key, str(current_time))
            await self._expire_key(key, window)

            return True

        except CacheGracefulDegradationError:
            return True
        except Exception as e:
            self.logger.error(f"Error checking user rate limit for {user_id}:{action}: {e}")
            return True

    async def check_action_rate_limit(self, action: str, limit: int, window: int = 60) -> bool:
        """Проверка rate limit для конкретного действия"""
        try:
            key = f"{self.ACTION_RATE_LIMIT_PREFIX}{action}"
            current_time = int(time.time())

            await self._cleanup_old_entries(key, current_time, window)
            count = await self._get_list_length(key)

            if count >= limit:
                self.logger.warning(f"Action rate limit exceeded for {action}")
                return False

            await self._push_to_list(key, str(current_time))
            await self._expire_key(key, window)

            return True

        except CacheGracefulDegradationError:
            return True
        except Exception as e:
            self.logger.error(f"Error checking action rate limit for {action}: {e}")
            return True

    async def get_rate_limit_info(self, identifier: str, action: str, window: int = 60, limit: int = 10) -> Dict[str, Any]:
        """Получение информации о rate limit"""
        try:
            key = f"{self.RATE_LIMIT_PREFIX}{identifier}:{action}"
            current_time = int(time.time())

            await self._cleanup_old_entries(key, current_time, window)
            count = await self._get_list_length(key)
            ttl = await self._get_key_ttl(key)

            remaining = max(0, limit - count)

            return {
                'identifier': identifier,
                'action': action,
                'current_count': count,
                'limit': limit,
                'remaining': remaining,
                'reset_time': datetime.utcnow() + timedelta(seconds=ttl) if ttl > 0 else None,
                'window_seconds': window
            }

        except Exception as e:
            self.logger.error(f"Error getting rate limit info for {identifier}:{action}: {e}")
            return {}

    async def reset_rate_limit(self, identifier: str, action: str) -> bool:
        """Сброс rate limit для идентификатора и действия"""
        try:
            key = f"{self.RATE_LIMIT_PREFIX}{identifier}:{action}"
            return await self._delete_key(key)
        except Exception as e:
            self.logger.error(f"Error resetting rate limit for {identifier}:{action}: {e}")
            return False

    async def reset_user_rate_limits(self, user_id: int) -> int:
        """Сброс всех rate limit для пользователя"""
        try:
            if not self.redis_client:
                return 0

            pattern = f"{self._make_key(self.USER_RATE_LIMIT_PREFIX)}{user_id}:*"
            keys = await self.redis_client.execute_operation('keys', pattern)

            if keys:
                deleted_count = await self.redis_client.execute_operation('delete', *keys)
                self.logger.info(f"Rate limits reset for user {user_id}")
                return deleted_count if deleted_count else len(keys)

            return 0

        except Exception as e:
            self.logger.error(f"Error resetting rate limits for user {user_id}: {e}")
            return 0

    async def get_rate_limit_stats(self) -> Dict[str, Any]:
        """Получение статистики rate limit"""
        try:
            if not self.redis_client:
                return {}

            stats = {
                'total_rate_limits': 0,
                'active_rate_limits': 0,
                'top_limited_actions': [],
                'top_limited_users': []
            }

            rate_limit_keys = await self.redis_client.execute_operation('keys', f"{self._make_key('')}*")
            stats['total_rate_limits'] = len(rate_limit_keys) if rate_limit_keys else 0

            action_counts = {}
            user_counts = {}

            for key in (rate_limit_keys or []):
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                count = await self._get_list_length(key_str)

                if count > 0:
                    stats['active_rate_limits'] += 1

                    if ':' in key_str:
                        parts = key_str.split(':')
                        if len(parts) >= 3:
                            action = parts[2]
                            action_counts[action] = action_counts.get(action, 0) + 1

                            if parts[1].isdigit():
                                user_id = int(parts[1])
                                user_counts[user_id] = user_counts.get(user_id, 0) + 1

            stats['top_limited_actions'] = sorted(action_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            stats['top_limited_users'] = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:5]

            return stats

        except Exception as e:
            self.logger.error(f"Error getting rate limit stats: {e}")
            return {}

    async def is_rate_limited(self, identifier: str, action: str) -> bool:
        """Быстрая проверка, ограничен ли пользователь"""
        try:
            key = f"{self.RATE_LIMIT_PREFIX}{identifier}:{action}"
            count = await self._get_list_length(key)
            return count > 0
        except Exception as e:
            self.logger.error(f"Error checking if rate limited for {identifier}:{action}: {e}")
            return False

    async def get_remaining_requests(self, identifier: str, action: str, limit: int = 10, window: int = 60) -> int:
        """Получение оставшихся запросов"""
        try:
            key = f"{self.RATE_LIMIT_PREFIX}{identifier}:{action}"
            current_time = int(time.time())

            await self._cleanup_old_entries(key, current_time, window)
            count = await self._get_list_length(key)

            return max(0, limit - count)

        except Exception as e:
            self.logger.error(f"Error getting remaining requests for {identifier}:{action}: {e}")
            return limit

    async def increment_rate_limit(self, identifier: str, action: str, ttl: Optional[int] = None) -> bool:
        """Инкремент счетчика rate limit"""
        try:
            key = f"{self.RATE_LIMIT_PREFIX}{identifier}:{action}"
            current_time = int(time.time())

            await self._push_to_list(key, str(current_time))
            expire_ttl = ttl or self._default_ttl
            await self._expire_key(key, expire_ttl)

            return True

        except Exception as e:
            self.logger.error(f"Error incrementing rate limit for {identifier}:{action}: {e}")
            return False

    # Вспомогательные методы для работы с Redis

    async def _cleanup_old_entries(self, key: str, current_time: int, window: int) -> None:
        """Очистка старых записей из rate limit"""
        try:
            if not self.redis_client:
                return

            cutoff_time = current_time - window
            cutoff_time_str = str(cutoff_time)

            await self.redis_client.execute_operation('lrem', self._make_key(key), 0, cutoff_time_str)

        except Exception as e:
            self.logger.error(f"Error cleaning up old entries for {key}: {e}")

    async def _get_list_length(self, key: str) -> int:
        """Получение длины списка"""
        try:
            if not self.redis_client:
                return 0
            return await self.redis_client.execute_operation('llen', self._make_key(key))
        except Exception:
            return 0

    async def _push_to_list(self, key: str, value: str) -> bool:
        """Добавление в список"""
        try:
            if not self.redis_client:
                return False
            await self.redis_client.execute_operation('lpush', self._make_key(key), value)
            return True
        except Exception:
            return False

    async def _expire_key(self, key: str, ttl: int) -> bool:
        """Установка TTL для ключа"""
        try:
            if not self.redis_client:
                return False
            await self.redis_client.execute_operation('expire', self._make_key(key), ttl)
            return True
        except Exception:
            return False

    async def _get_key_ttl(self, key: str) -> int:
        """Получение TTL ключа"""
        try:
            if not self.redis_client:
                return -1
            return await self.redis_client.execute_operation('ttl', self._make_key(key))
        except Exception:
            return -1

    async def _delete_key(self, key: str) -> bool:
        """Удаление ключа"""
        try:
            if not self.redis_client:
                return False
            await self.redis_client.execute_operation('delete', self._make_key(key))
            return True
        except Exception:
            return False


# Глобальный экземпляр для обратной совместимости
_rate_limit_cache_instance: Optional[RateLimitCacheService] = None


def get_rate_limit_cache() -> RateLimitCacheService:
    """Получение глобального экземпляра RateLimitCacheService"""
    global _rate_limit_cache_instance
    if _rate_limit_cache_instance is None:
        _rate_limit_cache_instance = RateLimitCacheService()
    return _rate_limit_cache_instance


# Обратная совместимость - старый интерфейс RateLimitCache
class RateLimitCache:
    """Обертка для обратной совместимости с существующим кодом"""

    def __init__(self, redis_client: Any = None):
        self._service = RateLimitCacheService(redis_client=redis_client)

    async def check_rate_limit(self, identifier: str, action: str, limit: int, window: int = 60) -> bool:
        return await self._service.check_rate_limit(identifier, action, limit, window)

    async def check_global_rate_limit(self, action: str, limit: int, window: int = 60) -> bool:
        return await self._service.check_global_rate_limit(action, limit, window)

    async def check_user_rate_limit(self, user_id: int, action: str, limit: int, window: int = 60) -> bool:
        return await self._service.check_user_rate_limit(user_id, action, limit, window)

    async def check_action_rate_limit(self, action: str, limit: int, window: int = 60) -> bool:
        return await self._service.check_action_rate_limit(action, limit, window)

    async def get_rate_limit_info(self, identifier: str, action: str, window: int = 60, limit: int = 10) -> Dict[str, Any]:
        return await self._service.get_rate_limit_info(identifier, action, window, limit)

    async def reset_rate_limit(self, identifier: str, action: str) -> bool:
        return await self._service.reset_rate_limit(identifier, action)

    async def reset_user_rate_limits(self, user_id: int) -> int:
        return await self._service.reset_user_rate_limits(user_id)

    async def get_rate_limit_stats(self) -> Dict[str, Any]:
        return await self._service.get_rate_limit_stats()

    async def is_rate_limited(self, identifier: str, action: str) -> bool:
        return await self._service.is_rate_limited(identifier, action)

    async def get_remaining_requests(self, identifier: str, action: str, limit: int = 10, window: int = 60) -> int:
        return await self._service.get_remaining_requests(identifier, action, limit, window)

    async def increment_rate_limit(self, identifier: str, action: str, ttl: Optional[int] = None) -> bool:
        return await self._service.increment_rate_limit(identifier, action, ttl)
