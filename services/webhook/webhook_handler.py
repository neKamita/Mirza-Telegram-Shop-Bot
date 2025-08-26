"""
Вебхук обработчик для приема уведомлений от платежной системы Heleket
"""
import json
import logging
import hashlib
import hmac
import base64
from typing import Dict, Any, Optional
from datetime import datetime

from starlette.requests import Request
from starlette.responses import JSONResponse

from repositories.user_repository import UserRepository
from repositories.balance_repository import BalanceRepository
from services.payment.star_purchase_service import StarPurchaseService
from services.cache.user_cache import UserCache
from services.cache.payment_cache import PaymentCache


class WebhookHandler:
    """Обработчик вебхуков от Heleket"""

    async def handle_payment_webhook(self, request: Request) -> JSONResponse:
        """Обработка вебхука от платежной системы"""
        try:
            # Настройка логирования для этой функции
            logger = logging.getLogger(__name__)

            # Получаем данные из запроса
            body = await request.body()
            webhook_data = await request.json()

            # Дополнительное логирование для отладки домена
            from config.settings import settings
            if settings.domain_debug_logging or settings.webhook_domain_logging:
                headers = dict(request.headers)
                client_host = getattr(request.client, 'host', 'unknown') if request.client else 'unknown'
                logger.info(f"Webhook domain debug - Client: {client_host}")
                logger.info(f"Webhook domain debug - Host header: {headers.get('host', 'unknown')}")
                logger.info(f"Webhook domain debug - Expected domain: {settings.production_domain}")
                logger.info(f"Webhook domain debug - User-Agent: {headers.get('user-agent', 'unknown')}")


            # Валидация подписи
            if not await self._validate_webhook_signature(body, request.headers):
                self.logger.error("Invalid webhook signature")
                return JSONResponse(
                    {"status": "error", "message": "Invalid signature"},
                    status_code=401
                )

            # Определяем тип вебхука (покупка звезд или пополнение баланса)
            external_id = webhook_data.get("uuid", "")
            if external_id.startswith("recharge_"):
                # Обработка вебхука пополнения баланса
                success = await self.star_purchase_service.process_recharge_webhook(webhook_data)
            else:
                # Обработка вебхука покупки звезд
                success = await self.star_purchase_service.process_payment_webhook(webhook_data)

            if success:
                self.logger.info("Webhook processed successfully")
                return JSONResponse({"status": "ok"}, status_code=200)
            else:
                self.logger.error("Failed to process webhook")
                return JSONResponse(
                    {"status": "error", "message": "Processing failed"},
                    status_code=400
                )

        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in webhook: {e}")
            return JSONResponse(
                {"status": "error", "message": "Invalid JSON"},
                status_code=400
            )
        except Exception as e:
            self.logger.error(f"Error processing webhook: {e}")
            return JSONResponse(
                {"status": "error", "message": "Internal server error"},
                status_code=500
            )

    async def _validate_webhook_signature(self, body: bytes, headers: Dict[str, str]) -> bool:
        """Валидация подписи вебхука от Heleket с использованием HMAC SHA256"""
        try:
            from config.settings import settings
            webhook_secret = settings.webhook_secret

            if not webhook_secret:
                self.logger.warning("Webhook secret is not configured, skipping signature validation")
                return True  # В режиме разработки разрешаем без подписи

            # Извлекаем подпись из заголовков
            provided_signature = headers.get('X-Signature') or headers.get('x-signature')

            if not provided_signature:
                self.logger.warning("No X-Signature header provided in webhook request")
                return False

            # Вычисляем ожидаемую подпись
            expected_signature = self._calculate_signature(body)

            # Используем постоянное время сравнение для безопасности
            is_valid = hmac.compare_digest(expected_signature, provided_signature)

            if not is_valid:
                self.logger.error("Invalid webhook signature")
                return False

            self.logger.info("Webhook signature validation passed")
            return True

        except Exception as e:
            self.logger.error(f"Error validating webhook signature: {e}")
            return False

    def __init__(self, star_purchase_service: StarPurchaseService,
                 user_cache: Optional[UserCache] = None,
                 payment_cache: Optional[PaymentCache] = None,
                 webhook_secret: str = ""):
        self.star_purchase_service = star_purchase_service
        self.user_cache = user_cache
        self.payment_cache = payment_cache
        self.webhook_secret = webhook_secret
        self.logger = logging.getLogger(__name__)

    def _calculate_signature(self, body: bytes) -> str:
        """Вычисление HMAC подписи для вебхука"""
        # Используем секретный ключ из конфигурации
        secret_key = self.webhook_secret.encode('utf-8') if self.webhook_secret else b""

        if not secret_key:
            self.logger.warning("Webhook secret is not configured")
            return ""

        signature = hmac.new(
            secret_key,
            body,
            hashlib.sha256
        ).hexdigest()

        return signature


# Фабрика для создания обработчика вебхуков
class WebhookHandlerFactory:
    """Фабрика для создания обработчиков вебхуков"""

    @staticmethod
    def create_webhook_handler(
        user_repository: UserRepository,
        balance_repository: BalanceRepository,
        payment_service,  # PaymentService
        user_cache: Optional[UserCache] = None,
        payment_cache: Optional[PaymentCache] = None,
        webhook_secret: str = ""
    ) -> WebhookHandler:
        """Создание обработчика вебхуков"""

        # Создаем сервис покупки звезд
        star_purchase_service = StarPurchaseService(
            user_repository=user_repository,
            balance_repository=balance_repository,
            payment_service=payment_service,
            user_cache=user_cache,
            payment_cache=payment_cache
        )

        # Создаем и возвращаем обработчик вебхуков
        return WebhookHandler(
            star_purchase_service=star_purchase_service,
            user_cache=user_cache,
            payment_cache=payment_cache,
            webhook_secret=webhook_secret
        )
