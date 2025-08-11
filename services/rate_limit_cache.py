"""
Rate Limit Cache Service - специализированный сервис для rate limiting
"""
import json
import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import redis.asyncio as redis
from config.settings import settings


class RateLimitCache:
    """Специализированный сервис для rate limiting"""

    def __init__(self, redis_client: Any):
        self.redis_client = redis_client
        self.logger = logging.getLogger(__name__)
        self.RATE_LIMIT_PREFIX = "rate_limit:"
        self.GLOBAL_RATE_LIMIT_PREFIX = "global_rate_limit:"
        self.USER_RATE_LIMIT_PREFIX = "user_rate_limit:"
        self.ACTION_RATE_LIMIT_PREFIX = "action_rate_limit:"
        self.DEFAULT_TTL = settings.cache_ttl_rate_limit

    async def check_rate_limit(self, identifier: str, action: str, limit: int, window: int = 60) -> bool:
        """
        Проверка rate limit для идентификатора и действия

        Args:
            identifier: IP адрес, user_id или другой идентификатор
            action: Тип действия (api, payment, websocket и т.д.)
            limit: Максимальное количество разрешенных действий
            window: Временное окно в секундах

        Returns:
            True если разрешено, False если превышен лимит
        """
        try:
            key = f"{self.RATE_LIMIT_PREFIX}{identifier}:{action}"
            current_time = int(time.time())

            # Удаляем старые записи
            await self._cleanup_old_entries(key, current_time, window)

            # Получаем текущее количество
            count = await self.redis_client.llen(key)

            if count >= limit:
                self.logger.warning(f"Rate limit exceeded for {identifier} on action {action}")
                return False

            # Добавляем новую запись
            await self.redis_client.lpush(key, str(current_time))
            await self.redis_client.expire(key, window)

            return True

        except Exception as e:
            self.logger.error(f"Error checking rate limit for {identifier}:{action}: {e}")
            # В случае ошибки разрешаем запрос для отказоустойчивости
            return True

    async def check_global_rate_limit(self, action: str, limit: int, window: int = 60) -> bool:
        """Проверка глобального rate limit"""
        try:
            key = f"{self.GLOBAL_RATE_LIMIT_PREFIX}{action}"
            current_time = int(time.time())

            # Удаляем старые записи
            await self._cleanup_old_entries(key, current_time, window)

            # Получаем текущее количество
            count = await self.redis_client.llen(key)

            if count >= limit:
                self.logger.warning(f"Global rate limit exceeded for action {action}")
                return False

            # Добавляем новую запись
            await self.redis_client.lpush(key, str(current_time))
            await self.redis_client.expire(key, window)

            return True

        except Exception as e:
            self.logger.error(f"Error checking global rate limit for {action}: {e}")
            return True

    async def check_user_rate_limit(self, user_id: int, action: str, limit: int, window: int = 60) -> bool:
        """Проверка rate limit для конкретного пользователя"""
        try:
            key = f"{self.USER_RATE_LIMIT_PREFIX}{user_id}:{action}"
            current_time = int(time.time())

            # Удаляем старые записи
            await self._cleanup_old_entries(key, current_time, window)

            # Получаем текущее количество
            count = await self.redis_client.llen(key)

            if count >= limit:
                self.logger.warning(f"User rate limit exceeded for {user_id} on action {action}")
                return False

            # Добавляем новую запись
            await self.redis_client.lpush(key, str(current_time))
            await self.redis_client.expire(key, window)

            return True

        except Exception as e:
            self.logger.error(f"Error checking user rate limit for {user_id}:{action}: {e}")
            return True

    async def check_action_rate_limit(self, action: str, limit: int, window: int = 60) -> bool:
        """Проверка rate limit для конкретного действия"""
        try:
            key = f"{self.ACTION_RATE_LIMIT_PREFIX}{action}"
            current_time = int(time.time())

            # Удаляем старые записи
            await self._cleanup_old_entries(key, current_time, window)

            # Получаем текущее количество
            count = await self.redis_client.llen(key)

            if count >= limit:
                self.logger.warning(f"Action rate limit exceeded for {action}")
                return False

            # Добавляем новую запись
            await self.redis_client.lpush(key, str(current_time))
            await self.redis_client.expire(key, window)

            return True

        except Exception as e:
            self.logger.error(f"Error checking action rate limit for {action}: {e}")
            return True

    async def get_rate_limit_info(self, identifier: str, action: str, window: int = 60) -> Dict[str, Any]:
        """Получение информации о rate limit"""
        try:
            key = f"{self.RATE_LIMIT_PREFIX}{identifier}:{action}"
            current_time = int(time.time())

            # Удаляем старые записи
            await self._cleanup_old_entries(key, current_time, window)

            # Получаем текущее количество
            count = await self.redis_client.llen(key)

            # Получаем оставшееся время до сброса
            ttl = await self.redis_client.ttl(key)

            # Рассчитываем оставшиеся запросы
            remaining = max(0, 10 - count)  # Предполагаем лимит 10

            return {
                'identifier': identifier,
                'action': action,
                'current_count': count,
                'limit': 10,  # Предполагаемый лимит
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
            await self.redis_client.delete(key)
            self.logger.info(f"Rate limit reset for {identifier}:{action}")
            return True
        except Exception as e:
            self.logger.error(f"Error resetting rate limit for {identifier}:{action}: {e}")
            return False

    async def reset_user_rate_limits(self, user_id: int) -> int:
        """Сброс всех rate limit для пользователя"""
        try:
            pattern = f"{self.USER_RATE_LIMIT_PREFIX}{user_id}:*"
            keys = await self.redis_client.keys(pattern)
            if keys:
                await self.redis_client.delete(*keys)
            self.logger.info(f"Rate limits reset for user {user_id}")
            return len(keys)
        except Exception as e:
            self.logger.error(f"Error resetting rate limits for user {user_id}: {e}")
            return 0

    async def get_rate_limit_stats(self) -> Dict[str, Any]:
        """Получение статистики rate limit"""
        try:
            stats = {
                'total_rate_limits': 0,
                'active_rate_limits': 0,
                'top_limited_actions': [],
                'top_limited_users': []
            }

            # Получаем все ключи rate limit
            rate_limit_keys = await self.redis_client.keys(f"{self.RATE_LIMIT_PREFIX}*")
            stats['total_rate_limits'] = len(rate_limit_keys)

            # Анализируем активные лимиты
            action_counts = {}
            user_counts = {}

            for key in rate_limit_keys:
                key_str = key.decode('utf-8')
                count = await self.redis_client.llen(key)

                if count > 0:
                    stats['active_rate_limits'] += 1

                    # Анализируем действия
                    if ':' in key_str:
                        parts = key_str.split(':')
                        if len(parts) >= 3:
                            action = parts[2]
                            action_counts[action] = action_counts.get(action, 0) + 1

                            # Анализируем пользователей
                            if parts[1].isdigit():
                                user_id = int(parts[1])
                                user_counts[user_id] = user_counts.get(user_id, 0) + 1

            # Получаем топ ограниченных действий
            stats['top_limited_actions'] = sorted(
                action_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]

            # Получаем топ ограниченных пользователей
            stats['top_limited_users'] = sorted(
                user_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]

            return stats

        except Exception as e:
            self.logger.error(f"Error getting rate limit stats: {e}")
            return {}

    async def _cleanup_old_entries(self, key: str, current_time: int, window: int) -> None:
        """Очистка старых записей из rate limit"""
        try:
            # Удаляем записи старше временного окна
            cutoff_time = current_time - window
            await self.redis_client.lrem(key, 0, str(cutoff_time))
        except Exception as e:
            self.logger.error(f"Error cleaning up old entries for {key}: {e}")

    async def is_rate_limited(self, identifier: str, action: str) -> bool:
        """Быстрая проверка, ограничен ли пользователь"""
        try:
            key = f"{self.RATE_LIMIT_PREFIX}{identifier}:{action}"
            count = await self.redis_client.llen(key)
            return count > 0
        except Exception as e:
            self.logger.error(f"Error checking if rate limited for {identifier}:{action}: {e}")
            return False

    async def get_remaining_requests(self, identifier: str, action: str, limit: int = 10) -> int:
        """Получение оставшихся запросов"""
        try:
            key = f"{self.RATE_LIMIT_PREFIX}{identifier}:{action}"
            count = await self.redis_client.llen(key)
            return max(0, limit - count)
        except Exception as e:
            self.logger.error(f"Error getting remaining requests for {identifier}:{action}: {e}")
            return limit

    async def increment_rate_limit(self, identifier: str, action: str, ttl: Optional[int] = None) -> bool:
        """Инкремент счетчика rate limit"""
        try:
            key = f"{self.RATE_LIMIT_PREFIX}{identifier}:{action}"
            current_time = int(time.time())

            await self.redis_client.lpush(key, str(current_time))
            expire_ttl = ttl or self.DEFAULT_TTL
            await self.redis_client.expire(key, expire_ttl)

            return True
        except Exception as e:
            self.logger.error(f"Error incrementing rate limit for {identifier}:{action}: {e}")
            return False
