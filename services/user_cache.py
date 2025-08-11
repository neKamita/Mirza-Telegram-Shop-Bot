"""
User Cache Service - специализированный сервис для кеширования пользовательских данных
"""
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import redis.asyncio as redis
from config.settings import settings


class UserCache:
    """Специализированный сервис для кеширования пользовательских данных"""

    def __init__(self, redis_client: Any):
        self.redis_client = redis_client
        self.logger = logging.getLogger(__name__)
        self.CACHE_PREFIX = "user:"
        self.PROFILE_TTL = settings.cache_ttl_user
        self.BALANCE_TTL = settings.cache_ttl_user // 6  # 5 минут
        self.ACTIVITY_TTL = settings.cache_ttl_user // 2  # 15 минут

    async def cache_user_profile(self, user_id: int, user_data: Dict[str, Any]) -> bool:
        """Кеширование профиля пользователя"""
        try:
            key = f"{self.CACHE_PREFIX}{user_id}:profile"
            # Добавляем timestamp для отслеживания свежести данных
            user_data['cached_at'] = datetime.utcnow().isoformat()
            serialized = json.dumps(user_data, default=str)
            await self.redis_client.setex(key, self.PROFILE_TTL, serialized)
            return True
        except Exception as e:
            self.logger.error(f"Error caching user profile {user_id}: {e}")
            return False

    async def get_user_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение профиля пользователя из кеша"""
        try:
            key = f"{self.CACHE_PREFIX}{user_id}:profile"
            cached_data = await self.redis_client.get(key)
            if cached_data:
                data = json.loads(cached_data)
                # Проверяем свежесть данных
                cached_at = datetime.fromisoformat(data.get('cached_at', ''))
                if datetime.utcnow() - cached_at < timedelta(seconds=self.PROFILE_TTL):
                    # Удаляем временные поля перед возвратом
                    data.pop('cached_at', None)
                    return data
                else:
                    # Данные устарели, удаляем из кеша
                    await self.redis_client.delete(key)
            return None
        except Exception as e:
            self.logger.error(f"Error getting user profile {user_id}: {e}")
            return None

    async def cache_user_balance(self, user_id: int, balance: int) -> bool:
        """Кеширование баланса пользователя"""
        try:
            key = f"{self.CACHE_PREFIX}{user_id}:balance"
            balance_data = {
                'balance': balance,
                'cached_at': datetime.utcnow().isoformat()
            }
            serialized = json.dumps(balance_data, default=str)
            await self.redis_client.setex(key, self.BALANCE_TTL, serialized)
            return True
        except Exception as e:
            self.logger.error(f"Error caching user balance {user_id}: {e}")
            return False

    async def get_user_balance(self, user_id: int) -> Optional[int]:
        """Получение баланса пользователя из кеша"""
        try:
            key = f"{self.CACHE_PREFIX}{user_id}:balance"
            cached_data = await self.redis_client.get(key)
            if cached_data:
                data = json.loads(cached_data)
                # Проверяем свежесть данных
                cached_at = datetime.fromisoformat(data.get('cached_at', ''))
                if datetime.utcnow() - cached_at < timedelta(seconds=self.BALANCE_TTL):
                    return data['balance']
                else:
                    # Данные устарели, удаляем из кеша
                    await self.redis_client.delete(key)
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
        """Кеширование активности пользователя"""
        try:
            key = f"{self.CACHE_PREFIX}{user_id}:activity"
            activity_data['cached_at'] = datetime.utcnow().isoformat()
            serialized = json.dumps(activity_data, default=str)
            await self.redis_client.setex(key, self.ACTIVITY_TTL, serialized)
            return True
        except Exception as e:
            self.logger.error(f"Error caching user activity {user_id}: {e}")
            return False

    async def get_user_activity(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение активности пользователя из кеша"""
        try:
            key = f"{self.CACHE_PREFIX}{user_id}:activity"
            cached_data = await self.redis_client.get(key)
            if cached_data:
                data = json.loads(cached_data)
                # Проверяем свежесть данных
                cached_at = datetime.fromisoformat(data.get('cached_at', ''))
                if datetime.utcnow() - cached_at < timedelta(seconds=self.ACTIVITY_TTL):
                    data.pop('cached_at', None)
                    return data
                else:
                    await self.redis_client.delete(key)
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
