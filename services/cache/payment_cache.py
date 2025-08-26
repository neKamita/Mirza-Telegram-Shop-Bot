"""
Payment Cache Service - специализированный сервис для кеширования платежных данных
"""
import json
import logging
import time
import traceback
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import redis.asyncio as redis
from threading import Lock
from config.settings import settings


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

            self.cache[key] = {
                'data': value,
                'created_at': time.time()
            }
            self.access_times[key] = time.time()

            self.logger.debug(f"Stored key in local cache: {key}")
            return True


class PaymentCache:
    """Специализированный сервис для кеширования платежных данных с graceful degradation"""

    def __init__(self, redis_client: Any):
        self.redis_client = redis_client
        self.logger = logging.getLogger(__name__)
        self.PAYMENT_PREFIX = "payment:"
        self.INVOICE_PREFIX = "invoice:"
        self.PAYMENT_STATUS_PREFIX = "payment_status:"
        self.PAYMENT_DETAILS_PREFIX = "payment_details:"
        self.DEFAULT_TTL = settings.cache_ttl_payment
        self.INVOICE_TTL = settings.cache_ttl_invoice or 1800
        self.STATUS_TTL = settings.cache_ttl_payment_status or 300  # Увеличить до 5 минут

        # Локальное кэширование для graceful degradation
        self.local_cache_enabled = settings.redis_local_cache_enabled
        self.local_cache_ttl = settings.redis_local_cache_ttl
        self.local_cache = LocalCache(max_size=1000, ttl=self.local_cache_ttl) if self.local_cache_enabled else None

        self.logger.info(f"PaymentCache initialized with redis_client: {redis_client is not None}, local_cache: {self.local_cache_enabled}")

    async def cache_invoice(self, invoice_id: str, invoice_data: Dict[str, Any]) -> bool:
        """Кеширование данных инвойса с graceful degradation"""
        try:
            key = f"{self.INVOICE_PREFIX}{invoice_id}"
            invoice_data['cached_at'] = datetime.utcnow().isoformat()

            # Пытаемся сохранить в Redis
            if self.redis_client:
                try:
                    serialized = json.dumps(invoice_data, default=str)
                    await self._execute_redis_operation('setex', key, self.INVOICE_TTL, serialized)
                    self.logger.debug(f"Invoice {invoice_id} cached in Redis")
                    return True
                except Exception as redis_error:
                    self.logger.warning(f"Failed to cache invoice in Redis, using local cache: {redis_error}")

            # Локальное кэширование
            if self.local_cache:
                self.local_cache.set(key, invoice_data)
                self.logger.debug(f"Invoice {invoice_id} cached in local cache")
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error caching invoice {invoice_id}: {e}")
            return False

    async def get_invoice(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        """Получение данных инвойса из кеша с graceful degradation"""
        try:
            key = f"{self.INVOICE_PREFIX}{invoice_id}"

            # Сначала пробуем локальный кэш
            if self.local_cache:
                local_data = self.local_cache.get(key)
                if local_data:
                    self.logger.debug(f"Invoice {invoice_id} found in local cache")
                    return local_data

            # Если Redis доступен, пробуем Redis
            if self.redis_client:
                try:
                    self.logger.debug(f"Attempting to get invoice from Redis for {invoice_id}")
                    cached_data = await self._execute_redis_operation('get', key)
                    if cached_data:
                        self.logger.debug(f"Redis returned data for invoice {invoice_id}: {cached_data[:100]}...")
                        try:
                            data = json.loads(cached_data)
                            # Проверяем свежесть данных
                            cached_at_str = data.get('cached_at', '')
                            if cached_at_str:
                                try:
                                    cached_at = datetime.fromisoformat(cached_at_str)
                                    if datetime.utcnow() - cached_at < timedelta(seconds=self.INVOICE_TTL):
                                        # Удаляем временные поля перед возвратом
                                        data.pop('cached_at', None)
                                        # Кэшируем в локальном хранилище
                                        if self.local_cache:
                                            self.local_cache.set(key, data)
                                        self.logger.info(f"Invoice {invoice_id} found in Redis (fresh)")
                                        return data
                                    else:
                                        self.logger.warning(f"Invoice {invoice_id} found in Redis but expired")
                                        # Данные устарели, удаляем из кеша
                                        await self._execute_redis_operation('delete', key)
                                except ValueError as datetime_error:
                                    self.logger.error(f"Error parsing cached_at for invoice {invoice_id}: {datetime_error}")
                                    await self._execute_redis_operation('delete', key)
                            else:
                                self.logger.warning(f"No cached_at field in Redis data for invoice {invoice_id}")
                                await self._execute_redis_operation('delete', key)
                        except json.JSONDecodeError as json_error:
                            self.logger.error(f"Error parsing JSON from Redis for invoice {invoice_id}: {json_error}")
                            await self._execute_redis_operation('delete', key)
                    else:
                        self.logger.debug(f"No invoice found in Redis for {invoice_id}")
                except Exception as redis_error:
                    self.logger.error(f"Failed to get invoice from Redis: {redis_error}")
                    self.logger.error(f"Redis error type: {type(redis_error).__name__}")
                    self.logger.error(f"Redis error traceback: {traceback.format_exc()}")
                    # При ошибке Redis пробуем локальный кэш еще раз
                    if self.local_cache:
                        self.logger.debug(f"Retrying local cache after Redis error for invoice {invoice_id}")
                        try:
                            local_data = self.local_cache.get(key)
                            if local_data:
                                self.logger.info(f"Invoice {invoice_id} found in local cache (fallback)")
                                return local_data
                            else:
                                self.logger.debug(f"No invoice found in local cache fallback for {invoice_id}")
                        except Exception as fallback_error:
                            self.logger.error(f"Error in local cache fallback for invoice {invoice_id}: {fallback_error}")

            return None

        except Exception as e:
            self.logger.error(f"Error getting invoice {invoice_id}: {e}")
            return None

    async def cache_payment_status(self, payment_id: str, status: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Кеширование статуса платежа с graceful degradation"""
        try:
            key = f"{self.PAYMENT_STATUS_PREFIX}{payment_id}"
            status_data = {
                'status': status,
                'updated_at': datetime.utcnow().isoformat()
            }

            if metadata:
                status_data.update(metadata)

            # Пытаемся сохранить в Redis
            if self.redis_client:
                try:
                    serialized = json.dumps(status_data, default=str)
                    await self._execute_redis_operation('setex', key, self.STATUS_TTL, serialized)
                    self.logger.debug(f"Payment status {payment_id} cached in Redis")
                    return True
                except Exception as redis_error:
                    self.logger.warning(f"Failed to cache payment status in Redis, using local cache: {redis_error}")

            # Локальное кэширование
            if self.local_cache:
                self.local_cache.set(key, status_data)
                self.logger.debug(f"Payment status {payment_id} cached in local cache")
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error caching payment status {payment_id}: {e}")
            return False

    async def get_payment_status(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """Получение статуса платежа из кеша с graceful degradation"""
        try:
            key = f"{self.PAYMENT_STATUS_PREFIX}{payment_id}"

            # Сначала пробуем локальный кэш
            if self.local_cache:
                local_data = self.local_cache.get(key)
                if local_data:
                    self.logger.debug(f"Payment status {payment_id} found in local cache")
                    return local_data

            # Если Redis доступен, пробуем Redis
            if self.redis_client:
                try:
                    self.logger.debug(f"Attempting to get payment status from Redis for {payment_id}")
                    cached_data = await self._execute_redis_operation('get', key)
                    if cached_data:
                        self.logger.debug(f"Redis returned data for payment status {payment_id}: {cached_data[:100]}...")
                        try:
                            data = json.loads(cached_data)
                            # Проверяем свежесть данных
                            updated_at_str = data.get('updated_at', '')
                            if updated_at_str:
                                try:
                                    updated_at = datetime.fromisoformat(updated_at_str)
                                    if datetime.utcnow() - updated_at < timedelta(seconds=self.STATUS_TTL):
                                        # Удаляем временные поля перед возвратом
                                        data.pop('updated_at', None)
                                        # Кэшируем в локальном хранилище
                                        if self.local_cache:
                                            self.local_cache.set(key, data)
                                        self.logger.info(f"Payment status {payment_id} found in Redis (fresh)")
                                        return data
                                    else:
                                        self.logger.warning(f"Payment status {payment_id} found in Redis but expired")
                                        # Данные устарели, удаляем из кеша
                                        await self._execute_redis_operation('delete', key)
                                except ValueError as datetime_error:
                                    self.logger.error(f"Error parsing updated_at for payment status {payment_id}: {datetime_error}")
                                    await self._execute_redis_operation('delete', key)
                            else:
                                self.logger.warning(f"No updated_at field in Redis data for payment status {payment_id}")
                                await self._execute_redis_operation('delete', key)
                        except json.JSONDecodeError as json_error:
                            self.logger.error(f"Error parsing JSON from Redis for payment status {payment_id}: {json_error}")
                            await self._execute_redis_operation('delete', key)
                    else:
                        self.logger.debug(f"No payment status found in Redis for {payment_id}")
                except Exception as redis_error:
                    self.logger.error(f"Failed to get payment status from Redis: {redis_error}")
                    self.logger.error(f"Redis error type: {type(redis_error).__name__}")
                    self.logger.error(f"Redis error traceback: {traceback.format_exc()}")
                    # При ошибке Redis пробуем локальный кэш еще раз
                    if self.local_cache:
                        self.logger.debug(f"Retrying local cache after Redis error for payment status {payment_id}")
                        try:
                            local_data = self.local_cache.get(key)
                            if local_data:
                                self.logger.info(f"Payment status {payment_id} found in local cache (fallback)")
                                return local_data
                            else:
                                self.logger.debug(f"No payment status found in local cache fallback for {payment_id}")
                        except Exception as fallback_error:
                            self.logger.error(f"Error in local cache fallback for payment status {payment_id}: {fallback_error}")

            return None

        except Exception as e:
            self.logger.error(f"Error getting payment status {payment_id}: {e}")
            return None

    async def cache_payment_details(self, payment_id: str, details: Dict[str, Any]) -> bool:
        """Кеширование деталей платежа с graceful degradation"""
        try:
            key = f"{self.PAYMENT_DETAILS_PREFIX}{payment_id}"
            details['cached_at'] = datetime.utcnow().isoformat()

            # Пытаемся сохранить в Redis
            if self.redis_client:
                try:
                    serialized = json.dumps(details, default=str)
                    await self._execute_redis_operation('setex', key, self.DEFAULT_TTL, serialized)
                    self.logger.debug(f"Payment details {payment_id} cached in Redis")
                    return True
                except Exception as redis_error:
                    self.logger.warning(f"Failed to cache payment details in Redis, using local cache: {redis_error}")

            # Локальное кэширование
            if self.local_cache:
                self.local_cache.set(key, details)
                self.logger.debug(f"Payment details {payment_id} cached in local cache")
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error caching payment details {payment_id}: {e}")
            return False

    async def get_payment_details(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """Получение деталей платежа из кеша с graceful degradation"""
        try:
            key = f"{self.PAYMENT_DETAILS_PREFIX}{payment_id}"

            # Сначала пробуем локальный кэш
            if self.local_cache:
                local_data = self.local_cache.get(key)
                if local_data:
                    self.logger.debug(f"Payment details {payment_id} found in local cache")
                    return local_data

            # Если Redis доступен, пробуем Redis
            if self.redis_client:
                try:
                    self.logger.debug(f"Attempting to get payment details from Redis for {payment_id}")
                    cached_data = await self._execute_redis_operation('get', key)
                    if cached_data:
                        self.logger.debug(f"Redis returned data for payment details {payment_id}: {cached_data[:100]}...")
                        try:
                            data = json.loads(cached_data)
                            # Проверяем свежесть данных
                            cached_at_str = data.get('cached_at', '')
                            if cached_at_str:
                                try:
                                    cached_at = datetime.fromisoformat(cached_at_str)
                                    if datetime.utcnow() - cached_at < timedelta(seconds=self.DEFAULT_TTL):
                                        # Удаляем временные поля перед возвратом
                                        data.pop('cached_at', None)
                                        # Кэшируем в локальном хранилище
                                        if self.local_cache:
                                            self.local_cache.set(key, data)
                                        self.logger.info(f"Payment details {payment_id} found in Redis (fresh)")
                                        return data
                                    else:
                                        self.logger.warning(f"Payment details {payment_id} found in Redis but expired")
                                        # Данные устарели, удаляем из кеша
                                        await self._execute_redis_operation('delete', key)
                                except ValueError as datetime_error:
                                    self.logger.error(f"Error parsing cached_at for payment details {payment_id}: {datetime_error}")
                                    await self._execute_redis_operation('delete', key)
                            else:
                                self.logger.warning(f"No cached_at field in Redis data for payment details {payment_id}")
                                await self._execute_redis_operation('delete', key)
                        except json.JSONDecodeError as json_error:
                            self.logger.error(f"Error parsing JSON from Redis for payment details {payment_id}: {json_error}")
                            await self._execute_redis_operation('delete', key)
                    else:
                        self.logger.debug(f"No payment details found in Redis for {payment_id}")
                except Exception as redis_error:
                    self.logger.error(f"Failed to get payment details from Redis: {redis_error}")
                    self.logger.error(f"Redis error type: {type(redis_error).__name__}")
                    self.logger.error(f"Redis error traceback: {traceback.format_exc()}")
                    # При ошибке Redis пробуем локальный кэш еще раз
                    if self.local_cache:
                        self.logger.debug(f"Retrying local cache after Redis error for payment details {payment_id}")
                        try:
                            local_data = self.local_cache.get(key)
                            if local_data:
                                self.logger.info(f"Payment details {payment_id} found in local cache (fallback)")
                                return local_data
                            else:
                                self.logger.debug(f"No payment details found in local cache fallback for {payment_id}")
                        except Exception as fallback_error:
                            self.logger.error(f"Error in local cache fallback for payment details {payment_id}: {fallback_error}")

            return None

        except Exception as e:
            self.logger.error(f"Error getting payment details {payment_id}: {e}")
            return None

    async def cache_payment_transaction(self, payment_id: str, transaction_data: Dict[str, Any]) -> bool:
        """Кеширование данных транзакции с graceful degradation"""
        try:
            key = f"{self.PAYMENT_PREFIX}{payment_id}:transaction"
            transaction_data['cached_at'] = datetime.utcnow().isoformat()

            # Пытаемся сохранить в Redis
            if self.redis_client:
                try:
                    serialized = json.dumps(transaction_data, default=str)
                    await self._execute_redis_operation('setex', key, self.DEFAULT_TTL, serialized)
                    self.logger.debug(f"Payment transaction {payment_id} cached in Redis")
                    return True
                except Exception as redis_error:
                    self.logger.warning(f"Failed to cache payment transaction in Redis, using local cache: {redis_error}")

            # Локальное кэширование
            if self.local_cache:
                self.local_cache.set(key, transaction_data)
                self.logger.debug(f"Payment transaction {payment_id} cached in local cache")
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error caching payment transaction {payment_id}: {e}")
            return False

    async def get_payment_transaction(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """Получение данных транзакции из кеша с graceful degradation"""
        try:
            key = f"{self.PAYMENT_PREFIX}{payment_id}:transaction"

            # Сначала пробуем локальный кэш
            if self.local_cache:
                local_data = self.local_cache.get(key)
                if local_data:
                    self.logger.debug(f"Payment transaction {payment_id} found in local cache")
                    return local_data

            # Если Redis доступен, пробуем Redis
            if self.redis_client:
                try:
                    self.logger.debug(f"Attempting to get payment transaction from Redis for {payment_id}")
                    cached_data = await self._execute_redis_operation('get', key)
                    if cached_data:
                        self.logger.debug(f"Redis returned data for payment transaction {payment_id}: {cached_data[:100]}...")
                        try:
                            data = json.loads(cached_data)
                            # Проверяем свежесть данных
                            cached_at_str = data.get('cached_at', '')
                            if cached_at_str:
                                try:
                                    cached_at = datetime.fromisoformat(cached_at_str)
                                    if datetime.utcnow() - cached_at < timedelta(seconds=self.DEFAULT_TTL):
                                        # Удаляем временные поля перед возвратом
                                        data.pop('cached_at', None)
                                        # Кэшируем в локальном хранилище
                                        if self.local_cache:
                                            self.local_cache.set(key, data)
                                        self.logger.info(f"Payment transaction {payment_id} found in Redis (fresh)")
                                        return data
                                    else:
                                        self.logger.warning(f"Payment transaction {payment_id} found in Redis but expired")
                                        # Данные устарели, удаляем из кеша
                                        await self._execute_redis_operation('delete', key)
                                except ValueError as datetime_error:
                                    self.logger.error(f"Error parsing cached_at for payment transaction {payment_id}: {datetime_error}")
                                    await self._execute_redis_operation('delete', key)
                            else:
                                self.logger.warning(f"No cached_at field in Redis data for payment transaction {payment_id}")
                                await self._execute_redis_operation('delete', key)
                        except json.JSONDecodeError as json_error:
                            self.logger.error(f"Error parsing JSON from Redis for payment transaction {payment_id}: {json_error}")
                            await self._execute_redis_operation('delete', key)
                    else:
                        self.logger.debug(f"No payment transaction found in Redis for {payment_id}")
                except Exception as redis_error:
                    self.logger.error(f"Failed to get payment transaction from Redis: {redis_error}")
                    self.logger.error(f"Redis error type: {type(redis_error).__name__}")
                    self.logger.error(f"Redis error traceback: {traceback.format_exc()}")
                    # При ошибке Redis пробуем локальный кэш еще раз
                    if self.local_cache:
                        self.logger.debug(f"Retrying local cache after Redis error for payment transaction {payment_id}")
                        try:
                            local_data = self.local_cache.get(key)
                            if local_data:
                                self.logger.info(f"Payment transaction {payment_id} found in local cache (fallback)")
                                return local_data
                            else:
                                self.logger.debug(f"No payment transaction found in local cache fallback for {payment_id}")
                        except Exception as fallback_error:
                            self.logger.error(f"Error in local cache fallback for payment transaction {payment_id}: {fallback_error}")

            return None

        except Exception as e:
            self.logger.error(f"Error getting payment transaction {payment_id}: {e}")
            return None

    async def update_payment_status(self, payment_id: str, new_status: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Обновление статуса платежа с graceful degradation"""
        try:
            key = f"{self.PAYMENT_STATUS_PREFIX}{payment_id}"
            status_data = {
                'status': new_status,
                'updated_at': datetime.utcnow().isoformat()
            }

            if metadata:
                status_data.update(metadata)

            # Пытаемся сохранить в Redis
            if self.redis_client:
                try:
                    serialized = json.dumps(status_data, default=str)
                    await self._execute_redis_operation('setex', key, self.STATUS_TTL, serialized)
                    self.logger.debug(f"Payment status {payment_id} updated in Redis")
                    
                    # Также обновляем индекс статусов
                    await self._update_payment_status_index(payment_id, new_status)
                    return True
                except Exception as redis_error:
                    self.logger.warning(f"Failed to update payment status in Redis, using local cache: {redis_error}")

            # Локальное кэширование
            if self.local_cache:
                self.local_cache.set(key, status_data)
                self.logger.debug(f"Payment status {payment_id} updated in local cache")
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error updating payment status {payment_id}: {e}")
            return False

    async def get_payments_by_status(self, status: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Получение платежей по статусу"""
        try:
            index_key = f"payment_status_index:{status}"
            payment_ids = await self._execute_redis_operation('lrange', index_key, 0, limit - 1)

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
                keys = await self._execute_redis_operation('keys', pattern)
                if keys:
                    await self._execute_redis_operation('delete', *keys)

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
            payment_keys = await self._execute_redis_operation('keys', f"{self.PAYMENT_STATUS_PREFIX}*")
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

    async def _execute_redis_operation(self, operation: str, *args, **kwargs) -> Any:
        """
        Универсальный метод для выполнения Redis операций с поддержкой
        как синхронных, так и асинхронных клиентов
        
        Args:
            operation: Название операции (get, set, lpush, lrem и т.д.)
            *args: Аргументы операции
            **kwargs: Именованные аргументы операции
            
        Returns:
            Результат операции
        """
        try:
            # Проверяем доступность Redis клиента
            if not self.redis_client:
                raise ConnectionError("Redis client is not available")
            
            # Получаем метод Redis клиента
            method = getattr(self.redis_client, operation)
            
            # Проверяем, является ли метод асинхронным
            if asyncio.iscoroutinefunction(method):
                # Используем async метод
                return await method(*args, **kwargs)
            else:
                # Для синхронного метода используем asyncio.to_thread
                def wrapped_method():
                    return method(*args, **kwargs)
                
                return await asyncio.to_thread(wrapped_method)
                
        except Exception as e:
            self.logger.error(f"Error executing Redis operation {operation}: {e}")
            raise

    async def _update_payment_status_index(self, payment_id: str, status: str) -> None:
        """Обновление индекса статусов платежей"""
        try:
            index_key = f"payment_status_index:{status}"
            # Убеждаемся, что payment_id - это строка для Redis
            payment_id_str = str(payment_id)
            await self._execute_redis_operation('lpush', index_key, payment_id_str)
            await self._execute_redis_operation('expire', index_key, self.STATUS_TTL)
        except Exception as e:
            self.logger.error(f"Error updating payment status index: {e}")

    async def _remove_payment_from_indices(self, payment_id: str) -> None:
        """Удаление платежа из индексов"""
        try:
            # Получаем все возможные статусы
            statuses = ['pending', 'processing', 'completed', 'failed', 'cancelled']

            for status in statuses:
                index_key = f"payment_status_index:{status}"
                # Убеждаемся, что payment_id - это строка для Redis
                payment_id_str = str(payment_id)
                await self._execute_redis_operation('lrem', index_key, 0, payment_id_str)
        except Exception as e:
            self.logger.error(f"Error removing payment from indices: {e}")

    async def is_payment_cached(self, payment_id: str) -> bool:
        """Проверка, есть ли платеж в кеше"""
        try:
            key = f"{self.PAYMENT_STATUS_PREFIX}{payment_id}"
            return await self._execute_redis_operation('exists', key) > 0
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
                await self._execute_redis_operation('expire', key, new_ttl)

            self.logger.info(f"Extended payment cache for {payment_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error extending payment cache for {payment_id}: {e}")
            return False
