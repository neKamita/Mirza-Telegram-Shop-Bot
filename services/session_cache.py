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
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type, retry_if_exception, before_sleep_log
)

from config.settings import settings
from services.circuit_breaker import circuit_manager, CircuitConfigs


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

        self._setup_redis_client()

    def _setup_redis_client(self):
        """Настройка Redis клиента с оптимизированными параметрами"""
        if self.redis_client is None:
            try:
                if settings.is_redis_cluster:
                    # Конфигурация для Redis кластера
                    self.redis_client = RedisCluster(
                        host=settings.redis_cluster_url.split('://')[1].split(':')[0],
                        port=int(settings.redis_cluster_url.split(':')[-1]),
                        password=settings.redis_password,
                        decode_responses=True,
                        socket_timeout=settings.redis_socket_timeout,
                        socket_connect_timeout=settings.redis_socket_connect_timeout,
                        retry_on_timeout=settings.redis_retry_on_timeout,
                        max_connections=settings.redis_max_connections,
                        health_check_interval=settings.redis_health_check_interval,
                        skip_full_coverage_check=True  # Для производительности
                    )
                else:
                    # Конфигурация для одиночного Redis
                    self.redis_client = redis.Redis(
                        host=settings.redis_url.split('://')[1].split(':')[0],
                        port=int(settings.redis_url.split(':')[-1]),
                        password=settings.redis_password,
                        db=settings.redis_db,
                        decode_responses=True,
                        socket_timeout=settings.redis_socket_timeout,
                        socket_connect_timeout=settings.redis_socket_connect_timeout,
                        retry_on_timeout=settings.redis_retry_on_timeout,
                        max_connections=settings.redis_max_connections,
                        health_check_interval=settings.redis_health_check_interval
                    )

                self.logger.info("Redis client configured successfully")

            except Exception as e:
                self.logger.error(f"Failed to configure Redis client: {e}")
                self.redis_healthy = False
                self.last_redis_error = e

    @retry(
        stop=stop_after_attempt(settings.redis_retry_attempts),
        wait=wait_exponential(
            multiplier=settings.redis_retry_backoff_factor,
            min=1,
            max=10
        ),
        retry=retry_if_exception(lambda e: isinstance(e, SessionCache.RETRIABLE_EXCEPTIONS)),
        before_sleep=before_sleep_log(logging.getLogger(__name__), logging.WARNING),
        reraise=True
    )
    async def _execute_redis_operation(self, operation: str, *args, **kwargs) -> Any:
        """Выполнение Redis операции с retry и Circuit Breaker"""

        if not self.redis_healthy:
            self.logger.warning("Redis is not healthy, using local cache fallback")
            raise ConnectionError("Redis is not available")

        # Оборачиваем в Circuit Breaker
        try:
            result = await self.circuit_breaker.call(
                getattr(self.redis_client, operation),
                *args, **kwargs
            )

            # Обновляем статистику при успехе
            self.stats['redis_hits'] += 1
            return result

        except self.CRITICAL_EXCEPTIONS as e:
            # Критические ошибки - отключаем Redis
            self._handle_critical_redis_error(e)
            raise

        except Exception as e:
            # Прочие ошибки
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
                    await self._execute_redis_operation('setex', session_key, self.SESSION_TTL, serialized)

                    # Индексируем сессии по пользователю
                    user_sessions_key = f"user_sessions:{user_id}"
                    await self._execute_redis_operation('lpush', user_sessions_key, session_id)
                    await self._execute_redis_operation('expire', user_sessions_key, self.SESSION_TTL)

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

        # Сначала пробуем локальный кэш
        if self.local_cache:
            local_data = self.local_cache.get(cache_key)
            if local_data:
                self.stats['local_cache_hits'] += 1
                self.logger.debug(f"Session {session_id} found in local cache")
                return local_data
            self.stats['local_cache_misses'] += 1

        # Если Redis доступен, пробуем Redis
        if self.redis_healthy:
            try:
                session_key = f"{self.SESSION_PREFIX}{session_id}"
                cached_data = await self._execute_redis_operation('get', session_key)

                if cached_data:
                    session_data = json.loads(cached_data)

                    # Проверяем активность и свежесть
                    if session_data.get('is_active') and self._is_session_valid(session_data):
                        # Обновляем время последней активности
                        session_data['last_activity'] = datetime.utcnow().isoformat()
                        await self.update_session(session_id, session_data)

                        # Кэшируем в локальном хранилище
                        if self.local_cache:
                            self.local_cache.set(cache_key, session_data)

                        return session_data
                    else:
                        # Сессия неактивна или устарела
                        await self.delete_session(session_id)

                return None

            except Exception as e:
                self.logger.warning(f"Failed to get session from Redis, using local cache: {e}")
                # При ошибке Redis пробуем локальный кэш еще раз
                if self.local_cache:
                    return self.local_cache.get(cache_key)

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
            await self._execute_redis_operation('lrem', user_sessions_key, 0, session_id)

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
                session_ids = await self._execute_redis_operation('lrange', user_sessions_key, 0, -1)

                for session_id_bytes in session_ids:
                    session_id = session_id_bytes.decode('utf-8')
                    session = await self.get_session(session_id)
                    if session:
                        sessions.append(session)

                return sessions

            except Exception as e:
                self.logger.warning(f"Failed to get user sessions from Redis, using local cache: {e}")

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
                    await self.redis_client.ping()
                    health_status['redis_status'] = 'connected'
                except Exception as e:
                    health_status['redis_status'] = 'error'
                    health_status['last_error'] = str(e)
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

                    for key in session_keys:
                        session_id = key.decode('utf-8').replace(self.SESSION_PREFIX, '')
                        session = await self.get_session(session_id)

                        if session and not self._is_session_valid(session):
                            await self.delete_session(session_id)
                            cleaned_count += 1

                    self.logger.info(f"Cleaned up {cleaned_count} expired sessions from Redis")

                except Exception as e:
                    self.logger.warning(f"Failed to cleanup expired sessions from Redis: {e}")

            # Очистка локального кэша
            if self.local_cache:
                self.local_cache._cleanup_expired()
                self.logger.info("Cleaned up expired sessions from local cache")

            return cleaned_count

        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
            return 0
