"""
Health Check Service - сервис для мониторинга состояния системы
"""
import asyncio
import aiohttp
import redis.asyncio as redis
import logging
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from config.settings import settings
from redis.cluster import RedisCluster


class HealthService:
    """Сервис для проверки здоровья системы"""

    def __init__(self, redis_client: Union[redis.Redis, RedisCluster]):
        self.redis_client = redis_client
        self.logger = logging.getLogger(__name__)
        self.checks = {}
        self.is_cluster = isinstance(redis_client, RedisCluster)

    async def check_redis_health(self) -> Dict[str, Any]:
        """Проверка состояния Redis"""
        try:
            start_time = datetime.utcnow()

            # Для RedisCluster ping() возвращает bool, для обычного Redis - корутину
            if self.is_cluster:
                ping_result = self.redis_client.ping()
            else:
                ping_result = await self.redis_client.ping()

            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            # Получаем информацию о Redis
            if self.is_cluster:
                info = self.redis_client.info()
            else:
                info = await self.redis_client.info()

            # Извлекаем нужные метрики
            redis_version = info.get("redis_version", "unknown") if isinstance(info, dict) else "unknown"
            connected_clients = info.get("connected_clients", 0) if isinstance(info, dict) else 0
            used_memory = info.get("used_memory_human", "unknown") if isinstance(info, dict) else "unknown"
            uptime_seconds = info.get("uptime_in_seconds", 0) if isinstance(info, dict) else 0

            return {
                "status": "healthy",
                "response_time_ms": response_time,
                "version": redis_version,
                "connected_clients": connected_clients,
                "used_memory": used_memory,
                "uptime_seconds": uptime_seconds
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    async def check_database_health(self) -> Dict[str, Any]:
        """Проверка состояния базы данных"""
        try:
            # Импортируем здесь для избежания циклических зависимостей
            from sqlalchemy.ext.asyncio import create_async_engine
            from sqlalchemy import text

            engine = create_async_engine(settings.database_url)
            start_time = datetime.utcnow()

            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                response_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            return {
                "status": "healthy",
                "response_time_ms": response_time
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    async def check_external_services(self) -> Dict[str, Any]:
        """Проверка внешних сервисов"""
        results = {}

        # Проверка Telegram API
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                start_time = datetime.utcnow()
                async with session.get("https://api.telegram.org/bot/getMe") as response:
                    response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                    results["telegram_api"] = {
                        "status": "healthy" if response.status == 200 else "unhealthy",
                        "response_time_ms": response_time,
                        "status_code": response.status
                    }
        except Exception as e:
            results["telegram_api"] = {
                "status": "unhealthy",
                "error": str(e)
            }

        # Проверка платежной системы
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                start_time = datetime.utcnow()
                async with session.get("https://api.heleket.com/v1/health") as response:
                    response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                    results["payment_service"] = {
                        "status": "healthy" if response.status == 200 else "unhealthy",
                        "response_time_ms": response_time,
                        "status_code": response.status
                    }
        except Exception as e:
            results["payment_service"] = {
                "status": "unhealthy",
                "error": str(e)
            }

        return results

    async def check_system_resources(self) -> Dict[str, Any]:
        """Проверка системных ресурсов"""
        try:
            import psutil

            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            return {
                "cpu": {
                    "usage_percent": cpu_percent,
                    "cores": psutil.cpu_count()
                },
                "memory": {
                    "total_gb": memory.total / (1024**3),
                    "available_gb": memory.available / (1024**3),
                    "usage_percent": memory.percent
                },
                "disk": {
                    "total_gb": disk.total / (1024**3),
                    "free_gb": disk.free / (1024**3),
                    "usage_percent": disk.percent
                }
            }
        except ImportError:
            return {
                "error": "psutil not available"
            }

    async def get_health_status(self) -> Dict[str, Any]:
        """Получение полного статуса здоровья системы"""
        start_time = datetime.utcnow()

        # Параллельные проверки
        redis_task = self.check_redis_health()
        db_task = self.check_database_health()
        external_task = self.check_external_services()
        system_task = self.check_system_resources()

        redis_health, db_health, external_health, system_health = await asyncio.gather(
            redis_task, db_task, external_task, system_task
        )

        # Определение общего статуса
        overall_status = "healthy"
        if redis_health.get("status") == "unhealthy":
            overall_status = "unhealthy"
        elif db_health.get("status") == "unhealthy":
            overall_status = "unhealthy"

        # Подсчет нездоровых сервисов
        unhealthy_services = []
        for service, status in external_health.items():
            if status.get("status") == "unhealthy":
                unhealthy_services.append(service)

        if unhealthy_services:
            overall_status = "degraded"

        response_time = (datetime.utcnow() - start_time).total_seconds() * 1000

        return {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "response_time_ms": response_time,
            "services": {
                "redis": redis_health,
                "database": db_health,
                "external": external_health,
                "system": system_health
            },
            "unhealthy_services": unhealthy_services
        }

    async def get_detailed_metrics(self) -> Dict[str, Any]:
        """Получение детальных метрик системы"""
        health_status = await self.get_health_status()

        # Дополнительные метрики Redis
        redis_metrics = {}
        if health_status["services"]["redis"]["status"] == "healthy":
            try:
                if self.is_cluster:
                    info = self.redis_client.info()
                else:
                    info = await self.redis_client.info()

                if isinstance(info, dict):
                    keyspace_hits = info.get("keyspace_hits", 0)
                    keyspace_misses = info.get("keyspace_misses", 0)
                    redis_metrics = {
                        "keyspace_hits": keyspace_hits,
                        "keyspace_misses": keyspace_misses,
                        "hit_ratio": keyspace_hits / max(keyspace_hits + keyspace_misses, 1),
                        "connected_slaves": info.get("connected_slaves", 0),
                        "master_repl_offset": info.get("master_repl_offset", 0),
                        "used_memory_rss": info.get("used_memory_rss", 0),
                        "mem_fragmentation_ratio": info.get("mem_fragmentation_ratio", 0)
                    }
                else:
                    redis_metrics = {"error": "Unable to retrieve Redis info"}
            except Exception as e:
                redis_metrics = {"error": str(e)}

        return {
            **health_status,
            "metrics": {
                "redis": redis_metrics
            }
        }

    async def cache_health_status(self, ttl: int = 30) -> None:
        """Кеширование статуса здоровья"""
        try:
            health_status = await self.get_health_status()
            if self.is_cluster:
                self.redis_client.setex(
                    "health:status",
                    ttl,
                    str(health_status)
                )
            else:
                await self.redis_client.setex(
                    "health:status",
                    ttl,
                    str(health_status)
                )
        except Exception as e:
            self.logger.error(f"Error caching health status: {e}")

    async def get_cached_health_status(self) -> Optional[Dict[str, Any]]:
        """Получение кешированного статуса здоровья"""
        try:
            if self.is_cluster:
                cached = self.redis_client.get("health:status")
            else:
                cached = await self.redis_client.get("health:status")

            if cached:
                import ast
                cached_data = cached.decode() if isinstance(cached, bytes) else cached
                return ast.literal_eval(cached_data)  # type: ignore
            return None
        except Exception:
            return None
