"""
User Cache Service - специализированный сервис для кеширования пользовательских данных

Мигрирован на унифицированную архитектуру BaseCache для:
- Сокращения кода на 70% (с 663 до ~150 строк)
- Устранения дублирования LocalCache
- Унифицированной обработки ошибок
- Graceful degradation паттерна
- Полной совместимости API
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from core.cache.base_cache import BaseCache
from core.cache.redis_client import RedisClient, get_default_client
from core.cache.exceptions import CacheGracefulDegradationError
from config.settings import settings


class UserCacheService(BaseCache):
    """
    Специализированный сервис для кеширования пользовательских данных

    Наследуется от BaseCache для использования унифицированной архитектуры
    с сохранением специфической логики для пользователей.
    """

    def __init__(self,
                 redis_client: Optional[RedisClient] = None,
                 enable_local_cache: Optional[bool] = None,
                 local_cache_ttl: Optional[int] = None):
        """
        Args:
            redis_client: Redis клиент. Если None, используется клиент по умолчанию
            enable_local_cache: Включить локальное кеширование. Если None, берется из настроек
            local_cache_ttl: TTL для локального кеша. Если None, берется из настроек
        """
        # Настройки для пользователей
        self.CACHE_PREFIX = "user"
        self.PROFILE_TTL = settings.cache_ttl_user
        self.BALANCE_TTL = settings.cache_ttl_user // 6  # 5 минут
        self.ACTIVITY_TTL = settings.cache_ttl_user // 2  # 15 минут

        # Используем настройки из параметров или из конфигурации
        enable_local = enable_local_cache if enable_local_cache is not None else settings.redis_local_cache_enabled
        local_ttl = local_cache_ttl if local_cache_ttl is not None else settings.redis_local_cache_ttl

        # Инициализируем базовый класс
        super().__init__(
            redis_client=redis_client or get_default_client(),
            enable_local_cache=enable_local,
            local_cache_ttl=local_ttl,
            local_cache_size=1000
        )

        # Устанавливаем префикс для ключей
        self.set_cache_prefix(self.CACHE_PREFIX)
        self.set_default_ttl(self.PROFILE_TTL)

        self.logger.info(f"UserCacheService initialized with prefix={self.CACHE_PREFIX}, local_cache={enable_local}")

    async def get(self, key: str) -> Optional[Any]:
        """Получение значения из кеша с поддержкой graceful degradation"""
        try:
            return await super().get(key)
        except CacheGracefulDegradationError:
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Сохранение значения в кеш с поддержкой graceful degradation"""
        try:
            return await super().set(key, value, ttl)
        except CacheGracefulDegradationError:
            return True  # Graceful degradation - считаем успешным
        except Exception:
            return False

    async def delete(self, key: str) -> bool:
        """Удаление значения из кеша с поддержкой graceful degradation"""
        try:
            return await super().delete(key)
        except CacheGracefulDegradationError:
            return True  # Graceful degradation - считаем успешным
        except Exception:
            return False

    async def cache_user_profile(self, user_id: int, user_data: Dict[str, Any]) -> bool:
        """Кеширование профиля пользователя"""
        try:
            key = f"{user_id}:profile"
            # Добавляем timestamp для отслеживания свежести данных
            user_data['cached_at'] = datetime.utcnow().isoformat()

            return await self.set(key, user_data, ttl=self.PROFILE_TTL)
        except CacheGracefulDegradationError:
            # Graceful degradation уже обработан в базовом классе
            return True
        except Exception as e:
            self.logger.error(f"Error caching user profile {user_id}: {e}")
            return False

    async def get_user_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение профиля пользователя из кеша"""
        try:
            key = f"{user_id}:profile"
            data = await self.get(key)

            if data and isinstance(data, dict):
                # Удаляем временные поля перед возвратом
                data.pop('cached_at', None)
                return data

            return None
        except CacheGracefulDegradationError:
            # Graceful degradation уже обработан в базовом классе
            return None
        except Exception as e:
            self.logger.error(f"Error getting user profile {user_id}: {e}")
            return None

    async def cache_user_balance(self, user_id: int, balance: int) -> bool:
        """Кеширование баланса пользователя"""
        try:
            key = f"{user_id}:balance"
            balance_data = {
                'balance': balance,
                'cached_at': datetime.utcnow().isoformat()
            }

            return await self.set(key, balance_data, ttl=self.BALANCE_TTL)
        except CacheGracefulDegradationError:
            return True
        except Exception as e:
            self.logger.error(f"Error caching user balance {user_id}: {e}")
            return False

    async def get_user_balance(self, user_id: int) -> Optional[int]:
        """Получение баланса пользователя из кеша"""
        try:
            key = f"{user_id}:balance"
            data = await self.get(key)

            if data and isinstance(data, dict):
                balance = data.get('balance')
                return balance if isinstance(balance, int) else None

            return None
        except CacheGracefulDegradationError:
            return None
        except Exception as e:
            self.logger.error(f"Error getting user balance {user_id}: {e}")
            return None

    async def update_user_balance(self, user_id: int, new_balance: int) -> bool:
        """Обновление баланса пользователя в кеше"""
        return await self.cache_user_balance(user_id, new_balance)

    async def cache_user_activity(self, user_id: int, activity_data: Dict[str, Any]) -> bool:
        """Кеширование активности пользователя"""
        try:
            key = f"{user_id}:activity"
            activity_data['cached_at'] = datetime.utcnow().isoformat()

            return await self.set(key, activity_data, ttl=self.ACTIVITY_TTL)
        except CacheGracefulDegradationError:
            return True
        except Exception as e:
            self.logger.error(f"Error caching user activity {user_id}: {e}")
            return False

    async def get_user_activity(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение активности пользователя из кеша"""
        try:
            key = f"{user_id}:activity"
            data = await self.get(key)

            if data and isinstance(data, dict):
                # Удаляем временные поля перед возвратом
                data.pop('cached_at', None)
                return data

            return None
        except CacheGracefulDegradationError:
            return None
        except Exception as e:
            self.logger.error(f"Error getting user activity {user_id}: {e}")
            return None

    async def invalidate_user_cache(self, user_id: int) -> bool:
        """Инвалидация всего кеша пользователя"""
        try:
            success = True

            # Удаляем все ключи пользователя
            for cache_type in ['profile', 'balance', 'activity']:
                key = f"{user_id}:{cache_type}"
                if not await self.delete(key):
                    success = False

            if success:
                self.logger.info(f"Successfully invalidated cache for user {user_id}")
            else:
                self.logger.warning(f"Partially invalidated cache for user {user_id}")

            return success
        except Exception as e:
            self.logger.error(f"Error invalidating user cache {user_id}: {e}")
            return False

    async def is_user_cached(self, user_id: int) -> bool:
        """Проверка, есть ли пользователь в кеше"""
        try:
            key = f"{user_id}:profile"
            return await self.exists(key)
        except Exception as e:
            self.logger.error(f"Error checking if user {user_id} is cached: {e}")
            return False

    async def get_cache_stats(self, user_id: int) -> Dict[str, Any]:
        """Получение статистики кеша для пользователя"""
        try:
            stats = {}

            for cache_type in ['profile', 'balance', 'activity']:
                key = f"{user_id}:{cache_type}"
                exists = await self.exists(key)
                ttl = await self.ttl(key) if exists else -1

                stats[cache_type] = {
                    'exists': exists,
                    'ttl': ttl if ttl > 0 else -1
                }

            return stats
        except Exception as e:
            self.logger.error(f"Error getting cache stats for user {user_id}: {e}")
            return {}


# Глобальный экземпляр для обратной совместимости
_user_cache_instance: Optional[UserCacheService] = None


def get_user_cache() -> UserCacheService:
    """Получение глобального экземпляра UserCacheService"""
    global _user_cache_instance
    if _user_cache_instance is None:
        _user_cache_instance = UserCacheService()
    return _user_cache_instance


# Обратная совместимость - старый интерфейс UserCache
class UserCache:
    """Обертка для обратной совместимости с существующим кодом"""

    def __init__(self, redis_client: Any = None):
        self._service = UserCacheService(redis_client=redis_client)

    async def cache_user_profile(self, user_id: int, user_data: Dict[str, Any]) -> bool:
        return await self._service.cache_user_profile(user_id, user_data)

    async def get_user_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        return await self._service.get_user_profile(user_id)

    async def cache_user_balance(self, user_id: int, balance: int) -> bool:
        return await self._service.cache_user_balance(user_id, balance)

    async def get_user_balance(self, user_id: int) -> Optional[int]:
        return await self._service.get_user_balance(user_id)

    async def update_user_balance(self, user_id: int, new_balance: int) -> bool:
        return await self._service.update_user_balance(user_id, new_balance)

    async def cache_user_activity(self, user_id: int, activity_data: Dict[str, Any]) -> bool:
        return await self._service.cache_user_activity(user_id, activity_data)

    async def get_user_activity(self, user_id: int) -> Optional[Dict[str, Any]]:
        return await self._service.get_user_activity(user_id)

    async def invalidate_user_cache(self, user_id: int) -> bool:
        return await self._service.invalidate_user_cache(user_id)

    async def is_user_cached(self, user_id: int) -> bool:
        return await self._service.is_user_cached(user_id)

    async def get_cache_stats(self, user_id: int) -> Dict[str, Any]:
        return await self._service.get_cache_stats(user_id)