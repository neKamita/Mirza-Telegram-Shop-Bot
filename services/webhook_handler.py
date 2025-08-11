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
from services.star_purchase_service import StarPurchaseService
from services.user_cache import UserCache
from services.payment_cache import PaymentCache


class WebhookHandler:
    """Обработчик вебхуков от Heleket"""

    def __init__(self, star_purchase_service: StarPurchaseService,
                 user_cache: Optional[UserCache] = None,
                 payment_cache: Optional[PaymentCache] = None):
        self.star_purchase_service = star_purchase_service
        self.user_cache = user_cache
        self.payment_cache = payment_cache
        self.logger = logging.getLogger(__name__)

    async def handle_payment_webhook(self, request: Request) -> JSONResponse:
        """Обработка вебхука от платежной системы"""
        try:
            # Получаем данные из запроса
            body = await request.body()
            webhook_data = await request.json()

            self.logger.info(f"Received webhook data: {webhook_data}")

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
        """Валидация подписи вебхука от Heleket"""
        try:
            # В реальном проекте здесь должна быть логика проверки HMAC подписи
            # using secret key from Heleket

            # Для примера просто проверяем наличие необходимых полей
            webhook_data = json.loads(body.decode('utf-8'))

            # Проверяем обязательные поля
            required_fields = ['uuid', 'status', 'amount']
            for field in required_fields:
                if field not in webhook_data:
                    self.logger.error(f"Missing required field: {field}")
                    return False

            # Здесь должна быть проверка HMAC подписи
            # signature = headers.get('X-Signature')
            # expected_signature = self._calculate_signature(body)
            # if not hmac.compare_digest(signature, expected_signature):
            #     return False

            return True

        except Exception as e:
            self.logger.error(f"Error validating webhook signature: {e}")
            return False

    def _calculate_signature(self, body: bytes) -> str:
        """Вычисление HMAC подписи для вебхука"""
        # В реальном проекте здесь должна быть логика вычисления подписи
        # using secret key from Heleket
        secret_key = b"your-secret-key-here"  # Должен храниться в конфигурации

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
        payment_cache: Optional[PaymentCache] = None
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
            payment_cache=payment_cache
        )
