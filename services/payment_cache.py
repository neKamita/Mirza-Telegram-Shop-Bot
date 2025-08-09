"""
Payment Cache Service - специализированный сервис для кеширования платежных данных
"""
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import redis.asyncio as redis
from config.settings import settings


class PaymentCache:
    """Специализированный сервис для кеширования платежных данных"""

    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client
        self.logger = logging.getLogger(__name__)
        self.PAYMENT_PREFIX = "payment:"
        self.INVOICE_PREFIX = "invoice:"
        self.PAYMENT_STATUS_PREFIX = "payment_status:"
        self.PAYMENT_DETAILS_PREFIX = "payment_details:"
        self.DEFAULT_TTL = settings.cache_ttl_payment
        self.INVOICE_TTL = settings.cache_ttl_invoice or 1800
        self.STATUS_TTL = settings.cache_ttl_payment_status or 900

    async def cache_invoice(self, invoice_id: str, invoice_data: Dict[str, Any]) -> bool:
        """Кеширование данных инвойса"""
        try:
            key = f"{self.INVOICE_PREFIX}{invoice_id}"
            invoice_data['cached_at'] = datetime.utcnow().isoformat()
            serialized = json.dumps(invoice_data, default=str)
            await self.redis_client.setex(key, self.INVOICE_TTL, serialized)
            return True
        except Exception as e:
            self.logger.error(f"Error caching invoice {invoice_id}: {e}")
            return False

    async def get_invoice(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        """Получение данных инвойса из кеша"""
        try:
            key = f"{self.INVOICE_PREFIX}{invoice_id}"
            cached_data = await self.redis_client.get(key)

            if cached_data:
                data = json.loads(cached_data)
                # Проверяем свежесть
                cached_at = datetime.fromisoformat(data.get('cached_at', ''))
                if datetime.utcnow() - cached_at < timedelta(seconds=self.INVOICE_TTL):
                    data.pop('cached_at', None)
                    return data
                else:
                    await self.redis_client.delete(key)

            return None

        except Exception as e:
            self.logger.error(f"Error getting invoice {invoice_id}: {e}")
            return None

    async def cache_payment_status(self, payment_id: str, status: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Кеширование статуса платежа"""
        try:
            key = f"{self.PAYMENT_STATUS_PREFIX}{payment_id}"
            status_data = {
                'status': status,
                'updated_at': datetime.utcnow().isoformat()
            }

            if metadata:
                status_data.update(metadata)

            serialized = json.dumps(status_data, default=str)
            await self.redis_client.setex(key, self.STATUS_TTL, serialized)
            return True
        except Exception as e:
            self.logger.error(f"Error caching payment status {payment_id}: {e}")
            return False

    async def get_payment_status(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """Получение статуса платежа из кеша"""
        try:
            key = f"{self.PAYMENT_STATUS_PREFIX}{payment_id}"
            cached_data = await self.redis_client.get(key)

            if cached_data:
                data = json.loads(cached_data)
                # Проверяем свежесть
                updated_at = datetime.fromisoformat(data.get('updated_at', ''))
                if datetime.utcnow() - updated_at < timedelta(seconds=self.STATUS_TTL):
                    data.pop('updated_at', None)
                    return data
                else:
                    await self.redis_client.delete(key)

            return None

        except Exception as e:
            self.logger.error(f"Error getting payment status {payment_id}: {e}")
            return None

    async def cache_payment_details(self, payment_id: str, details: Dict[str, Any]) -> bool:
        """Кеширование деталей платежа"""
        try:
            key = f"{self.PAYMENT_DETAILS_PREFIX}{payment_id}"
            details['cached_at'] = datetime.utcnow().isoformat()
            serialized = json.dumps(details, default=str)
            await self.redis_client.setex(key, self.DEFAULT_TTL, serialized)
            return True
        except Exception as e:
            self.logger.error(f"Error caching payment details {payment_id}: {e}")
            return False

    async def get_payment_details(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """Получение деталей платежа из кеша"""
        try:
            key = f"{self.PAYMENT_DETAILS_PREFIX}{payment_id}"
            cached_data = await self.redis_client.get(key)

            if cached_data:
                data = json.loads(cached_data)
                # Проверяем свежесть
                cached_at = datetime.fromisoformat(data.get('cached_at', ''))
                if datetime.utcnow() - cached_at < timedelta(seconds=self.DEFAULT_TTL):
                    data.pop('cached_at', None)
                    return data
                else:
                    await self.redis_client.delete(key)

            return None

        except Exception as e:
            self.logger.error(f"Error getting payment details {payment_id}: {e}")
            return None

    async def cache_payment_transaction(self, payment_id: str, transaction_data: Dict[str, Any]) -> bool:
        """Кеширование данных транзакции"""
        try:
            key = f"{self.PAYMENT_PREFIX}{payment_id}:transaction"
            transaction_data['cached_at'] = datetime.utcnow().isoformat()
            serialized = json.dumps(transaction_data, default=str)
            await self.redis_client.setex(key, self.DEFAULT_TTL, serialized)
            return True
        except Exception as e:
            self.logger.error(f"Error caching payment transaction {payment_id}: {e}")
            return False

    async def get_payment_transaction(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """Получение данных транзакции из кеша"""
        try:
            key = f"{self.PAYMENT_PREFIX}{payment_id}:transaction"
            cached_data = await self.redis_client.get(key)

            if cached_data:
                data = json.loads(cached_data)
                # Проверяем свежесть
                cached_at = datetime.fromisoformat(data.get('cached_at', ''))
                if datetime.utcnow() - cached_at < timedelta(seconds=self.DEFAULT_TTL):
                    data.pop('cached_at', None)
                    return data
                else:
                    await self.redis_client.delete(key)

            return None

        except Exception as e:
            self.logger.error(f"Error getting payment transaction {payment_id}: {e}")
            return None

    async def update_payment_status(self, payment_id: str, new_status: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Обновление статуса платежа"""
        try:
            key = f"{self.PAYMENT_STATUS_PREFIX}{payment_id}"
            status_data = {
                'status': new_status,
                'updated_at': datetime.utcnow().isoformat()
            }

            if metadata:
                status_data.update(metadata)

            serialized = json.dumps(status_data, default=str)
            await self.redis_client.setex(key, self.STATUS_TTL, serialized)

            # Также обновляем индекс статусов
            await self._update_payment_status_index(payment_id, new_status)

            return True
        except Exception as e:
            self.logger.error(f"Error updating payment status {payment_id}: {e}")
            return False

    async def get_payments_by_status(self, status: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Получение платежей по статусу"""
        try:
            index_key = f"payment_status_index:{status}"
            payment_ids = await self.redis_client.lrange(index_key, 0, limit - 1)

            payments = []
            for payment_id_bytes in payment_ids:
                payment_id = payment_id_bytes.decode('utf-8')
                payment_status = await self.get_payment_status(payment_id)
                if payment_status and payment_status.get('status') == status:
                    payments.append({
                        'payment_id': payment_id,
                        'status': payment_status,
                        'details': await self.get_payment_details(payment_id)
                    })

            return payments

        except Exception as e:
            self.logger.error(f"Error getting payments by status {status}: {e}")
            return []

    async def invalidate_payment_cache(self, payment_id: str) -> bool:
        """Инвалидация кеша платежа"""
        try:
            # Удаляем все связанные с платежом ключи
            patterns = [
                f"{self.INVOICE_PREFIX}{payment_id}",
                f"{self.PAYMENT_STATUS_PREFIX}{payment_id}",
                f"{self.PAYMENT_DETAILS_PREFIX}{payment_id}",
                f"{self.PAYMENT_PREFIX}{payment_id}:*"
            ]

            for pattern in patterns:
                keys = await self.redis_client.keys(pattern)
                if keys:
                    await self.redis_client.delete(*keys)

            # Удаляем из индексов
            await self._remove_payment_from_indices(payment_id)

            self.logger.info(f"Invalidated payment cache for {payment_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error invalidating payment cache for {payment_id}: {e}")
            return False

    async def get_payment_stats(self) -> Dict[str, Any]:
        """Получение статистики платежей"""
        try:
            stats = {
                'total_cached_payments': 0,
                'payments_by_status': {},
                'recent_payments': [],
                'cache_hit_rate': 0.0
            }

            # Получаем все ключи платежей
            payment_keys = await self.redis_client.keys(f"{self.PAYMENT_STATUS_PREFIX}*")
            stats['total_cached_payments'] = len(payment_keys)

            # Анализируем статусы
            status_counts = {}
            recent_payments = []

            for key in payment_keys:
                key_str = key.decode('utf-8')
                payment_id = key_str.replace(self.PAYMENT_STATUS_PREFIX, '')

                # Получаем статус
                status_data = await self.get_payment_status(payment_id)
                if status_data:
                    status = status_data.get('status', 'unknown')
                    status_counts[status] = status_counts.get(status, 0) + 1

                    # Добавляем в недавние платежи
                    if status_data.get('updated_at'):
                        updated_at = datetime.fromisoformat(status_data['updated_at'])
                        if datetime.utcnow() - updated_at < timedelta(hours=1):
                            recent_payments.append({
                                'payment_id': payment_id,
                                'status': status,
                                'updated_at': updated_at
                            })

            stats['payments_by_status'] = status_counts
            stats['recent_payments'] = sorted(
                recent_payments,
                key=lambda x: x['updated_at'],
                reverse=True
            )[:10]

            return stats

        except Exception as e:
            self.logger.error(f"Error getting payment stats: {e}")
            return {}

    async def _update_payment_status_index(self, payment_id: str, status: str) -> None:
        """Обновление индекса статусов платежей"""
        try:
            index_key = f"payment_status_index:{status}"
            await self.redis_client.lpush(index_key, payment_id)
            await self.redis_client.expire(index_key, self.STATUS_TTL)
        except Exception as e:
            self.logger.error(f"Error updating payment status index: {e}")

    async def _remove_payment_from_indices(self, payment_id: str) -> None:
        """Удаление платежа из индексов"""
        try:
            # Получаем все возможные статусы
            statuses = ['pending', 'processing', 'completed', 'failed', 'cancelled']

            for status in statuses:
                index_key = f"payment_status_index:{status}"
                await self.redis_client.lrem(index_key, 0, payment_id)
        except Exception as e:
            self.logger.error(f"Error removing payment from indices: {e}")

    async def is_payment_cached(self, payment_id: str) -> bool:
        """Проверка, есть ли платеж в кеше"""
        try:
            key = f"{self.PAYMENT_STATUS_PREFIX}{payment_id}"
            return await self.redis_client.exists(key) > 0
        except Exception as e:
            self.logger.error(f"Error checking if payment {payment_id} is cached: {e}")
            return False

    async def extend_payment_cache(self, payment_id: str, additional_ttl: Optional[int] = None) -> bool:
        """Продление срока действия кеша платежа"""
        try:
            keys_to_extend = [
                f"{self.INVOICE_PREFIX}{payment_id}",
                f"{self.PAYMENT_STATUS_PREFIX}{payment_id}",
                f"{self.PAYMENT_DETAILS_PREFIX}{payment_id}"
            ]

            new_ttl = additional_ttl or self.DEFAULT_TTL

            for key in keys_to_extend:
                await self.redis_client.expire(key, new_ttl)

            self.logger.info(f"Extended payment cache for {payment_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error extending payment cache for {payment_id}: {e}")
            return False
