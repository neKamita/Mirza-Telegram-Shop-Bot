"""
Унифицированный Redis клиент для системы кеширования

Поддерживает как одиночный Redis, так и кластер с:
- Автоматическим переподключением
- Connection pooling
- Оптимизированными настройками
- Health checks
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union
import redis.asyncio as redis
from redis.cluster import RedisCluster
from redis.exceptions import RedisError, ConnectionError, TimeoutError
from .exceptions import CacheConnectionError, CacheTimeoutError, CacheClusterError


logger = logging.getLogger(__name__)


@dataclass
class RedisConfig:
    """Конфигурация Redis клиента"""

    # Базовые настройки подключения
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None

    # Настройки кластера
    cluster_mode: bool = False
    cluster_nodes: Optional[List[Dict[str, Union[str, int]]]] = None

    # Connection pool настройки
    max_connections: int = 20
    min_connections: int = 5

    # Таймауты
    socket_connect_timeout: float = 5.0
    socket_timeout: float = 5.0
    socket_read_timeout: float = 5.0

    # Повторные попытки
    retry_on_timeout: bool = True
    max_retries: int = 3
    retry_delay: float = 1.0

    # Health check
    health_check_interval: int = 30

    # SSL настройки
    ssl_enabled: bool = False
    ssl_certfile: Optional[str] = None
    ssl_keyfile: Optional[str] = None

    # Оптимизации
    decode_responses: bool = True
    serializer: Optional[Any] = None

    def __post_init__(self):
        """Валидация конфигурации после инициализации"""
        if self.cluster_mode and not self.cluster_nodes:
            raise ValueError("cluster_nodes must be provided when cluster_mode is True")


class RedisClient:
    """
    Унифицированный Redis клиент с поддержкой кластера

    Features:
    - Автоматическое переподключение
    - Connection pooling
    - Health monitoring
    - Graceful error handling
    - Поддержка кластера и одиночного режима
    """

    def __init__(self, config: RedisConfig):
        """
        Args:
            config: Конфигурация Redis клиента
        """
        self.config = config
        self._client: Optional[Union[redis.Redis, RedisCluster]] = None
        self._lock = asyncio.Lock()
        self._is_connected = False
        self._connection_attempts = 0
        self._last_health_check = 0

        logger.info(f"RedisClient initialized with config: host={config.host}, port={config.port}, cluster={config.cluster_mode}")

    async def connect(self) -> bool:
        """
        Установление соединения с Redis

        Returns:
            bool: True если соединение установлено успешно
        """
        async with self._lock:
            try:
                if self.config.cluster_mode:
                    await self._connect_cluster()
                else:
                    await self._connect_single()

                self._is_connected = True
                self._connection_attempts = 0
                logger.info("Successfully connected to Redis")
                return True

            except Exception as e:
                self._connection_attempts += 1
                logger.error(f"Failed to connect to Redis (attempt {self._connection_attempts}): {e}")
                self._is_connected = False
                return False

    async def _connect_single(self) -> None:
        """Подключение к одиночному Redis"""
        connection_params = {
            'host': self.config.host,
            'port': self.config.port,
            'db': self.config.db,
            'password': self.config.password,
            'decode_responses': self.config.decode_responses,
            'socket_connect_timeout': self.config.socket_connect_timeout,
            'socket_timeout': self.config.socket_timeout,
            'retry_on_timeout': self.config.retry_on_timeout,
            'max_connections': self.config.max_connections,
            'health_check_interval': self.config.health_check_interval,
        }

        if self.config.ssl_enabled:
            connection_params.update({
                'ssl': True,
                'ssl_certfile': self.config.ssl_certfile,
                'ssl_keyfile': self.config.ssl_keyfile,
            })

        self._client = redis.Redis(**connection_params)

        # Тестовое подключение
        await self._client.ping()

    async def _connect_cluster(self) -> None:
        """Подключение к Redis кластеру"""
        if not self.config.cluster_nodes:
            raise CacheClusterError("No cluster nodes configured")

        connection_params = {
            'startup_nodes': self.config.cluster_nodes,
            'password': self.config.password,
            'decode_responses': self.config.decode_responses,
            'socket_connect_timeout': self.config.socket_connect_timeout,
            'socket_timeout': self.config.socket_timeout,
            'retry_on_timeout': self.config.retry_on_timeout,
            'max_connections': self.config.max_connections,
            'health_check_interval': self.config.health_check_interval,
        }

        if self.config.ssl_enabled:
            connection_params.update({
                'ssl': True,
                'ssl_certfile': self.config.ssl_certfile,
                'ssl_keyfile': self.config.ssl_keyfile,
            })

        self._client = RedisCluster(**connection_params)

        # Тестовое подключение
        await self._client.ping()

    async def disconnect(self) -> None:
        """Отключение от Redis"""
        async with self._lock:
            if self._client:
                if hasattr(self._client, 'close'):
                    await self._client.close()
                self._client = None
            self._is_connected = False
            logger.info("Disconnected from Redis")

    async def execute_operation(self, operation: str, *args, **kwargs) -> Any:
        """
        Выполнение Redis операции с обработкой ошибок и повторными попытками

        Args:
            operation: Название операции (get, set, setex, delete и т.д.)
            *args: Аргументы операции
            **kwargs: Именованные аргументы операции

        Returns:
            Результат операции

        Raises:
            CacheConnectionError: При проблемах с подключением
            CacheTimeoutError: При таймаутах
            CacheClusterError: При ошибках кластера
        """
        if not self._client:
            raise CacheConnectionError("Redis client is not connected")

        # Health check перед операцией
        await self._ensure_healthy_connection()

        last_error = None
        for attempt in range(self.config.max_retries + 1):
            try:
                # Получаем метод Redis клиента
                method = getattr(self._client, operation)

                # Проверяем, является ли метод асинхронным
                if asyncio.iscoroutinefunction(method):
                    result = await method(*args, **kwargs)
                else:
                    # Для синхронного метода используем asyncio.to_thread
                    def wrapped_method():
                        return method(*args, **kwargs)

                    result = await asyncio.to_thread(wrapped_method)

                return result

            except TimeoutError as e:
                last_error = e
                if attempt < self.config.max_retries:
                    logger.warning(f"Redis operation {operation} timed out (attempt {attempt + 1}), retrying...")
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                else:
                    raise CacheTimeoutError(
                        f"Redis operation {operation} timed out after {self.config.max_retries + 1} attempts",
                        operation=operation,
                        timeout=self.config.socket_timeout
                    ) from e

            except ConnectionError as e:
                last_error = e
                self._is_connected = False
                if attempt < self.config.max_retries:
                    logger.warning(f"Redis connection lost (attempt {attempt + 1}), reconnecting...")
                    await self.connect()
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                else:
                    raise CacheConnectionError(
                        f"Redis connection failed after {self.config.max_retries + 1} attempts",
                        host=self.config.host,
                        port=self.config.port
                    ) from e

            except Exception as e:
                # Обработка специфических ошибок Redis кластера
                if "CLUSTER" in str(e) or "MOVED" in str(e):
                    last_error = e
                    if attempt < self.config.max_retries:
                        logger.warning(f"Redis cluster error (attempt {attempt + 1}): {e}")
                        await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                    else:
                        raise CacheClusterError(
                            f"Redis cluster operation failed: {e}",
                            cluster_info=self.config.cluster_nodes
                        ) from e
                else:
                    # Для других ошибок не делаем повторные попытки
                    logger.error(f"Redis operation {operation} failed: {e}")
                    raise

        # Если дошли сюда, значит все попытки исчерпаны
        raise last_error

    async def _ensure_healthy_connection(self) -> None:
        """Проверка здоровья соединения"""
        if not self._is_connected:
            await self.connect()
            return

        # Периодический health check
        current_time = asyncio.get_event_loop().time()
        if current_time - self._last_health_check > self.config.health_check_interval:
            try:
                await self._client.ping()
                self._last_health_check = current_time
            except Exception as e:
                logger.warning(f"Health check failed: {e}")
                self._is_connected = False
                await self.connect()

    async def get_connection_info(self) -> Dict[str, Any]:
        """Получение информации о соединении"""
        return {
            'is_connected': self._is_connected,
            'host': self.config.host,
            'port': self.config.port,
            'cluster_mode': self.config.cluster_mode,
            'connection_attempts': self._connection_attempts,
            'client_type': type(self._client).__name__ if self._client else None
        }

    async def ping(self) -> bool:
        """Проверка доступности Redis"""
        try:
            if self._client:
                await self._client.ping()
                return True
            return False
        except Exception:
            return False

    # Context manager support
    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    def __str__(self) -> str:
        return f"RedisClient(host={self.config.host}, port={self.config.port}, cluster={self.config.cluster_mode})"


# Фабричные функции для создания клиентов
def create_single_redis_client(
    host: str = "localhost",
    port: int = 6379,
    db: int = 0,
    password: Optional[str] = None,
    **kwargs
) -> RedisClient:
    """Создание клиента для одиночного Redis"""
    config = RedisConfig(
        host=host,
        port=port,
        db=db,
        password=password,
        cluster_mode=False,
        **kwargs
    )
    return RedisClient(config)


def create_cluster_redis_client(
    nodes: List[Dict[str, Union[str, int]]],
    password: Optional[str] = None,
    **kwargs
) -> RedisClient:
    """Создание клиента для Redis кластера"""
    config = RedisConfig(
        cluster_mode=True,
        cluster_nodes=nodes,
        password=password,
        **kwargs
    )
    return RedisClient(config)


# Глобальный клиент для использования по умолчанию
_default_client: Optional[RedisClient] = None


def get_default_client() -> RedisClient:
    """Получение глобального Redis клиента"""
    global _default_client
    if _default_client is None:
        _default_client = create_single_redis_client()
    return _default_client


def set_default_client(client: RedisClient) -> None:
    """Установка глобального Redis клиента"""
    global _default_client
    _default_client = client