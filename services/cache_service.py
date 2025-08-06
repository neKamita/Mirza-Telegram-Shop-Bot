"""
Сервис кеширования через Redis
"""
import json
from typing import Any, Optional
import redis.asyncio as redis
from datetime import timedelta


class CacheService:
    """Сервис для работы с Redis кешем"""

    def __init__(self, redis_url: str, db: int = 0):
        self.redis_client = redis.from_url(redis_url, db=db)

    async def get(self, key: str) -> Optional[Any]:
        """Получение значения из кеша"""
        value = await self.redis_client.get(key)
        if value:
            return json.loads(value)
        return None

    async def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Сохранение значения в кеш"""
        try:
            serialized = json.dumps(value, default=str)
            await self.redis_client.setex(key, ttl, serialized)
            return True
        except Exception:
            return False

    async def delete(self, key: str) -> bool:
        """Удаление значения из кеша"""
        try:
            await self.redis_client.delete(key)
            return True
        except Exception:
            return False

    async def exists(self, key: str) -> bool:
        """Проверка существования ключа"""
        return await self.redis_client.exists(key) > 0

    async def close(self):
        """Закрытие соединения"""
        await self.redis_client.close()

    # Методы для специфичных кейсов
    async def cache_user_session(self, user_id: int, data: dict, ttl: int = 1800):
        """Кеширование сессии пользователя"""
        key = f"user_session:{user_id}"
        return await self.set(key, data, ttl)

    async def get_user_session(self, user_id: int) -> Optional[dict]:
        """Получение сессии пользователя"""
        key = f"user_session:{user_id}"
        return await self.get(key)

    async def cache_rate_limit(self, key: str, ttl: int = 60) -> bool:
        """Кеширование rate limit"""
        return await self.set(f"rate_limit:{key}", 1, ttl)

    async def check_rate_limit(self, key: str) -> bool:
        """Проверка rate limit"""
        return await self.exists(f"rate_limit:{key}")
