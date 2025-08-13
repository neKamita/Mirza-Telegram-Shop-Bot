"""
User Cache Service - специализированный сервис для кеширования пользовательских данных
"""
import json
import logging
import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import redis.asyncio as redis
from threading import Lock
from config.settings import settings


class LocalCache:
    """Локальное кэширование для graceful degradation при недоступности Redis"""

    def __init__(self, max_size: int = 1000, ttl: int = 300):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.max_size = max_size
        self.ttl = ttl
        self.lock = Lock()
        self.access_times: Dict[str, float] = {}
        self.logger = logging.getLogger(f"{__name__}.local_cache")

    def _cleanup_expired(self):
        """Очистка устаревших записей"""
        current_time = time.time()
        expired_keys = []

        for key, data in self.cache.items():
            if current_time - data['created_at'] > self.ttl:
                expired_keys.append(key)

        for key in expired_keys:
            self._remove_key(key)

    def _remove_key(self, key: str):
        """Удаление ключа из кэша"""
        if key in self.cache:
            del self.cache[key]
            self.access_times.pop(key, None)
            self.logger.debug(f"Removed expired key from local cache: {key}")

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Получение данных из локального кэша"""
        with self.lock:
            self._cleanup_expired()

            if key in self.cache:
                self.access_times[key] = time.time()
                data = self.cache[key].copy()
                data.pop('created_at', None)  # Удаляем служебное поле
                return data

            return None

    def set(self, key: str, value: Dict[str, Any]) -> bool:
        """Сохранение данных в локальный кэш"""
        with self.lock:
            self._cleanup_expired()

            self.cache[key] = {
                'data': value,
                'created_at': time.time()
            }
            self.access_times[key] = time.time()

            self.logger.debug(f"Stored key in local cache: {key}")
            return True


class UserCache:
    """Специализированный сервис для кеширования пользовательских данных"""

    def __init__(self, redis_client: Any):
        self.redis_client = redis_client
        self.logger = logging.getLogger(__name__)
        self.CACHE_PREFIX = "user:"
        self.PROFILE_TTL = settings.cache_ttl_user
        self.BALANCE_TTL = settings.cache_ttl_user // 6  # 5 минут
        self.ACTIVITY_TTL = settings.cache_ttl_user // 2  # 15 минут

        # Локальное кэширование для graceful degradation
        self.local_cache_enabled = settings.redis_local_cache_enabled
        self.local_cache_ttl = settings.redis_local_cache_ttl
        self.local_cache = LocalCache(max_size=1000, ttl=self.local_cache_ttl) if self.local_cache_enabled else None

        self.logger.info(f"UserCache initialized with redis_client: {redis_client is not None}, local_cache: {self.local_cache_enabled}")

    async def cache_user_profile(self, user_id: int, user_data: Dict[str, Any]) -> bool:
        """Кеширование профиля пользователя с graceful degradation"""
        try:
            key = f"{self.CACHE_PREFIX}{user_id}:profile"
            # Добавляем timestamp для отслеживания свежести данных
            user_data['cached_at'] = datetime.utcnow().isoformat()

            # Пытаемся сохранить в Redis
            if self.redis_client:
                try:
                    serialized = json.dumps(user_data, default=str)
                    await self.redis_client.setex(key, self.PROFILE_TTL, serialized)
                    self.logger.debug(f"User profile {user_id} cached in Redis")
                    return True
                except Exception as redis_error:
                    self.logger.warning(f"Failed to cache user profile in Redis, using local cache: {redis_error}")

            # Локальное кэширование
            if self.local_cache:
                self.local_cache.set(key, user_data)
                self.logger.debug(f"User profile {user_id} cached in local cache")
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error caching user profile {user_id}: {e}")
            return False

    async def get_user_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение профиля пользователя из кеша с graceful degradation"""
        try:
            key = f"{self.CACHE_PREFIX}{user_id}:profile"

            # Сначала пробуем локальный кэш
            if self.local_cache:
                local_data = self.local_cache.get(key)
                if local_data:
                    self.logger.debug(f"User profile {user_id} found in local cache")
                    return local_data

            # Если Redis доступен, пробуем Redis
            if self.redis_client:
                try:
                    cached_data = await self.redis_client.get(key)
                    if cached_data:
                        data = json.loads(cached_data)
                        # Проверяем свежесть данных
                        cached_at = datetime.fromisoformat(data.get('cached_at', ''))
                        if datetime.utcnow() - cached_at < timedelta(seconds=self.PROFILE_TTL):
                            # Удаляем временные поля перед возвратом
                            data.pop('cached_at', None)
                            # Кэшируем в локальном хранилище
                            if self.local_cache:
                                self.local_cache.set(key, data)
                            return data
                        else:
                            # Данные устарели, удаляем из кеша
                            await self.redis_client.delete(key)
                except Exception as e:
                    self.logger.warning(f"Failed to get user profile from Redis, using local cache: {e}")
                    # При ошибке Redis пробуем локальный кэш еще раз
                    if self.local_cache:
                        return self.local_cache.get(key)

            return None

        except Exception as e:
            self.logger.error(f"Error getting user profile {user_id}: {e}")
            return None

    async def cache_user_balance(self, user_id: int, balance: int) -> bool:
        """Кеширование баланса пользователя с graceful degradation"""
        try:
            key = f"{self.CACHE_PREFIX}{user_id}:balance"
            balance_data = {
                'balance': balance,
                'cached_at': datetime.utcnow().isoformat()
            }

            # Пытаемся сохранить в Redis
            if self.redis_client:
                try:
                    serialized = json.dumps(balance_data, default=str)
                    await self.redis_client.setex(key, self.BALANCE_TTL, serialized)
                    self.logger.debug(f"User balance {user_id} cached in Redis")
                    return True
                except Exception as redis_error:
                    self.logger.warning(f"Failed to cache user balance in Redis, using local cache: {redis_error}")

            # Локальное кэширование
            if self.local_cache:
                self.local_cache.set(key, balance_data)
                self.logger.debug(f"User balance {user_id} cached in local cache")
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error caching user balance {user_id}: {e}")
            return False

    async def get_user_balance(self, user_id: int) -> Optional[int]:
        """Получение баланса пользователя из кеша с graceful degradation"""
        try:
            key = f"{self.CACHE_PREFIX}{user_id}:balance"

            # Сначала пробуем локальный кэш
            if self.local_cache:
                local_data = self.local_cache.get(key)
                if local_data:
                    self.logger.debug(f"User balance {user_id} found in local cache")
                    return local_data.get('balance')

            # Если Redis доступен, пробуем Redis
            if self.redis_client:
                try:
                    cached_data = await self.redis_client.get(key)
                    if cached_data:
                        data = json.loads(cached_data)
                        # Проверяем свежесть данных
                        cached_at = datetime.fromisoformat(data.get('cached_at', ''))
                        if datetime.utcnow() - cached_at < timedelta(seconds=self.BALANCE_TTL):
                            balance = data['balance']
                            # Кэшируем в локальном хранилище
                            if self.local_cache:
                                self.local_cache.set(key, data)
                            return balance
                        else:
                            # Данные устарели, удаляем из кеша
                            await self.redis_client.delete(key)
                except Exception as e:
                    self.logger.warning(f"Failed to get user balance from Redis, using local cache: {e}")
                    # При ошибке Redis пробуем локальный кэш еще раз
                    if self.local_cache:
                        local_data = self.local_cache.get(key)
                        return local_data.get('balance') if local_data else None

            return None

        except Exception as e:
            self.logger.error(f"Error getting user balance {user_id}: {e}")
            return None

    async def update_user_balance(self, user_id: int, new_balance: int) -> bool:
        """Обновление баланса пользователя в кеше"""
        try:
            key = f"{self.CACHE_PREFIX}{user_id}:balance"
            balance_data = {
                'balance': new_balance,
                'cached_at': datetime.utcnow().isoformat()
            }
            serialized = json.dumps(balance_data, default=str)
            await self.redis_client.setex(key, self.BALANCE_TTL, serialized)
            return True
        except Exception as e:
            self.logger.error(f"Error updating user balance {user_id}: {e}")
            return False

    async def cache_user_activity(self, user_id: int, activity_data: Dict[str, Any]) -> bool:
        """Кеширование активности пользователя с graceful degradation"""
        try:
            key = f"{self.CACHE_PREFIX}{user_id}:activity"
            activity_data['cached_at'] = datetime.utcnow().isoformat()

            # Пытаемся сохранить в Redis
            if self.redis_client:
                try:
                    serialized = json.dumps(activity_data, default=str)
                    await self.redis_client.setex(key, self.ACTIVITY_TTL, serialized)
                    self.logger.debug(f"User activity {user_id} cached in Redis")
                    return True
                except Exception as redis_error:
                    self.logger.warning(f"Failed to cache user activity in Redis, using local cache: {redis_error}")

            # Локальное кэширование
            if self.local_cache:
                self.local_cache.set(key, activity_data)
                self.logger.debug(f"User activity {user_id} cached in local cache")
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error caching user activity {user_id}: {e}")
            return False

    async def get_user_activity(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение активности пользователя из кеша с graceful degradation"""
        try:
            key = f"{self.CACHE_PREFIX}{user_id}:activity"

            # Сначала пробуем локальный кэш
            if self.local_cache:
                local_data = self.local_cache.get(key)
                if local_data:
                    self.logger.debug(f"User activity {user_id} found in local cache")
                    return local_data

            # Если Redis доступен, пробуем Redis
            if self.redis_client:
                try:
                    cached_data = await self.redis_client.get(key)
                    if cached_data:
                        data = json.loads(cached_data)
                        # Проверяем свежесть данных
                        cached_at = datetime.fromisoformat(data.get('cached_at', ''))
                        if datetime.utcnow() - cached_at < timedelta(seconds=self.ACTIVITY_TTL):
                            # Удаляем временные поля перед возвратом
                            data.pop('cached_at', None)
                            # Кэшируем в локальном хранилище
                            if self.local_cache:
                                self.local_cache.set(key, data)
                            return data
                        else:
                            # Данные устарели, удаляем из кеша
                            await self.redis_client.delete(key)
                except Exception as e:
                    self.logger.warning(f"Failed to get user activity from Redis, using local cache: {e}")
                    # При ошибке Redis пробуем локальный кэш еще раз
                    if self.local_cache:
                        return self.local_cache.get(key)

            return None

        except Exception as e:
            self.logger.error(f"Error getting user activity {user_id}: {e}")
            return None

    async def invalidate_user_cache(self, user_id: int) -> bool:
        """Инвалидация всего кеша пользователя"""
        try:
            # Удаляем все связанные с пользователем ключи
            pattern = f"{self.CACHE_PREFIX}{user_id}:*"
            keys = await self.redis_client.keys(pattern)
            if keys:
                await self.redis_client.delete(*keys)
            return True
        except Exception as e:
            self.logger.error(f"Error invalidating user cache {user_id}: {e}")
            return False

    async def is_user_cached(self, user_id: int) -> bool:
        """Проверка, есть ли пользователь в кеше"""
        try:
            key = f"{self.CACHE_PREFIX}{user_id}:profile"
            return await self.redis_client.exists(key) > 0
        except Exception as e:
            self.logger.error(f"Error checking if user {user_id} is cached: {e}")
            return False

    async def get_cache_stats(self, user_id: int) -> Dict[str, Any]:
        """Получение статистики кеша для пользователя"""
        try:
            stats = {}
            for cache_type in ['profile', 'balance', 'activity']:
                key = f"{self.CACHE_PREFIX}{user_id}:{cache_type}"
                exists = await self.redis_client.exists(key)
                if exists:
                    ttl = await self.redis_client.ttl(key)
                    stats[cache_type] = {
                        'exists': True,
                        'ttl': ttl if ttl > 0 else -1
                    }
                else:
                    stats[cache_type] = {'exists': False, 'ttl': 0}
            return stats
        except Exception as e:
            self.logger.error(f"Error getting cache stats for user {user_id}: {e}")
            return {}
