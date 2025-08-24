"""
Payment Cache Service - миграция на новую единую архитектуру кеширования BaseCache
Сокращение с 727 строк до ~180-200 строк с сохранением полной функциональности
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from core.cache.base_cache import BaseCache
from core.cache.redis_client import RedisClient, create_single_redis_client
from config.settings import settings


logger = logging.getLogger(__name__)


class PaymentCacheService(BaseCache):
    """
    Сервис кеширования платежных данных с наследованием от BaseCache
    Обеспечивает автоматическую сериализацию, graceful degradation и метрики
    """
    
    def __init__(self, redis_client: Optional[RedisClient] = None):
        if redis_client is None:
            redis_client = create_single_redis_client()
        
        super().__init__(
            redis_client=redis_client,
            enable_local_cache=settings.redis_local_cache_enabled,
            local_cache_ttl=settings.redis_local_cache_ttl,
            local_cache_size=1000
        )
        
        self.set_cache_prefix("payment")
        self.set_default_ttl(settings.cache_ttl_payment)
        self.INVOICE_TTL = settings.cache_ttl_invoice or 1800
        self.STATUS_TTL = settings.cache_ttl_payment_status or 300
        
        logger.info(f"PaymentCacheService инициализирован с local_cache={settings.redis_local_cache_enabled}")
    
    async def get(self, key: str) -> Optional[Any]:
        data = await super().get(key)
        if key.startswith("status:") and data:
            await self._validate_status_freshness(key, data)
        return data
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        if isinstance(value, dict) and not key.startswith("status:"):
            value = {**value, 'cached_at': datetime.utcnow().isoformat()}
        return await super().set(key, value, ttl)
    
    async def delete(self, key: str) -> bool:
        return await super().delete(key)
    
    # Специфические методы для платежей
    
    async def cache_invoice(self, invoice_id: str, invoice_data: Dict[str, Any]) -> bool:
        return await self.set(f"invoice:{invoice_id}", invoice_data, ttl=self.INVOICE_TTL)
    
    async def get_invoice(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        data = await self.get(f"invoice:{invoice_id}")
        if data and isinstance(data, dict):
            return {k: v for k, v in data.items() if k != 'cached_at'}
        return data
    
    async def cache_payment_status(self, payment_id: str, status: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        key = f"status:{payment_id}"
        status_data = {
            'status': status,
            'updated_at': datetime.utcnow().isoformat(),
            'payment_id': payment_id
        }
        if metadata:
            status_data.update(metadata)
        
        success = await self.set(key, status_data, ttl=self.STATUS_TTL)
        if success:
            await self._update_status_index(payment_id, status)
        return success
    
    async def get_payment_status(self, payment_id: str) -> Optional[Dict[str, Any]]:
        data = await self.get(f"status:{payment_id}")
        if data and isinstance(data, dict):
            return {k: v for k, v in data.items() if k != 'updated_at'}
        return data
    
    async def cache_payment_details(self, payment_id: str, details: Dict[str, Any]) -> bool:
        return await self.set(f"details:{payment_id}", details)
    
    async def get_payment_details(self, payment_id: str) -> Optional[Dict[str, Any]]:
        return await self.get(f"details:{payment_id}")
    
    async def cache_payment_transaction(self, payment_id: str, transaction_data: Dict[str, Any]) -> bool:
        return await self.set(f"transaction:{payment_id}", transaction_data)
    
    async def get_payment_transaction(self, payment_id: str) -> Optional[Dict[str, Any]]:
        return await self.get(f"transaction:{payment_id}")
    
    async def update_payment_status(self, payment_id: str, new_status: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        return await self.cache_payment_status(payment_id, new_status, metadata)
    
    async def get_payments_by_status(self, status: str, limit: int = 100) -> List[Dict[str, Any]]:
        payment_ids = await self._get_payment_ids_by_status(status, limit)
        payments = []
        for payment_id in payment_ids:
            payment_status = await self.get_payment_status(payment_id)
            if payment_status and payment_status.get('status') == status:
                payment_details = await self.get_payment_details(payment_id)
                payments.append({
                    'payment_id': payment_id,
                    'status': payment_status,
                    'details': payment_details
                })
        return payments
    
    async def invalidate_payment_cache(self, payment_id: str) -> bool:
        keys = [f"invoice:{payment_id}", f"status:{payment_id}", f"details:{payment_id}", f"transaction:{payment_id}"]
        success = all(await self.delete(key) for key in keys)
        if success:
            await self._remove_from_status_indices(payment_id)
        return success
    
    async def get_payment_stats(self) -> Dict[str, Any]:
        return {
            'cache_hit_rate': self.metrics.hit_rate,
            'total_hits': self.metrics.hits,
            'total_misses': self.metrics.misses,
            'errors': self.metrics.errors,
            'redis_connected': bool(self.redis_client and await self.redis_client.ping()),
            'local_cache_enabled': self.enable_local_cache
        }
    
    async def is_payment_cached(self, payment_id: str) -> bool:
        return await self.exists(f"status:{payment_id}")
    
    async def extend_payment_cache(self, payment_id: str, additional_ttl: Optional[int] = None) -> bool:
        ttl = additional_ttl or self._default_ttl
        keys = [f"invoice:{payment_id}", f"status:{payment_id}", f"details:{payment_id}", f"transaction:{payment_id}"]
        return all(await self.expire(key, ttl) for key in keys)
    
    # Вспомогательные методы
    
    async def _validate_status_freshness(self, key: str, data: Dict[str, Any]) -> None:
        try:
            updated_at = data.get('updated_at')
            if updated_at:
                updated_time = datetime.fromisoformat(updated_at)
                if datetime.utcnow() - updated_time > timedelta(seconds=self.STATUS_TTL):
                    await self.delete(key)
        except (ValueError, KeyError):
            pass
    
    async def _update_status_index(self, payment_id: str, status: str) -> None:
        if not self.redis_client:
            return
        try:
            await self.redis_client.execute_operation('sadd', f"status_index:{status}", payment_id)
            await self.redis_client.execute_operation('expire', f"status_index:{status}", self.STATUS_TTL)
        except Exception:
            pass
    
    async def _get_payment_ids_by_status(self, status: str, limit: int) -> List[str]:
        if not self.redis_client:
            return []
        try:
            payment_ids = await self.redis_client.execute_operation('smembers', f"status_index:{status}")
            return list(payment_ids)[:limit] if payment_ids else []
        except Exception:
            return []
    
    async def _remove_from_status_indices(self, payment_id: str) -> None:
        if not self.redis_client:
            return
        try:
            for status in ['pending', 'processing', 'completed', 'failed', 'cancelled']:
                await self.redis_client.execute_operation('srem', f"status_index:{status}", payment_id)
        except Exception:
            pass


# Для обратной совместимости
PaymentCache = PaymentCacheService
