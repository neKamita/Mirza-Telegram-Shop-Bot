"""
User Cache Service - специализированный сервис для кеширования пользовательских данных
"""
import json
import logging
import time
import traceback
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
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

    async def _execute_redis_operation(self, operation: str, *args, **kwargs) -> Any:
        """
        Универсальный метод для выполнения Redis операций с поддержкой
        как синхронных, так и асинхронных клиентов
        
        Args:
            operation: Название операции (get, set, setex, delete, exists и т.д.)
            *args: Аргументы операции
            **kwargs: Именованные аргументы операции
            
        Returns:
            Результат операции
        """
        try:
            # Проверяем доступность Redis клиента
            if not self.redis_client:
                raise ConnectionError("Redis client is not available")
            
            # Получаем метод Redis клиента
            method = getattr(self.redis_client, operation)
            
            # Проверяем, является ли метод асинхронным
            if asyncio.iscoroutinefunction(method):
                # Используем async метод
                return await method(*args, **kwargs)
            else:
                # Для синхронного метода используем asyncio.to_thread
                def wrapped_method():
                    return method(*args, **kwargs)
                
                return await asyncio.to_thread(wrapped_method)
                
        except Exception as e:
            self.logger.error(f"Error executing Redis operation {operation}: {e}")
            raise

    async def cache_user_profile(self, user_id: int, user_data: Dict[str, Any]) -> bool:
        """Кеширование профиля пользователя с graceful degradation"""
        try:
            key = f"{self.CACHE_PREFIX}{user_id}:profile"
            # Добавляем timestamp для отслеживания свежести данных
            user_data['cached_at'] = datetime.now(timezone.utc).isoformat()

            # Пытаемся сохранить в Redis
            if self.redis_client:
                try:
                    serialized = json.dumps(user_data, default=str)
                    print(f"DEBUG: Attempting to save to Redis with setex, key: {key}")
                    result = await self._execute_redis_operation('setex', key, self.PROFILE_TTL, serialized)
                    print(f"DEBUG: Redis setex result: {result}")
                    self.logger.debug(f"User profile {user_id} cached in Redis")
                    
                    # Также сохраняем в локальный кэш для graceful degradation
                    if self.local_cache:
                        # Убираем временные поля для локального кэша
                        local_data = user_data.copy()
                        local_data.pop('cached_at', None)
                        # Сохраняем данные напрямую, LocalCache.get() уже обрабатывает формат
                        self.local_cache.set(key, local_data)
                        self.logger.debug(f"User profile {user_id} also cached in local cache for failover")
                    
                    return True
                except Exception as redis_error:
                    print(f"DEBUG: Redis setex failed, error: {redis_error}")
                    self.logger.warning(f"Failed to cache user profile in Redis, using local cache: {redis_error}")

            # Локальное кэширование
            if self.local_cache:
                # Убираем временные поля для локального кэша
                local_data = user_data.copy()
                local_data.pop('cached_at', None)
                # Сохраняем данные напрямую, LocalCache.get() уже обрабатывает формат
                self.local_cache.set(key, local_data)
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
            print(f"DEBUG: get_user_profile called for user_id: {user_id}, key: {key}")

            # Сначала пробуем локальный кэш
            if self.local_cache:
                print(f"DEBUG: Checking local cache for key: {key}")
                local_data = self.local_cache.get(key)
                print(f"DEBUG: Local cache result for key {key}: {local_data}")
                if local_data:
                    self.logger.debug(f"User profile {user_id} found in local cache")
                    # LocalCache возвращает данные в формате {'data': value}
                    if isinstance(local_data, dict) and 'data' in local_data:
                        print(f"DEBUG: Returning data from local cache: {local_data['data']}")
                        return local_data['data']
                    print(f"DEBUG: Returning local data directly: {local_data}")
                    return local_data
                else:
                    print(f"DEBUG: No data found in local cache for key: {key}")

            # Если Redis доступен, пробуем Redis
            if self.redis_client:
                try:
                    self.logger.debug(f"Attempting to get profile from Redis for user {user_id}")
                    print(f"DEBUG: Getting Redis data for key: {key}")
                    cached_data = await self._execute_redis_operation('get', key)
                    print(f"DEBUG: Redis get result for key {key}: {cached_data}")
                    if cached_data and isinstance(cached_data, (str, bytes)):
                        # Логируем только начало данных для безопасности
                        data_preview = str(cached_data)[:100]
                        self.logger.debug(f"Redis returned data for user {user_id}: {data_preview}...")
                        try:
                            data = json.loads(cached_data)
                            print(f"DEBUG: Parsed Redis data: {data}")
                            # Проверяем свежесть данных
                            cached_at_str = data.get('cached_at', '')
                            if cached_at_str:
                                try:
                                    cached_at = datetime.fromisoformat(cached_at_str)
                                    now = datetime.now(timezone.utc)
                                    time_diff = now - cached_at
                                    ttl_delta = timedelta(seconds=self.PROFILE_TTL)
                                    if time_diff < ttl_delta:
                                        # Удаляем временные поля перед возвратом
                                        data.pop('cached_at', None)
                                        # Кэшируем в локальном хранилище
                                        if self.local_cache:
                                            self.local_cache.set(key, data)
                                        self.logger.info(f"User profile {user_id} found in Redis (fresh)")
                                        print(f"DEBUG: Returning fresh data from Redis: {data}")
                                        return data
                                    else:
                                        self.logger.warning(f"User profile {user_id} found in Redis but expired")
                                        # Данные устарели, удаляем из кеша
                                        await self._execute_redis_operation('delete', key)
                                except ValueError as datetime_error:
                                    self.logger.error(f"Error parsing cached_at for user {user_id}: {datetime_error}")
                                    await self._execute_redis_operation('delete', key)
                            else:
                                self.logger.warning(f"No cached_at field in Redis data for user {user_id}")
                                await self._execute_redis_operation('delete', key)
                        except json.JSONDecodeError as json_error:
                            self.logger.error(f"Error parsing JSON from Redis for user {user_id}: {json_error}")
                            await self._execute_redis_operation('delete', key)
                    elif cached_data:
                        self.logger.debug(f"Redis returned non-string data for user {user_id}: {type(cached_data)}")
                        print(f"DEBUG: Redis returned non-string data: {cached_data}")
                    else:
                        self.logger.debug(f"No profile found in Redis for user {user_id}")
                        print(f"DEBUG: No data found in Redis for key: {key}")
                except Exception as redis_error:
                    self.logger.error(f"Failed to get user profile from Redis: {redis_error}")
                    self.logger.error(f"Redis error type: {type(redis_error).__name__}")
                    self.logger.error(f"Redis error traceback: {traceback.format_exc()}")
                    # При ошибке Redis пробуем локальный кэш еще раз
                    if self.local_cache:
                        self.logger.debug(f"Retrying local cache after Redis error for user {user_id}")
                        try:
                            local_data = self.local_cache.get(key)
                            if local_data:
                                self.logger.info(f"User profile {user_id} found in local cache (fallback)")
                                # LocalCache возвращает данные в формате {'data': value}
                                if isinstance(local_data, dict) and 'data' in local_data:
                                    return local_data['data']
                                return local_data
                            else:
                                self.logger.debug(f"No profile found in local cache fallback for user {user_id}")
                        except Exception as fallback_error:
                            self.logger.error(f"Error in local cache fallback for user {user_id}: {fallback_error}")

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
                'cached_at': datetime.now(timezone.utc).isoformat()
            }
            
            self.logger.debug(f"Attempting to cache user balance for user_id: {user_id}, balance: {balance}")
            self.logger.debug(f"Redis client available: {self.redis_client is not None}")
            self.logger.debug(f"Local cache available: {self.local_cache is not None}")

            # Пытаемся сохранить в Redis
            if self.redis_client:
                try:
                    serialized = json.dumps(balance_data, default=str)
                    self.logger.debug(f"Calling Redis setex for key: {key}, TTL: {self.BALANCE_TTL}")
                    await self._execute_redis_operation('setex', key, self.BALANCE_TTL, serialized)
                    self.logger.info(f"User balance {user_id} successfully cached in Redis")
                    return True
                except Exception as redis_error:
                    self.logger.error(f"Redis cache failed for user {user_id}: {redis_error}")
                    self.logger.error(f"Redis error type: {type(redis_error).__name__}")
                    self.logger.error(f"Redis error traceback: {traceback.format_exc()}")
                    self.logger.warning(f"Falling back to local cache for user balance {user_id}")

            # Локальное кэширование
            if self.local_cache:
                try:
                    self.local_cache.set(key, balance_data)
                    self.logger.info(f"User balance {user_id} successfully cached in local cache")
                    return True
                except Exception as local_cache_error:
                    self.logger.error(f"Local cache failed for user {user_id}: {local_cache_error}")
                    self.logger.error(f"Local cache error type: {type(local_cache_error).__name__}")
                    self.logger.error(f"Local cache error traceback: {traceback.format_exc()}")

            self.logger.error(f"Failed to cache user balance {user_id} in both Redis and local cache")
            return False

        except Exception as e:
            self.logger.error(f"Unexpected error caching user balance {user_id}: {e}")
            self.logger.error(f"Error type: {type(e).__name__}")
            self.logger.error(f"Error traceback: {traceback.format_exc()}")
            return False

    async def get_user_balance(self, user_id: int) -> Optional[int]:
        """Получение баланса пользователя из кеша с graceful degradation"""
        try:
            key = f"{self.CACHE_PREFIX}{user_id}:balance"
            self.logger.debug(f"Attempting to get user balance for user_id: {user_id}")
            self.logger.debug(f"Redis client available: {self.redis_client is not None}")
            self.logger.debug(f"Local cache available: {self.local_cache is not None}")

            # Сначала пробуем локальный кэш
            if self.local_cache:
                try:
                    local_data = self.local_cache.get(key)
                    if local_data:
                        # LocalCache возвращает данные в формате {'data': value}
                        if isinstance(local_data, dict) and 'data' in local_data:
                            balance = local_data['data'].get('balance')
                        else:
                            balance = local_data.get('balance')
                        self.logger.info(f"User balance {user_id} found in local cache: {balance}")
                        return balance
                    else:
                        self.logger.debug(f"No balance found in local cache for user {user_id}")
                except Exception as local_error:
                    self.logger.error(f"Error reading from local cache for user {user_id}: {local_error}")

            # Если Redis доступен, пробуем Redis
            if self.redis_client and not isinstance(self.redis_client, bool):
                try:
                    self.logger.debug(f"Attempting to get balance from Redis for user {user_id}")
                    # Проверяем, что redis_client является асинхронным клиентом
                    # Используем универсальный метод для выполнения Redis операций
                    try:
                        cached_data = await self._execute_redis_operation('get', key)
                    except Exception as e:
                        self.logger.error(f"Redis client error: {e}")
                        cached_data = None
                    if cached_data and isinstance(cached_data, (str, bytes)):
                        # Логируем только начало данных для безопасности
                        data_preview = str(cached_data)[:100]
                        self.logger.debug(f"Redis returned data for user {user_id}: {data_preview}...")
                        try:
                            data = json.loads(cached_data)
                            # Проверяем свежесть данных
                            cached_at_str = data.get('cached_at', '')
                            if cached_at_str:
                                try:
                                    cached_at = datetime.fromisoformat(cached_at_str)
                                    now = datetime.now(timezone.utc)
                                    time_diff = now - cached_at
                                    ttl_delta = timedelta(seconds=self.BALANCE_TTL)
                                    if time_diff < ttl_delta:
                                        balance = data['balance']
                                        self.logger.info(f"User balance {user_id} found in Redis (fresh): {balance}")
                                        # Кэшируем в локальном хранилище
                                        if self.local_cache:
                                            self.local_cache.set(key, data)
                                        return balance
                                    else:
                                        self.logger.warning(f"User balance {user_id} found in Redis but expired")
                                        # Данные устарели, удалов из кеша
                                        await self._execute_redis_operation('delete', key)
                                except ValueError as datetime_error:
                                    self.logger.error(f"Error parsing cached_at for user {user_id}: {datetime_error}")
                                    await self._execute_redis_operation('delete', key)
                            else:
                                self.logger.warning(f"No cached_at field in Redis data for user {user_id}")
                                await self._execute_redis_operation('delete', key)
                        except json.JSONDecodeError as json_error:
                            self.logger.error(f"Error parsing JSON from Redis for user {user_id}: {json_error}")
                            await self._execute_redis_operation('delete', key)
                    elif cached_data:
                        self.logger.debug(f"Redis returned non-string data for user {user_id}: {type(cached_data)}")
                    else:
                        self.logger.debug(f"No balance found in Redis for user {user_id}")
                except Exception as redis_error:
                    self.logger.error(f"Failed to get user balance from Redis: {redis_error}")
                    self.logger.error(f"Redis error type: {type(redis_error).__name__}")
                    self.logger.error(f"Redis error traceback: {traceback.format_exc()}")
                    # При ошибке Redis пробуем локальный кэш еще раз
                    if self.local_cache:
                        self.logger.debug(f"Retrying local cache after Redis error for user {user_id}")
                        try:
                            local_data = self.local_cache.get(key)
                            if local_data:
                                # LocalCache возвращает данные в формате {'data': value}
                                if isinstance(local_data, dict) and 'data' in local_data:
                                    balance = local_data['data'].get('balance')
                                else:
                                    balance = local_data.get('balance')
                                if balance is not None:
                                    self.logger.info(f"User balance {user_id} found in local cache (fallback): {balance}")
                                    return balance
                            else:
                                self.logger.debug(f"No balance found in local cache fallback for user {user_id}")
                        except Exception as fallback_error:
                            self.logger.error(f"Error in local cache fallback for user {user_id}: {fallback_error}")

            self.logger.debug(f"No balance found for user {user_id} in any cache")
            return None

        except Exception as e:
            self.logger.error(f"Unexpected error getting user balance {user_id}: {e}")
            self.logger.error(f"Error type: {type(e).__name__}")
            self.logger.error(f"Error traceback: {traceback.format_exc()}")
            return None

    async def update_user_balance(self, user_id: int, new_balance: int) -> bool:
        """Обновление баланса пользователя в кеше"""
        try:
            key = f"{self.CACHE_PREFIX}{user_id}:balance"
            balance_data = {
                'balance': new_balance,
                'cached_at': datetime.now(timezone.utc).isoformat()
            }
            serialized = json.dumps(balance_data, default=str)
            
            self.logger.debug(f"Attempting to update user balance for user_id: {user_id}, new_balance: {new_balance}")
            self.logger.debug(f"Redis client available: {self.redis_client is not None}")
            
            if self.redis_client and not isinstance(self.redis_client, bool):
                try:
                    # Проверяем, что redis_client является асинхронным клиентом
                    await self._execute_redis_operation('setex', key, self.BALANCE_TTL, serialized)
                    self.logger.info(f"User balance {user_id} successfully updated in Redis")
                    return True
                except Exception as redis_error:
                    self.logger.error(f"Failed to update user balance in Redis: {redis_error}")
                    self.logger.error(f"Redis error type: {type(redis_error).__name__}")
                    self.logger.error(f"Redis error traceback: {traceback.format_exc()}")
                    self.logger.warning(f"Falling back to local cache for user balance update {user_id}")
                
            # Fallback to local cache if Redis fails or is not available
            if self.local_cache:
                try:
                    self.local_cache.set(key, balance_data)
                    self.logger.info(f"User balance {user_id} updated in local cache (fallback)")
                    return True
                except Exception as local_error:
                    self.logger.error(f"Failed to update user balance in local cache: {local_error}")
                    self.logger.error(f"Local cache error type: {type(local_error).__name__}")
                    self.logger.error(f"Local cache error traceback: {traceback.format_exc()}")
            
            self.logger.error(f"Failed to update user balance {user_id} in both Redis and local cache")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error updating user balance {user_id}: {e}")
            self.logger.error(f"Error type: {type(e).__name__}")
            self.logger.error(f"Error traceback: {traceback.format_exc()}")
            return False

    async def cache_user_activity(self, user_id: int, activity_data: Dict[str, Any]) -> bool:
        """Кеширование активности пользователя с graceful degradation"""
        try:
            key = f"{self.CACHE_PREFIX}{user_id}:activity"
            activity_data['cached_at'] = datetime.now(timezone.utc).isoformat()

            # Пытаемся сохранить в Redis
            if self.redis_client:
                try:
                    serialized = json.dumps(activity_data, default=str)
                    await self._execute_redis_operation('setex', key, self.ACTIVITY_TTL, serialized)
                    self.logger.debug(f"User activity {user_id} cached in Redis")
                    return True
                except Exception as redis_error:
                    self.logger.error(f"Redis cache failed for user {user_id}: {redis_error}")
                    self.logger.error(f"Redis error type: {type(redis_error).__name__}")
                    self.logger.error(f"Redis error traceback: {traceback.format_exc()}")
                    self.logger.warning(f"Falling back to local cache for user activity {user_id}")

            # Локальное кэширование
            if self.local_cache:
                try:
                    self.local_cache.set(key, activity_data)
                    self.logger.debug(f"User activity {user_id} cached in local cache")
                    return True
                except Exception as local_cache_error:
                    self.logger.error(f"Local cache failed for user {user_id}: {local_cache_error}")
                    self.logger.error(f"Local cache error type: {type(local_cache_error).__name__}")
                    self.logger.error(f"Local cache error traceback: {traceback.format_exc()}")

            self.logger.error(f"Failed to cache user activity {user_id} in both Redis and local cache")
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
                    self.logger.debug(f"Attempting to get activity from Redis for user {user_id}")
                    cached_data = await self._execute_redis_operation('get', key)
                    if cached_data and isinstance(cached_data, (str, bytes)):
                        # Логируем только начало данных для безопасности
                        data_preview = str(cached_data)[:100]
                        self.logger.debug(f"Redis returned data for user {user_id}: {data_preview}...")
                    elif cached_data:
                        self.logger.debug(f"Redis returned non-string data for user {user_id}: {type(cached_data)}")
                        try:
                            data = json.loads(cached_data)
                            # Проверяем свежесть данных
                            cached_at_str = data.get('cached_at', '')
                            if cached_at_str:
                                try:
                                    cached_at = datetime.fromisoformat(cached_at_str)
                                    if datetime.now(timezone.utc) - cached_at < timedelta(seconds=self.ACTIVITY_TTL):
                                        # Удаляем временные поля перед возвратом
                                        data.pop('cached_at', None)
                                        # Кэшируем в локальном хранилище
                                        if self.local_cache:
                                            self.local_cache.set(key, data)
                                        self.logger.info(f"User activity {user_id} found in Redis (fresh)")
                                        return data
                                    else:
                                        self.logger.warning(f"User activity {user_id} found in Redis but expired")
                                        # Данные устарели, удаляем из кеша
                                        await self._execute_redis_operation('delete', key)
                                except ValueError as datetime_error:
                                    self.logger.error(f"Error parsing cached_at for user {user_id}: {datetime_error}")
                                    await self._execute_redis_operation('delete', key)
                            else:
                                self.logger.warning(f"No cached_at field in Redis data for user {user_id}")
                                await self._execute_redis_operation('delete', key)
                        except json.JSONDecodeError as json_error:
                            self.logger.error(f"Error parsing JSON from Redis for user {user_id}: {json_error}")
                            await self._execute_redis_operation('delete', key)
                    else:
                        self.logger.debug(f"No activity found in Redis for user {user_id}")
                except Exception as redis_error:
                    self.logger.error(f"Failed to get user activity from Redis: {redis_error}")
                    self.logger.error(f"Redis error type: {type(redis_error).__name__}")
                    self.logger.error(f"Redis error traceback: {traceback.format_exc()}")
                    # При ошибке Redis пробуем локальный кэш еще раз
                    if self.local_cache:
                        self.logger.debug(f"Retrying local cache after Redis error for user {user_id}")
                        try:
                            local_data = self.local_cache.get(key)
                            if local_data:
                                self.logger.info(f"User activity {user_id} found in local cache (fallback)")
                                return local_data
                            else:
                                self.logger.debug(f"No activity found in local cache fallback for user {user_id}")
                        except Exception as fallback_error:
                            self.logger.error(f"Error in local cache fallback for user {user_id}: {fallback_error}")

            return None

        except Exception as e:
            self.logger.error(f"Error getting user activity {user_id}: {e}")
            return None

    async def invalidate_user_cache(self, user_id: int) -> bool:
        """Инвалидация всего кеша пользователя"""
        try:
            self.logger.debug(f"Attempting to invalidate cache for user_id: {user_id}")
            self.logger.debug(f"Redis client available: {self.redis_client is not None}")
            
            success = True
            
            # Удаляем все связанные с пользователем ключи из Redis
            if self.redis_client:
                try:
                    pattern = f"{self.CACHE_PREFIX}{user_id}:*"
                    self.logger.debug(f"Getting keys with pattern: {pattern}")
                    keys = await self._execute_redis_operation('keys', pattern)
                    if keys:
                        self.logger.info(f"Found {len(keys)} keys to delete for user {user_id}")
                        await self._execute_redis_operation('delete', *keys)
                        self.logger.info(f"Successfully deleted {len(keys)} keys from Redis for user {user_id}")
                    else:
                        self.logger.debug(f"No keys found for user {user_id} in Redis")
                except Exception as redis_error:
                    self.logger.error(f"Error invalidating Redis cache for user {user_id}: {redis_error}")
                    self.logger.error(f"Redis error type: {type(redis_error).__name__}")
                    self.logger.error(f"Redis error traceback: {traceback.format_exc()}")
                    success = False
            else:
                self.logger.warning(f"Redis client not available for invalidating user cache {user_id}")
            
            # Удаляем из локального кэша
            if self.local_cache:
                try:
                    keys_to_remove = []
                    for key in self.local_cache.cache.keys():
                        if key.startswith(f"{self.CACHE_PREFIX}{user_id}:"):
                            keys_to_remove.append(key)
                    
                    if keys_to_remove:
                        print(f"DEBUG: Found {len(keys_to_remove)} keys to remove from local cache: {keys_to_remove}")
                        for key in keys_to_remove:
                            self.local_cache._remove_key(key)
                        self.logger.info(f"Successfully removed {len(keys_to_remove)} keys from local cache for user {user_id}")
                    else:
                        print(f"DEBUG: No keys found for user {user_id} in local cache")
                        self.logger.debug(f"No keys found for user {user_id} in local cache")
                except Exception as local_error:
                    self.logger.error(f"Error invalidating local cache for user {user_id}: {local_error}")
                    self.logger.error(f"Local cache error type: {type(local_error).__name__}")
                    self.logger.error(f"Local cache error traceback: {traceback.format_exc()}")
                    success = False
            
            if success:
                self.logger.info(f"Successfully invalidated cache for user {user_id}")
            else:
                self.logger.warning(f"Partially invalidated cache for user {user_id} (some errors occurred)")
                
            return success
        except Exception as e:
            self.logger.error(f"Unexpected error invalidating user cache {user_id}: {e}")
            self.logger.error(f"Error type: {type(e).__name__}")
            self.logger.error(f"Error traceback: {traceback.format_exc()}")
            return False

    async def is_user_cached(self, user_id: int) -> bool:
        """Проверка, есть ли пользователь в кеше"""
        try:
            key = f"{self.CACHE_PREFIX}{user_id}:profile"
            self.logger.debug(f"Checking if user {user_id} is cached, key: {key}")
            self.logger.debug(f"Redis client available: {self.redis_client is not None}")
            
            if self.redis_client:
                try:
                    exists = await self._execute_redis_operation('exists', key) > 0
                    self.logger.debug(f"Redis exists result for user {user_id}: {exists}")
                    return exists
                except Exception as redis_error:
                    self.logger.error(f"Error checking Redis cache for user {user_id}: {redis_error}")
                    self.logger.error(f"Redis error type: {type(redis_error).__name__}")
                    self.logger.error(f"Redis error traceback: {traceback.format_exc()}")
            else:
                self.logger.warning(f"Redis client not available for checking user cache {user_id}")
            
            # Fallback to local cache
            if self.local_cache:
                try:
                    local_exists = self.local_cache.get(key) is not None
                    self.logger.debug(f"Local cache exists result for user {user_id}: {local_exists}")
                    return local_exists
                except Exception as local_error:
                    self.logger.error(f"Error checking local cache for user {user_id}: {local_error}")
                    self.logger.error(f"Local cache error type: {type(local_error).__name__}")
                    self.logger.error(f"Local cache error traceback: {traceback.format_exc()}")
            
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error checking if user {user_id} is cached: {e}")
            self.logger.error(f"Error type: {type(e).__name__}")
            self.logger.error(f"Error traceback: {traceback.format_exc()}")
            return False

    async def get_cache_stats(self, user_id: int) -> Dict[str, Any]:
        """Получение статистики кеша для пользователя"""
        try:
            self.logger.debug(f"Getting cache stats for user_id: {user_id}")
            self.logger.debug(f"Redis client available: {self.redis_client is not None}")
            
            stats = {}
            for cache_type in ['profile', 'balance', 'activity']:
                key = f"{self.CACHE_PREFIX}{user_id}:{cache_type}"
                stats[cache_type] = {'exists': False, 'ttl': 0}
                
                try:
                    if self.redis_client:
                        exists = await self._execute_redis_operation('exists', key)
                        if exists:
                            ttl = await self._execute_redis_operation('ttl', key)
                            stats[cache_type] = {
                                'exists': True,
                                'ttl': ttl if ttl > 0 else -1
                            }
                            self.logger.debug(f"Redis stats for {cache_type} - exists: {stats[cache_type]['exists']}, ttl: {stats[cache_type]['ttl']}")
                        else:
                            self.logger.debug(f"Redis stats for {cache_type} - not exists")
                    else:
                        self.logger.warning(f"Redis client not available for cache stats {cache_type}")
                    
                    # Check local cache as well
                    if self.local_cache:
                        local_exists = self.local_cache.get(key) is not None
                        if local_exists:
                            stats[cache_type]['local_cache'] = True
                            self.logger.debug(f"Local cache stats for {cache_type} - exists: True")
                        else:
                            stats[cache_type]['local_cache'] = False
                            self.logger.debug(f"Local cache stats for {cache_type} - not exists")
                            
                except Exception as cache_error:
                    self.logger.error(f"Error getting stats for {cache_type} cache: {cache_error}")
                    self.logger.error(f"Cache error type: {type(cache_error).__name__}")
                    self.logger.error(f"Cache error traceback: {traceback.format_exc()}")
            
            self.logger.info(f"Cache stats for user {user_id}: {stats}")
            return stats
        except Exception as e:
            self.logger.error(f"Unexpected error getting cache stats for user {user_id}: {e}")
            self.logger.error(f"Error type: {type(e).__name__}")
            self.logger.error(f"Error traceback: {traceback.format_exc()}")
            return {}
