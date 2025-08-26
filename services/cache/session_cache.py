"""
Session Cache Service - специализированный сервис для управления сессиями пользователей
с поддержкой Redis кластера, retry-механизмов, Circuit Breaker и локального кэширования
"""
import json
import logging
import time
import uuid
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, timedelta
import asyncio
from threading import Lock
import weakref

import redis.asyncio as redis
from redis.cluster import RedisCluster
from redis.exceptions import (
    RedisError, ConnectionError, TimeoutError,
    ClusterDownError, ClusterError, MovedError, AskError,
    ConnectionError as RedisConnectionError,  # Псевдоним для избежания конфликта
    ResponseError, DataError
)

from config.settings import settings
from services.system.circuit_breaker import circuit_manager, CircuitConfigs


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

    def _evict_lru(self):
        """Удаление наименее используемых записей при переполнении"""
        if len(self.cache) >= self.max_size:
            # Находим ключ с самым старым доступом
            oldest_key = min(self.access_times.items(), key=lambda x: x[1])[0]
            self._remove_key(oldest_key)

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
            self._evict_lru()

            self.cache[key] = {
                'data': value,
                'created_at': time.time()
            }
            self.access_times[key] = time.time()

            self.logger.debug(f"Stored key in local cache: {key}")
            return True

    def delete(self, key: str) -> bool:
        """Удаление данных из локального кэша"""
        with self.lock:
            if key in self.cache:
                self._remove_key(key)
                return True
            return False

    def clear(self):
        """Очистка всего кэша"""
        with self.lock:
            self.cache.clear()
            self.access_times.clear()
            self.logger.info("Local cache cleared")

    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики локального кэша"""
        with self.lock:
            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'ttl': self.ttl,
                'hit_count': len(self.access_times)
            }


class SessionCache:
    """Специализированный сервис для управления сессиями пользователей с продвинутой обработкой ошибок"""

    # Redis исключения, которые требуют retry
    RETRIABLE_EXCEPTIONS = (
        RedisConnectionError, TimeoutError,
        MovedError, AskError,
        ResponseError
    )

    # Redis исключения, которые не требуют retry (критические ошибки)
    CRITICAL_EXCEPTIONS = (
        ClusterDownError, ClusterError, DataError
    )

    def __init__(self, redis_client: Any = None):
        self.redis_client = redis_client
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"SessionCache initializing with redis_client: {redis_client}")
        self.logger.info(f"Redis client type: {type(redis_client)}")

        self.SESSION_PREFIX = "session:"
        self.SESSION_TTL = settings.cache_ttl_session
        self.SESSION_DATA_PREFIX = "session_data:"
        self.SESSION_STATE_PREFIX = "session_state:"

        # Локальное кэширование
        self.local_cache_enabled = settings.redis_local_cache_enabled
        self.local_cache_ttl = settings.redis_local_cache_ttl
        self.local_cache = LocalCache(max_size=5000, ttl=self.local_cache_ttl) if self.local_cache_enabled else None

        # Circuit Breaker
        self.circuit_breaker = circuit_manager.create_circuit(
            "redis_session_cache",
            CircuitConfigs.redis()
        )

        # Флаг состояния Redis
        self.redis_healthy = True
        self.last_redis_error = None

        # Статистика
        self.stats = {
            'redis_hits': 0,
            'redis_misses': 0,
            'local_cache_hits': 0,
            'local_cache_misses': 0,
            'redis_errors': 0,
            'circuit_breaker_tripped': 0
        }

        self.logger.info("Setting up Redis client...")
        self._setup_redis_client()

    def _setup_redis_client(self):
        """Настройка Redis клиента с оптимизированными параметрами"""
        if self.redis_client is None:
            try:
                self.logger.info(f"Setting up Redis client, is_cluster: {settings.is_redis_cluster}")
                self.logger.info(f"Redis URL: {settings.redis_url}")
                self.logger.info(f"Redis Cluster URL: {settings.redis_cluster_url}")

                if settings.is_redis_cluster:
                    # Конфигурация для Redis кластера
                    cluster_host = settings.redis_cluster_url.split('://')[1].split(':')[0]
                    cluster_port = int(settings.redis_cluster_url.split(':')[-1])

                    self.logger.info(f"Configuring Redis cluster with host: {cluster_host}, port: {cluster_port}")

                    self.redis_client = RedisCluster(
                        host=cluster_host,
                        port=cluster_port,
                        password=settings.redis_password,
                        decode_responses=True,
                        socket_timeout=settings.redis_socket_timeout,
                        socket_connect_timeout=settings.redis_socket_connect_timeout,
                        max_connections=settings.redis_max_connections,
                        health_check_interval=settings.redis_health_check_interval
                    )
                else:
                    # Конфигурация для одиночного Redis
                    redis_host = settings.redis_url.split('://')[1].split(':')[0]
                    redis_port = int(settings.redis_url.split(':')[-1])

                    self.logger.info(f"Configuring Redis with host: {redis_host}, port: {redis_port}")

                    self.redis_client = redis.Redis(
                        host=redis_host,
                        port=redis_port,
                        password=settings.redis_password,
                        db=settings.redis_db,
                        decode_responses=True,
                        socket_timeout=settings.redis_socket_timeout,
                        socket_connect_timeout=settings.redis_socket_connect_timeout,
                        retry_on_timeout=settings.redis_retry_on_timeout,
                        max_connections=settings.redis_max_connections,
                        health_check_interval=settings.redis_health_check_interval
                    )

                # Проверяем тип клиента и настройки декодирования
                self.logger.info(f"Redis client type: {type(self.redis_client)}")
                self.logger.info(f"Redis client configured successfully with decode_responses: {getattr(self.redis_client, 'decode_responses', 'unknown')}")

                # Тестируем соединение (синхронно, так как метод не async)
                try:
                    # Проверяем, что у клиента есть метод ping
                    if hasattr(self.redis_client, 'ping'):
                        self.logger.info("Redis client ping method available")
                        # Проверяем, является ли метод ping корутиной
                        import asyncio
                        is_ping_async = asyncio.iscoroutinefunction(self.redis_client.ping)
                        self.logger.info(f"Redis client ping method is async: {is_ping_async}")

                        # Проверяем, что возвращает метод ping
                        try:
                            if is_ping_async:
                                # Используем event loop для асинхронного ping
                                loop = asyncio.get_event_loop()
                                ping_result = loop.run_until_complete(self.redis_client.ping())
                            else:
                                ping_result = self.redis_client.ping()
                            self.logger.info(f"Redis ping result: {ping_result} (type: {type(ping_result)})")
                        except Exception as ping_error:
                            self.logger.error(f"Redis ping execution failed: {ping_error}")
                            raise
                    else:
                        self.logger.warning("Redis client ping method not available")
                except Exception as ping_error:
                    self.logger.error(f"Redis ping test failed: {ping_error}")
                    raise

            except Exception as e:
                self.logger.error(f"Failed to configure Redis client: {e}")
                self.logger.error(f"Error type: {type(e)}")
                import traceback
                self.logger.error(f"Traceback: {traceback.format_exc()}")
                self.redis_healthy = False
                self.last_redis_error = e
        else:
            self.logger.info(f"Using provided Redis client: {type(self.redis_client)}")
            # Проверяем, что у клиента есть метод ping
            if hasattr(self.redis_client, 'ping'):
                self.logger.info("Redis client ping method available")
                # Проверяем, является ли метод ping корутиной
                import asyncio
                is_ping_async = asyncio.iscoroutinefunction(self.redis_client.ping)
                self.logger.info(f"Redis client ping method is async: {is_ping_async}")

                # Проверяем, что возвращает метод ping
                try:
                    if is_ping_async:
                        # Используем event loop для асинхронного ping
                        loop = asyncio.get_event_loop()
                        ping_result = loop.run_until_complete(self.redis_client.ping())
                    else:
                        ping_result = self.redis_client.ping()
                    self.logger.info(f"Redis ping result: {ping_result} (type: {type(ping_result)})")
                except Exception as ping_error:
                    self.logger.error(f"Redis ping execution failed: {ping_error}")
            else:
                self.logger.warning("Redis client ping method not available")

    async def _execute_redis_operation(self, operation: str, *args, **kwargs) -> Any:
        """Выполнение Redis операции с retry и Circuit Breaker"""

        if not self.redis_healthy:
            self.logger.warning("Redis is not healthy, using local cache fallback")
            raise ConnectionError("Redis is not available")

        # Оборачиваем в Circuit Breaker
        try:
            self.logger.info(f"Executing Redis operation: {operation}")

            # Проверяем тип Redis клиента
            self.logger.info(f"Redis client type: {type(self.redis_client)}")
            self.logger.info(f"Redis client module: {self.redis_client.__class__.__module__}")

            # Для AsyncRedisCluster всегда используем async методы с префиксом 'a'
            async_method = f'a{operation}'

            if hasattr(self.redis_client, async_method):
                # Используем async метод с префиксом 'a'
                redis_async_method = getattr(self.redis_client, async_method)
                self.logger.info(f"Using async method: {async_method}")
                self.logger.info(f"Circuit breaker call with async method: {async_method}")
                self.logger.info(f"Circuit breaker type: {type(self.circuit_breaker)}")
                self.logger.info(f"Circuit breaker call method: {self.circuit_breaker.call}")

                # Дополнительная проверка перед вызовом
                self.logger.info(f"About to call circuit_breaker.call with async method: {async_method}")
                self.logger.info(f"Circuit breaker state before call: {self.circuit_breaker.get_state()}")

                try:
                    result = await self.circuit_breaker.call(
                        redis_async_method,
                        *args, **kwargs
                    )
                    self.logger.info(f"Async method call succeeded, result type: {type(result)}, value: {result}")
                except Exception as e:
                    self.logger.error(f"Async method call failed: {e}")
                    self.logger.error(f"Exception type: {type(e)}")
                    raise
            else:
                # Fallback на обычный метод если async версия не найдена
                redis_method = getattr(self.redis_client, operation)
                self.logger.info(f"Async method {async_method} not found, using fallback method: {operation}")
                self.logger.info(f"Using asyncio.to_thread for sync method: {operation}")

                # Создаем оберточную функцию для Circuit Breaker
                def wrapped_redis_operation():
                    self.logger.info(f"Executing Redis operation: {operation}")
                    try:
                        result = redis_method(*args, **kwargs)
                        self.logger.info(f"Redis operation {operation} succeeded, result: {result} (type: {type(result)})")
                        return result
                    except Exception as e:
                        self.logger.error(f"Redis operation {operation} failed: {e}")
                        raise

                # Используем asyncio.to_thread для синхронной операции
                result = await asyncio.to_thread(wrapped_redis_operation)
                self.logger.info(f"Redis operation {operation} completed in to_thread, result: {result} (type: {type(result)})")

            self.logger.info(f"Redis operation {operation} completed successfully, result type: {type(result)}")
            # Обновляем статистику при успехе
            self.stats['redis_hits'] += 1
            return result

        except self.CRITICAL_EXCEPTIONS as e:
            # Критические ошибки - отключаем Redis
            self._handle_critical_redis_error(e)
            raise

        except Exception as e:
            # Прочие ошибки
            self.logger.error(f"Error in _execute_redis_operation: {e}")
            self.logger.error(f"Error type: {type(e)}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            self._handle_redis_error(e)
            raise

    def _handle_critical_redis_error(self, error: Exception):
        """Обработка критических ошибок Redis"""
        self.redis_healthy = False
        self.last_redis_error = error
        self.stats['redis_errors'] += 1
        self.stats['circuit_breaker_tripped'] += 1

        self.logger.error(f"Critical Redis error: {type(error).__name__}: {error}")
        self.logger.warning("Switching to local cache mode")

        # Очищаем локальное кэш при критической ошибке
        if self.local_cache:
            self.local_cache.clear()

    def _handle_redis_error(self, error: Exception):
        """Обработка ошибок Redis"""
        self.stats['redis_errors'] += 1

        error_type = type(error).__name__
        self.logger.warning(f"Redis operation failed: {error_type}: {error}")

        # Для некоторых ошибок пытаемся восстановить соединение
        if isinstance(error, (ConnectionError, TimeoutError)):
            try:
                self._setup_redis_client()
                self.logger.info("Redis connection re-established")
            except Exception as reconnect_error:
                self.logger.error(f"Failed to reconnect to Redis: {reconnect_error}")

    def _get_cache_key(self, session_id: str) -> str:
        """Генерация ключа для локального кэша"""
        return f"local_session:{session_id}"

    async def create_session(self, user_id: int, initial_data: Optional[Dict[str, Any]] = None) -> str:
        """Создание новой сессии пользователя с graceful degradation"""
        try:
            session_id = str(uuid.uuid4())
            session_key = f"{self.SESSION_PREFIX}{session_id}"

            # Данные сессии
            session_data = {
                'user_id': user_id,
                'created_at': datetime.utcnow().isoformat(),
                'last_activity': datetime.utcnow().isoformat(),
                'is_active': True,
                'id': session_id  # Добавляем ID для удобства
            }

            if initial_data:
                session_data.update(initial_data)

            # Пытаемся сохранить в Redis
            if self.redis_healthy:
                try:
                    serialized = json.dumps(session_data, default=str)

                    # Проверяем, является ли метод setex асинхронным
                    import asyncio
                    setex_method = getattr(self.redis_client, 'setex')
                    self.logger.info(f"setex method: {setex_method}, type: {type(setex_method)}")
                    self.logger.info(f"setex is async: {asyncio.iscoroutinefunction(setex_method)}")

                    # Проверяем, что возвращает setex метод
                    try:
                        if asyncio.iscoroutinefunction(setex_method):
                            test_result = asyncio.get_event_loop().run_until_complete(setex_method(session_key, self.SESSION_TTL, serialized))
                        else:
                            test_result = setex_method(session_key, self.SESSION_TTL, serialized)
                        self.logger.info(f"setex method test result: {test_result} (type: {type(test_result)})")
                    except Exception as setex_test_error:
                        self.logger.error(f"setex method test failed: {setex_test_error}")

                    # Проверяем, является ли метод lpush асинхронным
                    lpush_method = getattr(self.redis_client, 'lpush')
                    self.logger.info(f"lpush method: {lpush_method}, type: {type(lpush_method)}")
                    self.logger.info(f"lpush is async: {asyncio.iscoroutinefunction(lpush_method)}")

                    # Проверяем, что возвращает lpush метод
                    try:
                        # Убеждаемся, что session_id - это строка для Redis
                        session_id_str = str(session_id)
                        if asyncio.iscoroutinefunction(lpush_method):
                            test_result = asyncio.get_event_loop().run_until_complete(lpush_method(f"user_sessions:{user_id}", session_id_str))
                        else:
                            test_result = lpush_method(f"user_sessions:{user_id}", session_id_str)
                        self.logger.info(f"lpush method test result: {test_result} (type: {type(test_result)})")
                    except Exception as lpush_test_error:
                        self.logger.error(f"lpush method test failed: {lpush_test_error}")

                    # Проверяем, является ли метод expire асинхронным
                    expire_method = getattr(self.redis_client, 'expire')
                    self.logger.info(f"expire method: {expire_method}, type: {type(expire_method)}")
                    self.logger.info(f"expire is async: {asyncio.iscoroutinefunction(expire_method)}")

                    # Проверяем, что возвращает expire метод
                    try:
                        if asyncio.iscoroutinefunction(expire_method):
                            test_result = asyncio.get_event_loop().run_until_complete(expire_method(f"user_sessions:{user_id}", self.SESSION_TTL))
                        else:
                            test_result = expire_method(f"user_sessions:{user_id}", self.SESSION_TTL)
                        self.logger.info(f"expire method test result: {test_result} (type: {type(test_result)})")
                    except Exception as expire_test_error:
                        self.logger.error(f"expire method test failed: {expire_test_error}")

                    self.logger.info(f"About to call setex operation for session: {session_id}")
                    await self._execute_redis_operation('setex', session_key, self.SESSION_TTL, serialized)
                    self.logger.info(f"setex operation completed for session: {session_id}")

                    # Индексируем сессии по пользователю
                    user_sessions_key = f"user_sessions:{user_id}"
                    self.logger.info(f"About to call lpush operation for user_sessions_key: {user_sessions_key}")
                    # Убеждаемся, что session_id - это строка для Redis
                    session_id_str = str(session_id)
                    await self._execute_redis_operation('lpush', user_sessions_key, session_id_str)
                    self.logger.info(f"lpush operation completed for user_sessions_key: {user_sessions_key}")

                    self.logger.info(f"About to call expire operation for user_sessions_key: {user_sessions_key}")
                    await self._execute_redis_operation('expire', user_sessions_key, self.SESSION_TTL)
                    self.logger.info(f"expire operation completed for user_sessions_key: {user_sessions_key}")

                    self.logger.info(f"Created session {session_id} for user {user_id} in Redis")

                except Exception as redis_error:
                    self.logger.warning(f"Failed to create session in Redis, using local cache: {redis_error}")
                    # Переходим на локальное кэширование
                    self._create_session_local(session_id, user_id, session_data)
                    return session_id

            # Локальное кэширование (если Redis недоступен или произошла ошибка)
            self._create_session_local(session_id, user_id, session_data)

            return session_id

        except Exception as e:
            self.logger.error(f"Error creating session for user {user_id}: {e}")
            raise

    def _create_session_local(self, session_id: str, user_id: int, session_data: Dict[str, Any]):
        """Локальное создание сессии"""
        if self.local_cache:
            # Сохраняем сессию в локальный кэш
            cache_key = self._get_cache_key(session_id)
            self.local_cache.set(cache_key, session_data)

            # Индексируем сессии по пользователю (в памяти)
            user_sessions_key = f"local_user_sessions:{user_id}"
            if not hasattr(self, '_local_user_sessions'):
                self._local_user_sessions = {}

            if user_sessions_key not in self._local_user_sessions:
                self._local_user_sessions[user_sessions_key] = []

            self._local_user_sessions[user_sessions_key].append(session_id)

            self.logger.info(f"Created session {session_id} for user {user_id} in local cache")

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Получение сессии по ID с graceful degradation"""
        cache_key = self._get_cache_key(session_id)
        self.logger.debug(f"Getting session for ID: {session_id}, cache_key: {cache_key}")

        # Проверяем, является ли метод get асинхронным
        import asyncio
        get_method = getattr(self.redis_client, 'get')
        self.logger.info(f"get method: {get_method}, type: {type(get_method)}")
        self.logger.info(f"get is async: {asyncio.iscoroutinefunction(get_method)}")

        # Сначала пробуем локальный кэш
        if self.local_cache:
            local_data = self.local_cache.get(cache_key)
            if local_data:
                self.stats['local_cache_hits'] += 1
                self.logger.debug(f"Session {session_id} found in local cache: {local_data}")
                return local_data
            self.stats['local_cache_misses'] += 1

        # Если Redis доступен, пробуем Redis
        if self.redis_healthy:
            try:
                session_key = f"{self.SESSION_PREFIX}{session_id}"
                self.logger.debug(f"Getting session from Redis, key: {session_key}")

                cached_data = await self._execute_redis_operation('get', session_key)
                self.logger.debug(f"Raw cached data from Redis: {cached_data} (type: {type(cached_data)})")

                if cached_data:
                    try:
                        session_data = json.loads(cached_data)
                        self.logger.debug(f"Parsed session data: {session_data} (type: {type(session_data)})")

                        # Проверяем, что это словарь
                        if not isinstance(session_data, dict):
                            self.logger.error(f"Expected dict but got {type(session_data)} for session {session_id}")
                            return None

                        # Проверяем активность и свежесть
                        if session_data.get('is_active') and self._is_session_valid(session_data):
                            # Обновляем время последней активности
                            session_data['last_activity'] = datetime.utcnow().isoformat()
                            await self.update_session(session_id, session_data)

                            # Кэшируем в локальном хранилище
                            if self.local_cache:
                                self.local_cache.set(cache_key, session_data)

                            self.logger.debug(f"Returning valid session data for {session_id}")
                            return session_data
                        else:
                            # Сессия неактивна или устарела
                            self.logger.debug(f"Session {session_id} is inactive or expired")
                            await self.delete_session(session_id)

                    except json.JSONDecodeError as json_error:
                        self.logger.error(f"JSON decode error for session {session_id}: {json_error}")
                        return None
                    except Exception as parse_error:
                        self.logger.error(f"Error parsing session data for {session_id}: {parse_error}")
                        return None

                self.logger.debug(f"No session found in Redis for {session_id}")
                return None

            except Exception as e:
                self.logger.error(f"Failed to get session from Redis: {e}")
                self.logger.error(f"Error type: {type(e)}")
                import traceback
                self.logger.error(f"Traceback: {traceback.format_exc()}")
                # При ошибке Redis пробуем локальный кэш еще раз
                if self.local_cache:
                    return self.local_cache.get(cache_key)

        self.logger.debug(f"No session found for {session_id}")
        return None

    async def update_session(self, session_id: str, session_data: Dict[str, Any]) -> bool:
        """Обновление данных сессии с graceful degradation"""
        try:
            session_data['last_activity'] = datetime.utcnow().isoformat()
            serialized = json.dumps(session_data, default=str)

            # Пытаемся обновить в Redis
            if self.redis_healthy:
                try:
                    session_key = f"{self.SESSION_PREFIX}{session_id}"
                    await self._execute_redis_operation('setex', session_key, self.SESSION_TTL, serialized)

                    # Кэшируем в локальном хранилище
                    if self.local_cache:
                        cache_key = self._get_cache_key(session_id)
                        self.local_cache.set(cache_key, session_data)

                    return True

                except Exception as redis_error:
                    self.logger.warning(f"Failed to update session in Redis, updating local cache: {redis_error}")

            # Локальное обновление
            if self.local_cache:
                cache_key = self._get_cache_key(session_id)
                self.local_cache.set(cache_key, session_data)
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error updating session {session_id}: {e}")
            return False

    async def delete_session(self, session_id: str) -> bool:
        """Удаление сессии с graceful degradation"""
        try:
            # Удаляем из Redis если доступен
            if self.redis_healthy:
                try:
                    session_key = f"{self.SESSION_PREFIX}{session_id}"
                    await self._execute_redis_operation('delete', session_key)

                    # Удаляем связанные данные
                    await self._execute_redis_operation('delete', f"{self.SESSION_DATA_PREFIX}{session_id}")
                    await self._execute_redis_operation('delete', f"{self.SESSION_STATE_PREFIX}{session_id}")

                    # Удаляем из индекса пользователя
                    session_data = await self.get_session(session_id)
                    if session_data:
                        await self._remove_from_user_index_redis(session_id, session_data)

                except Exception as redis_error:
                    self.logger.warning(f"Failed to delete session from Redis, cleaning local cache: {redis_error}")

            # Удаляем из локального кэша
            if self.local_cache:
                cache_key = self._get_cache_key(session_id)
                self.local_cache.delete(cache_key)

                # Удаляем из локального индекса
                self._remove_from_local_user_index(session_id)

            self.logger.info(f"Deleted session {session_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error deleting session {session_id}: {e}")
            return False

    async def _remove_from_user_index_redis(self, session_id: str, session_data: Dict[str, Any]):
        """Удаление сессии из индекса пользователя в Redis"""
        if session_data and 'user_id' in session_data:
            user_sessions_key = f"user_sessions:{session_data['user_id']}"
            # Убеждаемся, что session_id - это строка для Redis
            session_id_str = str(session_id)
            await self._execute_redis_operation('lrem', user_sessions_key, 0, session_id_str)

    def _remove_from_local_user_index(self, session_id: str):
        """Удаление сессии из локального индекса пользователя"""
        if hasattr(self, '_local_user_sessions'):
            for user_sessions_key in self._local_user_sessions:
                if session_id in self._local_user_sessions[user_sessions_key]:
                    self._local_user_sessions[user_sessions_key].remove(session_id)
                    break

    async def get_user_sessions(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение всех активных сессий пользователя с graceful degradation"""
        sessions = []

        # Пробуем Redis если доступен
        if self.redis_healthy:
            try:
                user_sessions_key = f"user_sessions:{user_id}"
                self.logger.debug(f"Getting user sessions for user {user_id}, key: {user_sessions_key}")

                session_ids = await self._execute_redis_operation('lrange', user_sessions_key, 0, -1)
                self.logger.debug(f"Found {len(session_ids)} session IDs for user {user_id}")

                for session_id_bytes in session_ids:
                    try:
                        # Проверяем тип данных session_id_bytes
                        self.logger.debug(f"Processing session_id_bytes: {type(session_id_bytes)}, value: {session_id_bytes}")

                        # Декодируем только если это байты
                        if isinstance(session_id_bytes, bytes):
                            session_id = session_id_bytes.decode('utf-8')
                        else:
                            session_id = str(session_id_bytes)

                        self.logger.debug(f"Processing session ID: {session_id}")

                        session = await self.get_session(session_id)
                        if session:
                            self.logger.debug(f"Found session for {session_id}: {session}")
                            sessions.append(session)
                        else:
                            self.logger.debug(f"No session found for ID: {session_id}")

                    except Exception as session_error:
                        self.logger.error(f"Error processing session ID {session_id_bytes}: {session_error}")
                        continue

                self.logger.info(f"Retrieved {len(sessions)} sessions for user {user_id} from Redis")
                return sessions

            except Exception as e:
                self.logger.error(f"Failed to get user sessions from Redis: {e}")
                self.logger.error(f"Error type: {type(e)}")
                import traceback
                self.logger.error(f"Traceback: {traceback.format_exc()}")

        # Локальное кэширование
        if hasattr(self, '_local_user_sessions'):
            user_sessions_key = f"local_user_sessions:{user_id}"
            if user_sessions_key in self._local_user_sessions:
                for session_id in self._local_user_sessions[user_sessions_key]:
                    session = await self.get_session(session_id)
                    if session:
                        sessions.append(session)

        return sessions

    async def invalidate_user_sessions(self, user_id: int, keep_active: bool = False) -> int:
        """Инвалидация всех сессий пользователя с graceful degradation"""
        try:
            sessions = await self.get_user_sessions(user_id)
            invalidated_count = 0

            for session in sessions:
                if keep_active and session.get('is_active'):
                    continue
                await self.delete_session(session['id'])
                invalidated_count += 1

            self.logger.info(f"Invalidated {invalidated_count} sessions for user {user_id}")
            return invalidated_count

        except Exception as e:
            self.logger.error(f"Error invalidating sessions for user {user_id}: {e}")
            return 0

    async def cache_session_data(self, session_id: str, data: Dict[str, Any]) -> bool:
        """Кеширование данных сессии с graceful degradation"""
        try:
            data['cached_at'] = datetime.utcnow().isoformat()
            serialized = json.dumps(data, default=str)

            # Пытаемся сохранить в Redis
            if self.redis_healthy:
                try:
                    data_key = f"{self.SESSION_DATA_PREFIX}{session_id}"
                    await self._execute_redis_operation('setex', data_key, self.SESSION_TTL, serialized)
                    return True

                except Exception as redis_error:
                    self.logger.warning(f"Failed to cache session data in Redis, using local cache: {redis_error}")

            # Локальное кэширование
            if self.local_cache:
                cache_key = f"{self._get_cache_key(session_id)}_data"
                self.local_cache.set(cache_key, data)
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error caching session data for {session_id}: {e}")
            return False

    async def get_session_data(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Получение данных сессии с graceful degradation"""
        # Сначала пробуем локальный кэш
        if self.local_cache:
            cache_key = f"{self._get_cache_key(session_id)}_data"
            local_data = self.local_cache.get(cache_key)
            if local_data:
                # Проверяем свежесть
                cached_at = datetime.fromisoformat(local_data.get('cached_at', ''))
                if datetime.utcnow() - cached_at < timedelta(seconds=self.SESSION_TTL):
                    data = local_data.copy()
                    data.pop('cached_at', None)
                    return data
                else:
                    self.local_cache.delete(cache_key)

        # Пробуем Redis если доступен
        if self.redis_healthy:
            try:
                data_key = f"{self.SESSION_DATA_PREFIX}{session_id}"
                cached_data = await self._execute_redis_operation('get', data_key)

                if cached_data:
                    data = json.loads(cached_data)
                    # Проверяем свежесть
                    cached_at = datetime.fromisoformat(data.get('cached_at', ''))
                    if datetime.utcnow() - cached_at < timedelta(seconds=self.SESSION_TTL):
                        data.pop('cached_at', None)
                        # Кэшируем в локальном хранилище
                        if self.local_cache:
                            cache_key = f"{self._get_cache_key(session_id)}_data"
                            self.local_cache.set(cache_key, data)
                        return data
                    else:
                        await self._execute_redis_operation('delete', data_key)

                return None

            except Exception as e:
                self.logger.warning(f"Failed to get session data from Redis: {e}")

        return None

    async def cache_session_state(self, session_id: str, state: Dict[str, Any]) -> bool:
        """Кеширование состояния сессии с graceful degradation"""
        try:
            state['updated_at'] = datetime.utcnow().isoformat()
            serialized = json.dumps(state, default=str)

            # Пытаемся сохранить в Redis
            if self.redis_healthy:
                try:
                    state_key = f"{self.SESSION_STATE_PREFIX}{session_id}"
                    await self._execute_redis_operation('setex', state_key, self.SESSION_TTL, serialized)
                    return True

                except Exception as redis_error:
                    self.logger.warning(f"Failed to cache session state in Redis, using local cache: {redis_error}")

            # Локальное кэширование
            if self.local_cache:
                cache_key = f"{self._get_cache_key(session_id)}_state"
                self.local_cache.set(cache_key, state)
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error caching session state for {session_id}: {e}")
            return False

    async def get_session_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Получение состояния сессии с graceful degradation"""
        # Сначала пробуем локальный кэш
        if self.local_cache:
            cache_key = f"{self._get_cache_key(session_id)}_state"
            local_data = self.local_cache.get(cache_key)
            if local_data:
                # Проверяем свежесть
                updated_at = datetime.fromisoformat(local_data.get('updated_at', ''))
                if datetime.utcnow() - updated_at < timedelta(seconds=self.SESSION_TTL):
                    data = local_data.copy()
                    data.pop('updated_at', None)
                    return data
                else:
                    self.local_cache.delete(cache_key)

        # Пробуем Redis если доступен
        if self.redis_healthy:
            try:
                state_key = f"{self.SESSION_STATE_PREFIX}{session_id}"
                cached_data = await self._execute_redis_operation('get', state_key)

                if cached_data:
                    state = json.loads(cached_data)
                    # Проверяем свежесть
                    updated_at = datetime.fromisoformat(state.get('updated_at', ''))
                    if datetime.utcnow() - updated_at < timedelta(seconds=self.SESSION_TTL):
                        state.pop('updated_at', None)
                        # Кэшируем в локальном хранилище
                        if self.local_cache:
                            cache_key = f"{self._get_cache_key(session_id)}_state"
                            self.local_cache.set(cache_key, state)
                        return state
                    else:
                        await self._execute_redis_operation('delete', state_key)

                return None

            except Exception as e:
                self.logger.warning(f"Failed to get session state from Redis: {e}")

        return None

    async def extend_session(self, session_id: str, additional_ttl: Optional[int] = None) -> bool:
        """Продление срока действия сессии с graceful degradation"""
        try:
            session = await self.get_session(session_id)

            if session:
                new_ttl = additional_ttl or self.SESSION_TTL

                # Пытаемся продлить в Redis
                if self.redis_healthy:
                    try:
                        session_key = f"{self.SESSION_PREFIX}{session_id}"
                        await self._execute_redis_operation('expire', session_key, new_ttl)

                        # Также продлеваем связанные данные
                        await self._execute_redis_operation('expire', f"{self.SESSION_DATA_PREFIX}{session_id}", new_ttl)
                        await self._execute_redis_operation('expire', f"{self.SESSION_STATE_PREFIX}{session_id}", new_ttl)

                        self.logger.info(f"Extended session {session_id} for {new_ttl} seconds in Redis")
                        return True

                    except Exception as redis_error:
                        self.logger.warning(f"Failed to extend session in Redis, updating local cache: {redis_error}")

                # Локальное продление
                if self.local_cache:
                    cache_key = self._get_cache_key(session_id)
                    self.local_cache.set(cache_key, session)
                    self.logger.info(f"Extended session {session_id} for {new_ttl} seconds in local cache")
                    return True

            return False

        except Exception as e:
            self.logger.error(f"Error extending session {session_id}: {e}")
            return False

    def _is_session_valid(self, session_data: Dict[str, Any]) -> bool:
        """Проверка валидности сессии"""
        try:
            last_activity = datetime.fromisoformat(session_data.get('last_activity', ''))
            max_inactive = timedelta(minutes=30)  # 30 минут бездействия

            return datetime.utcnow() - last_activity < max_inactive

        except Exception:
            return False

    async def get_session_stats(self) -> Dict[str, Any]:
        """Получение статистики сессий с graceful degradation"""
        try:
            stats = {
                'total_sessions': 0,
                'active_sessions': 0,
                'inactive_sessions': 0,
                'redis_status': 'healthy' if self.redis_healthy else 'degraded',
                'last_redis_error': str(self.last_redis_error) if self.last_redis_error else None,
                'cache_stats': self.local_cache.get_stats() if self.local_cache else None,
                'operation_stats': self.stats.copy(),
                'circuit_breaker_state': self.circuit_breaker.get_state()
            }

            # Получаем статистику из Redis если доступен
            if self.redis_healthy:
                try:
                    session_keys = await self._execute_redis_operation('keys', f"{self.SESSION_PREFIX}*")
                    stats['total_sessions'] = len(session_keys)

                    # Проверяем активность каждой сессии
                    for key in session_keys:
                        session_id = key.decode('utf-8').replace(self.SESSION_PREFIX, '')
                        session = await self.get_session(session_id)
                        if session and session.get('is_active'):
                            stats['active_sessions'] += 1
                        else:
                            stats['inactive_sessions'] += 1

                except Exception as e:
                    self.logger.warning(f"Failed to get session stats from Redis: {e}")

            # Дополняем статистику из локального кэша
            if self.local_cache:
                local_stats = self.local_cache.get_stats()
                stats['local_cache_sessions'] = local_stats['size']

            return stats

        except Exception as e:
            self.logger.error(f"Error getting session stats: {e}")
            return {}

    async def health_check(self) -> Dict[str, Any]:
        """Проверка здоровья сервиса"""
        try:
            health_status = {
                'status': 'healthy',
                'redis_connected': self.redis_healthy,
                'local_cache_enabled': self.local_cache_enabled,
                'last_error': str(self.last_redis_error) if self.last_redis_error else None,
                'circuit_breaker': self.circuit_breaker.get_state(),
                'cache_stats': self.local_cache.get_stats() if self.local_cache else None,
                'operation_stats': self.stats.copy()
            }

            # Проверяем соединение с Redis
            if self.redis_healthy and self.redis_client:
                try:
                    # Простая проверка пинга
                    self.logger.info(f"Attempting to ping Redis client: {type(self.redis_client)}")

                    # Проверяем, является ли метод ping корутиной
                    import asyncio
                    ping_method = getattr(self.redis_client, 'ping')
                    self.logger.info(f"ping method: {ping_method}, type: {type(ping_method)}")
                    self.logger.info(f"ping is async: {asyncio.iscoroutinefunction(ping_method)}")

                    # Проверяем, является ли метод ping асинхронным
                    import asyncio
                    ping_method = getattr(self.redis_client, 'ping')
                    self.logger.info(f"ping method: {ping_method}, type: {type(ping_method)}")
                    self.logger.info(f"ping is async: {asyncio.iscoroutinefunction(ping_method)}")

                    if asyncio.iscoroutinefunction(ping_method):
                        self.logger.info("Using async ping method")
                        await ping_method()
                        health_status['redis_status'] = 'connected'
                    else:
                        self.logger.info("Using sync ping method in async context")
                        # Используем executor для синхронного метода
                        loop = asyncio.get_event_loop()
                        result = await loop.run_in_executor(None, ping_method)
                        self.logger.info(f"Sync ping result: {result}")
                        health_status['redis_status'] = 'connected'

                except Exception as e:
                    health_status['redis_status'] = 'error'
                    health_status['last_error'] = str(e)
                    self.logger.error(f"Redis ping error: {e}")
                    self.logger.error(f"Error type: {type(e)}")
                    import traceback
                    self.logger.error(f"Traceback: {traceback.format_exc()}")
                    self.redis_healthy = False

            # Определяем общий статус
            if not self.redis_healthy and not (self.local_cache_enabled and self.local_cache):
                health_status['status'] = 'degraded'
            elif not self.redis_healthy:
                health_status['status'] = 'degraded'
            else:
                health_status['status'] = 'healthy'

            return health_status

        except Exception as e:
            self.logger.error(f"Error during health check: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'redis_connected': False,
                'local_cache_enabled': self.local_cache_enabled
            }

    async def cleanup_expired_sessions(self) -> int:
        """Очистка устаревших сессий"""
        cleaned_count = 0

        try:
            # Очистка в Redis
            if self.redis_healthy:
                try:
                    session_keys = await self._execute_redis_operation('keys', f"{self.SESSION_PREFIX}*")
                    self.logger.debug(f"Found {len(session_keys)} session keys to check for expiration")

                    for key in session_keys:
                        try:
                            # Проверяем тип ключа
                            self.logger.debug(f"Processing session key: {type(key)}, value: {key}")

                            # Декодируем только если это байты
                            if isinstance(key, bytes):
                                session_id = key.decode('utf-8').replace(self.SESSION_PREFIX, '')
                            else:
                                session_id = str(key).replace(self.SESSION_PREFIX, '')

                            self.logger.debug(f"Checking session for expiration: {session_id}")

                            session = await self.get_session(session_id)

                            if session and not self._is_session_valid(session):
                                self.logger.info(f"Cleaning up expired session: {session_id}")
                                await self.delete_session(session_id)
                                cleaned_count += 1
                            elif session:
                                self.logger.debug(f"Session {session_id} is still valid")

                        except Exception as key_error:
                            self.logger.error(f"Error processing session key {key}: {key_error}")
                            continue

                    self.logger.info(f"Cleaned up {cleaned_count} expired sessions from Redis")

                except Exception as e:
                    self.logger.error(f"Failed to cleanup expired sessions from Redis: {e}")
                    self.logger.error(f"Error type: {type(e)}")
                    import traceback
                    self.logger.error(f"Traceback: {traceback.format_exc()}")

            # Очистка локального кэша
            if self.local_cache:
                self.local_cache._cleanup_expired()
                self.logger.info("Cleaned up expired sessions from local cache")

            return cleaned_count

        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
            self.logger.error(f"Error type: {type(e)}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return 0

    async def initialize(self):
        """Инициализация Redis кластера"""
        if self.redis_healthy and settings.is_redis_cluster:
            try:
                self.logger.info("Redis cluster configuration completed")
                self.logger.info("Redis client will be initialized on first operation")

            except Exception as e:
                self.logger.error(f"Redis cluster initialization setup failed: {e}")
                # Не прерываем работу, просто продолжаем с текущим состоянием

    async def cleanup(self):
        """Очистка ресурсов и закрытие соединений"""
        try:
            if self.redis_client:
                # Пытаемся закрыть соединение, если возможно
                try:
                    import asyncio
                    if hasattr(self.redis_client, 'close'):
                        if asyncio.iscoroutinefunction(self.redis_client.close):
                            await self.redis_client.close()
                        else:
                            # Для синхронной версии используем executor
                            loop = asyncio.get_event_loop()
                            await loop.run_in_executor(None, self.redis_client.close)
                        self.logger.info("Redis connection closed successfully")
                    else:
                        self.logger.info("No explicit close method available for Redis client")
                except Exception as close_error:
                    self.logger.warning(f"Error closing Redis connection: {close_error}")

        except Exception as e:
            self.logger.error(f"Error during Redis cleanup: {e}")
