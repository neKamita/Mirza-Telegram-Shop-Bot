"""
Сервис для работы с платежной системой с интеграцией кеширования
"""
import json
import hashlib
import hmac
import base64
import logging
import aiohttp
import time
from typing import Dict, Any, Optional
from core.interfaces import PaymentInterface
from services.cache.payment_cache import PaymentCache
from services.system.circuit_breaker import circuit_manager, CircuitConfigs
from utils.retry_utils import async_retry, RetryConfigs, RetryError


class PaymentService(PaymentInterface):
    """
    Сервис для управления платежами с кешированием
    Интеграция с Heleket API для обработки платежей в TON
    С поддержкой retry и circuit breaker
    """

    def __init__(self, merchant_uuid: str, api_key: str, payment_cache: Optional[PaymentCache] = None):
        self.merchant_uuid = merchant_uuid
        self.api_key = api_key
        self.payment_cache = payment_cache
        self.base_url = "https://api.heleket.com/v1"
        self.logger = logging.getLogger(__name__)
        
        # Инициализация circuit breaker для платежного сервиса
        self.circuit_breaker = circuit_manager.create_circuit(
            "payment_service",
            CircuitConfigs.payment_service()
        )

    @async_retry(RetryConfigs.payment_service())
    async def _make_http_request(self, method: str, endpoint: str, headers: Dict[str, str],
                                 data: Optional[str] = None) -> Dict[str, Any]:
        """
        Выполнение HTTP запроса с retry и circuit breaker
        
        Args:
            method: HTTP метод (GET, POST, etc.)
            endpoint: API endpoint
            headers: HTTP заголовки
            data: Тело запроса (опционально)
            
        Returns:
            Результат запроса
        """
        url = f"{self.base_url}{endpoint}"
        self.logger.debug(f"Making {method} request to: {url}")
        
        async def http_request():
            async with aiohttp.ClientSession() as session:
                request_method = getattr(session, method.lower())
                
                async with request_method(
                    url,
                    headers=headers,
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    response_text = await response.text()
                    self.logger.debug(f"Response status: {response.status}, text: {response_text}")
                    
                    try:
                        result = json.loads(response_text)
                        # Добавляем статус код в результат для обработки retry
                        result['status_code'] = response.status
                        return result
                    except json.JSONDecodeError:
                        # Если не удалось распарсить JSON, возвращаем текст с статусом
                        return {
                            'error': f"Invalid JSON response: {response_text}",
                            'status': 'failed',
                            'status_code': response.status
                        }
        
        # Выполняем запрос через circuit breaker
        return await self.circuit_breaker.call(http_request)

    def _generate_headers(self, data: str) -> Dict[str, str]:
        """Генерация заголовков для запросов"""
        signature = hashlib.md5(
            base64.b64encode(data.encode("ascii")) +
            self.api_key.encode("ascii")
        ).hexdigest()

        headers = {
            "merchant": self.merchant_uuid,
            "sign": signature,
            "Content-Type": "application/json"
        }

        self.logger.warning("Используется MD5 для совместимости с Heleket API")
        self.logger.debug(f"Generated headers: merchant={self.merchant_uuid[:8]}..., sign={signature[:8]}...")
        return headers

    async def create_invoice(self, amount: str, currency: str, order_id: str) -> Dict[str, Any]:
        """Создание счета на оплату с кешированием, retry и circuit breaker"""
        cache_key = f"invoice:{order_id}"
        self.logger.info(f"Creating invoice: amount={amount}, currency={currency}, order_id={order_id}")

        # Проверяем кеш
        if self.payment_cache:
            cached_invoice = await self.payment_cache.get_payment_details(cache_key)
            if cached_invoice:
                self.logger.info(f"Using cached invoice for {order_id}")
                return cached_invoice

        payload = {
            "amount": amount,
            "currency": currency,
            "order_id": order_id
        }

        json_data = json.dumps(payload)
        headers = self._generate_headers(json_data)

        self.logger.debug(f"Request payload: {json_data}")
        self.logger.debug(f"Request URL: {self.base_url}/payment")

        try:
            # Используем новый метод с retry и circuit breaker
            result = await self._make_http_request("POST", "/payment", headers, json_data)
            
            # Обрабатываем результат
            if 'status_code' in result:
                status_code = result.pop('status_code')
                
                if status_code == 404:
                    self.logger.error(f"Payment endpoint not found (404) for order {order_id}")
                    return {
                        "error": "Payment service temporarily unavailable",
                        "status": "failed",
                        "retryable": True
                    }
                elif status_code >= 400:
                    self.logger.error(f"Payment API error {status_code} for order {order_id}")
                    return {
                        "error": f"Payment service error: HTTP {status_code}",
                        "status": "failed",
                        "retryable": status_code != 404  # 404 не retry, остальные могут быть
                    }
            
            self.logger.info(f"Payment API response: {result}")

            # Кешируем результат
            if self.payment_cache and "result" in result:
                await self.payment_cache.cache_payment_details(
                    cache_key,
                    result
                )
                self.logger.info(f"Cached invoice for {order_id}")

            return result
            
        except RetryError as e:
            self.logger.error(f"Failed to create invoice after retries: {e}")
            return {
                "error": f"Payment service unavailable after multiple attempts: {str(e.last_exception) if e.last_exception else 'Unknown error'}",
                "status": "failed",
                "retryable": False
            }
        except Exception as e:
            self.logger.error(f"Unexpected error during payment request: {e}", exc_info=True)
            return {
                "error": str(e),
                "status": "failed",
                "retryable": True
            }

    async def check_payment(self, invoice_uuid: str) -> Dict[str, Any]:
        """Проверка статуса оплаты с кешированием, retry и circuit breaker"""
        cache_key = f"payment_status:{invoice_uuid}"

        # Проверяем кеш
        if self.payment_cache:
            cached_status = await self.payment_cache.get_payment_details(cache_key)
            if cached_status:
                return cached_status

        payload = {"uuid": invoice_uuid}
        json_data = json.dumps(payload)
        headers = self._generate_headers(json_data)

        try:
            # Используем новый метод с retry и circuit breaker
            result = await self._make_http_request("POST", "/payment/info", headers, json_data)
            
            # Обрабатываем результат
            if 'status_code' in result:
                status_code = result.pop('status_code')
                
                if status_code == 404:
                    self.logger.error(f"Payment info endpoint not found (404) for invoice {invoice_uuid}")
                    return {
                        "error": "Payment service temporarily unavailable",
                        "status": "failed",
                        "retryable": True
                    }
                elif status_code >= 400:
                    self.logger.error(f"Payment API error {status_code} for invoice {invoice_uuid}")
                    return {
                        "error": f"Payment service error: HTTP {status_code}",
                        "status": "failed",
                        "retryable": status_code != 404
                    }
            
            # Кешируем результат на короткое время для избежания частых запросов
            if self.payment_cache:
                await self.payment_cache.cache_payment_details(
                    cache_key,
                    result
                )

            return result
            
        except RetryError as e:
            self.logger.error(f"Failed to check payment status after retries: {e}")
            return {
                "error": f"Payment service unavailable after multiple attempts: {str(e.last_exception) if e.last_exception else 'Unknown error'}",
                "status": "failed",
                "retryable": False
            }
        except Exception as e:
            self.logger.error(f"Unexpected error during payment status check: {e}", exc_info=True)
            return {
                "error": str(e),
                "status": "failed",
                "retryable": True
            }

    async def create_invoice_for_user(self, user_id: int, amount: str = "1") -> Dict[str, Any]:
        """Создание счета для конкретного пользователя с кешированием"""
        order_id = f"subscription-{user_id}-{int(time.time())}"

        # Кешируем информацию о заказе
        if self.payment_cache:
            await self.payment_cache.cache_payment_details(
                f"user_order:{user_id}:{order_id}",
                {
                    "user_id": user_id,
                    "amount": amount,
                    "currency": "TON",
                    "created_at": time.time()
                }
            )

        return await self.create_invoice(
            amount=amount,
            currency="TON",
            order_id=order_id
        )

    async def create_recharge_invoice(self, user_id: int, amount: str) -> Dict[str, Any]:
        """Создание счета на пополнение баланса с кешированием"""
        order_id = f"recharge-{user_id}-{int(time.time())}"

        # Кешируем информацию о пополнении
        if self.payment_cache:
            await self.payment_cache.cache_payment_details(
                f"recharge:{user_id}:{order_id}",
                {
                    "user_id": user_id,
                    "amount": amount,
                    "currency": "TON",
                    "type": "recharge",
                    "created_at": time.time()
                }
            )

        return await self.create_invoice(
            amount=amount,
            currency="TON",
            order_id=order_id
        )

    async def create_recharge_invoice_for_user(self, user_id: int, amount: str = "10") -> Dict[str, Any]:
        """Создание счета на пополнение баланса для конкретного пользователя с кешированием"""
        return await self.create_recharge_invoice(user_id, amount)

    async def get_recharge_history(self, user_id: int, limit: int = 10) -> Dict[str, Any]:
        """Получение истории пополнений пользователя из кеша"""
        if not self.payment_cache:
            return {"error": "Payment cache not available", "status": "failed"}

        try:
            # Получаем все ключи пополнений пользователя
            pattern = f"recharge:{user_id}:*"
            keys = await self.payment_cache.redis_client.keys(pattern)

            recharges = []
            for key in keys[:limit]:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)
                recharge_data = await self.payment_cache.get_payment_details(key_str)
                if recharge_data:
                    recharges.append(recharge_data)

            return {
                "status": "success",
                "recharges": recharges,
                "total": len(recharges)
            }
        except Exception as e:
            return {"error": str(e), "status": "failed"}

    async def get_payment_history(self, user_id: int, limit: int = 10) -> Dict[str, Any]:
        """Получение истории платежей пользователя из кеша"""
        if not self.payment_cache:
            return {"error": "Payment cache not available", "status": "failed"}

        try:
            # Получаем все ключи платежей пользователя
            pattern = f"user_order:{user_id}:*"
            keys = await self.payment_cache.redis_client.keys(pattern)

            payments = []
            for key in keys[:limit]:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)
                payment_data = await self.payment_cache.get_payment_details(key_str)
                if payment_data:
                    payments.append(payment_data)

            return {
                "status": "success",
                "payments": payments,
                "total": len(payments)
            }
        except Exception as e:
            return {"error": str(e), "status": "failed"}

    async def invalidate_payment_cache(self, invoice_uuid: str) -> bool:
        """Инвалидация кеша платежа"""
        if not self.payment_cache:
            return False

        try:
            cache_key = f"payment_status:{invoice_uuid}"
            await self.payment_cache.redis_client.delete(cache_key)
            return True
        except Exception:
            return False

    async def get_payment_statistics(self, user_id: int) -> Dict[str, Any]:
        """Получение статистики платежей пользователя"""
        if not self.payment_cache:
            return {"error": "Payment cache not available", "status": "failed"}

        try:
            pattern = f"user_order:{user_id}:*"
            keys = await self.payment_cache.redis_client.keys(pattern)

            total_amount = 0
            payment_count = 0

            for key in keys:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)
                payment_data = await self.payment_cache.get_payment_details(key_str)
                if payment_data and "amount" in payment_data:
                    try:
                        total_amount += float(payment_data["amount"])
                        payment_count += 1
                    except (ValueError, TypeError):
                        continue

            return {
                "status": "success",
                "total_payments": payment_count,
                "total_amount": total_amount,
                "average_amount": total_amount / payment_count if payment_count > 0 else 0
            }
        except Exception as e:
            return {"error": str(e), "status": "failed"}
