"""
Продвинутый Rate Limiter для масштабируемых приложений с 1000+ пользователей
"""
import logging
import time
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum

from services.rate_limit_cache import RateLimitCache
from config.settings import settings


class UserType(Enum):
    """Типы пользователей для дифференцированного rate limiting"""
    NEW = "new"           # Новые пользователи (первые 24 часа)
    REGULAR = "regular"   # Обычные пользователи
    PREMIUM = "premium"   # Премиум пользователи
    SUSPICIOUS = "suspicious"  # Подозрительные пользователи


class AdvancedRateLimiter:
    """
    Продвинутый rate limiter с поддержкой:
    - Многоуровневых лимитов (персональные, глобальные, burst)
    - Дифференциации пользователей
    - Адаптивных лимитов
    - Защиты от DDoS
    """
    
    def __init__(self, rate_limit_cache: RateLimitCache):
        self.rate_limit_cache = rate_limit_cache
        self.logger = logging.getLogger(__name__)
        
        # Кеш для определения типов пользователей
        self._user_type_cache: Dict[int, Tuple[UserType, datetime]] = {}
        
    async def check_rate_limit(self, user_id: int, action: str, 
                              user_type: Optional[UserType] = None) -> Tuple[bool, Dict[str, Any]]:
        """
        Комплексная проверка rate limit с учетом всех факторов
        
        Args:
            user_id: ID пользователя
            action: Тип действия (message, operation, payment)
            user_type: Тип пользователя (определяется автоматически если не указан)
            
        Returns:
            Tuple[bool, dict]: (разрешено, информация о лимитах)
        """
        try:
            # Определяем тип пользователя
            if user_type is None:
                user_type = await self._determine_user_type(user_id)
            
            # Получаем лимиты для данного типа пользователя и действия
            limits = self._get_limits_for_user_type(user_type, action)
            
            # Проверяем burst лимиты (кратковременные всплески)
            burst_allowed, burst_info = await self._check_burst_limit(user_id, action, limits)
            if not burst_allowed:
                return False, {
                    "reason": "burst_limit_exceeded",
                    "user_type": user_type.value,
                    "limits": limits,
                    "burst_info": burst_info
                }
            
            # Проверяем персональные лимиты
            personal_allowed = await self.rate_limit_cache.check_user_rate_limit(
                user_id, action, limits["personal"], 60
            )
            if not personal_allowed:
                return False, {
                    "reason": "personal_limit_exceeded",
                    "user_type": user_type.value,
                    "limits": limits
                }
            
            # Проверяем глобальные лимиты (защита от DDoS)
            global_allowed = await self.rate_limit_cache.check_global_rate_limit(
                action, limits["global"], 60
            )
            if not global_allowed:
                return False, {
                    "reason": "global_limit_exceeded",
                    "user_type": user_type.value,
                    "limits": limits
                }
            
            return True, {
                "user_type": user_type.value,
                "limits": limits
            }
            
        except Exception as e:
            self.logger.error(f"Error in advanced rate limit check: {e}")
            return True, {"error": str(e)}  # Fail open для надежности
    
    async def _determine_user_type(self, user_id: int) -> UserType:
        """
        Определение типа пользователя с кешированием
        """
        # Проверяем кеш
        if user_id in self._user_type_cache:
            user_type, cached_at = self._user_type_cache[user_id]
            # Кеш действителен 5 минут
            if datetime.now() - cached_at < timedelta(minutes=5):
                return user_type
        
        # Определяем тип пользователя
        user_type = await self._classify_user(user_id)
        
        # Кешируем результат
        self._user_type_cache[user_id] = (user_type, datetime.now())
        
        return user_type
    
    async def _classify_user(self, user_id: int) -> UserType:
        """
        Классификация пользователя по типу
        """
        try:
            # Проверяем, является ли пользователь новым
            # (в реальном проекте это должно проверяться через базу данных)
            user_creation_key = f"user_created:{user_id}"
            user_created = await self.rate_limit_cache._execute_redis_operation('get', user_creation_key)
            
            if not user_created:
                # Новый пользователь - устанавливаем метку
                await self.rate_limit_cache._execute_redis_operation(
                    'setex', user_creation_key, 
                    settings.rate_limit_new_user_hours * 3600, 
                    str(int(time.time()))
                )
                return UserType.NEW
            
            # Проверяем, прошло ли время ограничений для новых пользователей
            created_timestamp = int(user_created)
            if time.time() - created_timestamp < settings.rate_limit_new_user_hours * 3600:
                return UserType.NEW
            
            # Проверяем премиум статус
            # (в реальном проекте это должно проверяться через базу данных)
            premium_key = f"user_premium:{user_id}"
            is_premium = await self.rate_limit_cache._execute_redis_operation('get', premium_key)
            if is_premium:
                return UserType.PREMIUM
            
            # Проверяем подозрительную активность
            suspicious_key = f"user_suspicious:{user_id}"
            is_suspicious = await self.rate_limit_cache._execute_redis_operation('get', suspicious_key)
            if is_suspicious:
                return UserType.SUSPICIOUS
            
            return UserType.REGULAR
            
        except Exception as e:
            self.logger.error(f"Error classifying user {user_id}: {e}")
            return UserType.REGULAR  # По умолчанию обычный пользователь
    
    def _get_limits_for_user_type(self, user_type: UserType, action: str) -> Dict[str, int]:
        """
        Получение лимитов для конкретного типа пользователя и действия
        """
        # Базовые лимиты
        base_limits = {
            "message": {
                "personal": settings.rate_limit_user_messages,
                "global": settings.rate_limit_global_messages,
                "burst": settings.rate_limit_burst_messages
            },
            "operation": {
                "personal": settings.rate_limit_user_operations,
                "global": settings.rate_limit_global_operations,
                "burst": settings.rate_limit_burst_operations
            },
            "payment": {
                "personal": settings.rate_limit_user_payments,
                "global": settings.rate_limit_global_payments,
                "burst": 2  # Максимум 2 платежа за 10 секунд
            }
        }
        
        limits = base_limits.get(action, base_limits["message"]).copy()
        
        # Модификация лимитов в зависимости от типа пользователя
        if user_type == UserType.NEW:
            # Пониженные лимиты для новых пользователей
            limits["personal"] = min(limits["personal"], settings.rate_limit_new_user_messages if action == "message" else settings.rate_limit_new_user_operations)
            limits["burst"] = max(1, limits["burst"] // 2)
            
        elif user_type == UserType.PREMIUM:
            # Повышенные лимиты для премиум пользователей
            multiplier = settings.rate_limit_premium_multiplier
            limits["personal"] = int(limits["personal"] * multiplier)
            limits["burst"] = int(limits["burst"] * multiplier)
            
        elif user_type == UserType.SUSPICIOUS:
            # Пониженные лимиты для подозрительных пользователей
            limits["personal"] = max(1, limits["personal"] // 4)
            limits["burst"] = 1
        
        return limits
    
    async def _check_burst_limit(self, user_id: int, action: str, limits: Dict[str, int]) -> Tuple[bool, Dict[str, Any]]:
        """
        Проверка burst лимитов (кратковременные всплески активности)
        """
        try:
            burst_key = f"burst:{user_id}:{action}"
            current_time = int(time.time())
            window = settings.rate_limit_burst_window
            
            # Получаем записи за последние window секунд
            await self.rate_limit_cache._cleanup_old_entries(burst_key, current_time, window)
            count = await self.rate_limit_cache._execute_redis_operation('llen', burst_key)
            
            burst_info = {
                "current_count": count,
                "limit": limits["burst"],
                "window": window,
                "remaining": max(0, limits["burst"] - count)
            }
            
            if count >= limits["burst"]:
                return False, burst_info
            
            # Добавляем новую запись
            await self.rate_limit_cache._execute_redis_operation('lpush', burst_key, str(current_time))
            await self.rate_limit_cache._execute_redis_operation('expire', burst_key, window)
            
            return True, burst_info
            
        except Exception as e:
            self.logger.error(f"Error checking burst limit: {e}")
            return True, {"error": str(e)}
    
    async def mark_user_as_premium(self, user_id: int, duration_hours: int = 24 * 30) -> bool:
        """
        Отметить пользователя как премиум
        """
        try:
            premium_key = f"user_premium:{user_id}"
            await self.rate_limit_cache._execute_redis_operation(
                'setex', premium_key, duration_hours * 3600, "1"
            )
            # Очищаем кеш типа пользователя
            if user_id in self._user_type_cache:
                del self._user_type_cache[user_id]
            return True
        except Exception as e:
            self.logger.error(f"Error marking user {user_id} as premium: {e}")
            return False
    
    async def mark_user_as_suspicious(self, user_id: int, duration_hours: int = 24) -> bool:
        """
        Отметить пользователя как подозрительного
        """
        try:
            suspicious_key = f"user_suspicious:{user_id}"
            await self.rate_limit_cache._execute_redis_operation(
                'setex', suspicious_key, duration_hours * 3600, "1"
            )
            # Очищаем кеш типа пользователя
            if user_id in self._user_type_cache:
                del self._user_type_cache[user_id]
            return True
        except Exception as e:
            self.logger.error(f"Error marking user {user_id} as suspicious: {e}")
            return False
    
    async def get_user_rate_limit_status(self, user_id: int) -> Dict[str, Any]:
        """
        Получение полной информации о rate limit статусе пользователя
        """
        try:
            user_type = await self._determine_user_type(user_id)
            
            status = {
                "user_id": user_id,
                "user_type": user_type.value,
                "limits": {},
                "current_usage": {}
            }
            
            for action in ["message", "operation", "payment"]:
                limits = self._get_limits_for_user_type(user_type, action)
                status["limits"][action] = limits
                
                # Получаем текущее использование
                info = await self.rate_limit_cache.get_rate_limit_info(
                    str(user_id), action, window=60, limit=limits["personal"]
                )
                status["current_usage"][action] = info
            
            return status
            
        except Exception as e:
            self.logger.error(f"Error getting rate limit status for user {user_id}: {e}")
            return {"error": str(e)}