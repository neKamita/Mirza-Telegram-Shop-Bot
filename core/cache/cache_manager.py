"""
Унифицированный менеджер кеширования для всех сервисов приложения

Предоставляет унифицированный интерфейс для инициализации и работы с Redis кешем
в различных частях приложения (webhook сервисы, telegram bot и т.д.)
"""

import logging
from typing import Dict, Any, Optional, Union
from .redis_client import RedisClient, RedisConfig, create_single_redis_client, create_cluster_redis_client
from .exceptions import CacheConnectionError, CacheTimeoutError, CacheClusterError

logger = logging.getLogger(__name__)


class CacheInitializationError(Exception):
    """Ошибка инициализации кеша"""
    pass


class CacheManager:
    """
    Менеджер кеширования с унифицированной инициализацией Redis

    Обеспечивает:
    - Унифицированную инициализацию Redis для всех сервисов
    - Правильную обработку ошибок
    - Валидацию настроек
    - Поддержку как кластерного, так и одиночного Redis
    """

    def __init__(self):
        self.redis_client: Optional[RedisClient] = None
        self._cache_services: Dict[str, Any] = {}

    async def initialize_redis(
        self,
        redis_url: Optional[str] = None,
        redis_cluster_nodes: Optional[str] = None,
        redis_password: Optional[str] = None,
        is_redis_cluster: bool = False,
        decode_responses: bool = True,
        **redis_kwargs
    ) -> Dict[str, Any]:
        """
        Унифицированная инициализация Redis для всех сервисов

        Args:
            redis_url: URL для одиночного Redis (redis://host:port/db)
            redis_cluster_nodes: Список узлов кластера через запятую (host:port,host:port)
            redis_password: Пароль Redis
            is_redis_cluster: Флаг использования кластера
            decode_responses: Декодировать ответы в строки
            **redis_kwargs: Дополнительные параметры Redis

        Returns:
            Dict[str, Any]: Словарь с инициализированными сервисами

        Raises:
            CacheInitializationError: При ошибке инициализации
        """
        try:
            # Валидация настроек
            self._validate_redis_settings(
                redis_url=redis_url,
                redis_cluster_nodes=redis_cluster_nodes,
                is_redis_cluster=is_redis_cluster
            )

            # Создание Redis клиента
            if is_redis_cluster:
                cluster_nodes = self._parse_cluster_nodes(redis_cluster_nodes)
                self.redis_client = create_cluster_redis_client(
                    nodes=cluster_nodes,
                    password=redis_password,
                    decode_responses=decode_responses,
                    **redis_kwargs
                )
            else:
                # Парсинг URL для одиночного Redis
                parsed_url = self._parse_redis_url(redis_url)
                self.redis_client = create_single_redis_client(
                    host=parsed_url['host'],
                    port=parsed_url['port'],
                    db=parsed_url.get('db', 0),
                    password=redis_password,
                    decode_responses=decode_responses,
                    **redis_kwargs
                )

            # Подключение к Redis
            connection_success = await self.redis_client.connect()
            if not connection_success:
                raise CacheInitializationError("Failed to connect to Redis")

            # Тестирование подключения
            await self.redis_client.ping()
            logger.info("Redis cache initialized successfully")

            return {
                'redis_client': self.redis_client,
                'status': 'connected'
            }

        except Exception as e:
            error_msg = f"Failed to initialize Redis cache: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise CacheInitializationError(error_msg) from e

    def _validate_redis_settings(
        self,
        redis_url: Optional[str] = None,
        redis_cluster_nodes: Optional[str] = None,
        is_redis_cluster: bool = False
    ) -> None:
        """
        Валидация настроек Redis

        Args:
            redis_url: URL для одиночного Redis
            redis_cluster_nodes: Список узлов кластера
            is_redis_cluster: Флаг использования кластера

        Raises:
            CacheInitializationError: При ошибке валидации
        """
        if is_redis_cluster:
            if not redis_cluster_nodes or not redis_cluster_nodes.strip():
                raise CacheInitializationError(
                    "REDIS_CLUSTER_NODES must be provided when using Redis cluster mode"
                )

            # Проверка формата узлов кластера
            nodes = redis_cluster_nodes.split(",")
            for node in nodes:
                node = node.strip()
                if ":" not in node:
                    raise CacheInitializationError(
                        f"Invalid cluster node format: {node}. Expected format: host:port"
                    )

                try:
                    host, port = node.split(":", 1)
                    int(port)  # Проверка, что порт - число
                except ValueError as e:
                    raise CacheInitializationError(
                        f"Invalid cluster node port in: {node}. Port must be a number"
                    ) from e

        else:
            if not redis_url or not redis_url.strip():
                raise CacheInitializationError(
                    "REDIS_URL must be provided when using single Redis mode"
                )

    def _parse_cluster_nodes(self, cluster_nodes_str: str) -> list:
        """
        Парсинг строки с узлами кластера в список словарей

        Args:
            cluster_nodes_str: Строка вида "host1:port1,host2:port2"

        Returns:
            list: Список словарей с host и port
        """
        nodes = []
        for node_str in cluster_nodes_str.split(","):
            node_str = node_str.strip()
            if node_str:
                host, port_str = node_str.split(":", 1)
                nodes.append({
                    "host": host.strip(),
                    "port": int(port_str.strip())
                })
        return nodes

    def _parse_redis_url(self, redis_url: str) -> dict:
        """
        Парсинг Redis URL

        Args:
            redis_url: URL вида "redis://host:port/db"

        Returns:
            dict: Словарь с host, port, db
        """
        import re
        from urllib.parse import urlparse

        parsed = urlparse(redis_url)

        result = {
            'host': parsed.hostname or 'localhost',
            'port': parsed.port or 6379
        }

        # Извлечение базы данных из пути
        if parsed.path and parsed.path != '/':
            db_match = re.search(r'/(\d+)', parsed.path)
            if db_match:
                result['db'] = int(db_match.group(1))

        return result

    async def create_cache_services(self, redis_client: RedisClient) -> Dict[str, Any]:
        """
        Создание сервисов кеширования

        Args:
            redis_client: Инициализированный Redis клиент

        Returns:
            Dict[str, Any]: Словарь с сервисами кеширования
        """
        from services.cache import UserCache, PaymentCache, SessionCache, RateLimitCache

        cache_services = {}

        try:
            # Создание сервисов кеширования
            cache_services['user_cache'] = UserCache(redis_client)
            cache_services['payment_cache'] = PaymentCache(redis_client)
            cache_services['session_cache'] = SessionCache(redis_client)
            cache_services['rate_limit_cache'] = RateLimitCache(redis_client)

            logger.info("Cache services created successfully")
            return cache_services

        except Exception as e:
            logger.error(f"Failed to create cache services: {e}")
            raise CacheInitializationError(f"Cache services creation failed: {str(e)}") from e

    async def close(self) -> None:
        """Закрытие соединений"""
        if self.redis_client:
            await self.redis_client.disconnect()

        for service_name, service in self._cache_services.items():
            if hasattr(service, 'close'):
                try:
                    await service.close()
                except Exception as e:
                    logger.error(f"Error closing {service_name}: {e}")


# Глобальный экземпляр для использования в приложении
cache_manager = CacheManager()


async def initialize_cache_services(
    redis_url: Optional[str] = None,
    redis_cluster_nodes: Optional[str] = None,
    redis_password: Optional[str] = None,
    is_redis_cluster: bool = False,
    decode_responses: bool = True,
    **redis_kwargs
) -> Dict[str, Any]:
    """
    Унифицированная функция инициализации Redis кеша для всех сервисов

    Эта функция должна использоваться во всех частях приложения для инициализации Redis.

    Args:
        redis_url: URL для одиночного Redis (redis://host:port/db)
        redis_cluster_nodes: Список узлов кластера через запятую (host:port,host:port)
        redis_password: Пароль Redis
        is_redis_cluster: Флаг использования кластера
        decode_responses: Декодировать ответы в строки
        **redis_kwargs: Дополнительные параметры Redis

    Returns:
        Dict[str, Any]: Словарь с инициализированными сервисами

    Raises:
        CacheInitializationError: При ошибке инициализации

    Example:
        # Для одиночного Redis
        cache_services = await initialize_cache_services(
            redis_url="redis://localhost:6379/0",
            redis_password="password"
        )

        # Для Redis кластера
        cache_services = await initialize_cache_services(
            redis_cluster_nodes="redis-node-1:7379,redis-node-2:7380",
            redis_password="password",
            is_redis_cluster=True
        )
    """
    global cache_manager

    # Инициализация Redis
    redis_result = await cache_manager.initialize_redis(
        redis_url=redis_url,
        redis_cluster_nodes=redis_cluster_nodes,
        redis_password=redis_password,
        is_redis_cluster=is_redis_cluster,
        decode_responses=decode_responses,
        **redis_kwargs
    )

    # Создание сервисов кеширования
    cache_services = await cache_manager.create_cache_services(redis_result['redis_client'])

    return {
        **redis_result,
        **cache_services
    }