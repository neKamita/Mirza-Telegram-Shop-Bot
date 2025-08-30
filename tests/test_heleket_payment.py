
"""
Тесты для функционала пополнения баланса через Heleket
"""
import pytest
import asyncio
import json
from unittest.mock import patch, AsyncMock, Mock, MagicMock
from datetime import datetime

from services.payment.payment_service import PaymentService
from services.payment.star_purchase_service import StarPurchaseService
from services.webhook.webhook_handler import WebhookHandler, WebhookHandlerFactory
from repositories.user_repository import UserRepository, TransactionType, TransactionStatus
from repositories.balance_repository import BalanceRepository
from services.cache.user_cache import UserCache
from services.cache.payment_cache import PaymentCache


class TestHeleketPayment:
    """Тесты для пополнения баланса через Heleket API"""

    @pytest.fixture
    def mock_repositories_and_services(self):
        """Фикстура для создания mock объектов"""
        # Mock UserRepository
        user_repository = Mock()
        user_repository.get_user_by_id = AsyncMock(return_value={
            "user_id": 123456789,
            "telegram_username": "@testuser"
        })
        
        # Mock BalanceRepository
        balance_repository = Mock()
        balance_repository.create_transaction = AsyncMock(return_value=12345)
        balance_repository.update_transaction_status = AsyncMock(return_value=True)
        balance_repository.update_user_balance = AsyncMock(return_value=True)
        balance_repository.get_user_balance = AsyncMock(return_value={"balance": "1000.00"})
        balance_repository.get_transaction_by_external_id = AsyncMock(return_value={
            "id": 12345,
            "user_id": 123456789,
            "status": "pending",
            "metadata": {"recharge_amount": 100, "recharge_type": "heleket"}
        })
        balance_repository.get_user_transactions = AsyncMock(return_value=[])
        
        # Mock PaymentService - используем AsyncMock для всех методов
        payment_service = AsyncMock()
        payment_service.create_recharge_invoice.return_value = {
            "status": "success",
            "result": {
                "uuid": "test_uuid_123",
                "url": "https://heleket.com/pay/test_uuid_123",
                "amount": "100",
                "currency": "TON"
            }
        }
        payment_service.create_recharge_invoice_for_user.return_value = {
            "status": "success",
            "result": {
                "uuid": "recharge_test_uuid_123",
                "url": "https://heleket.com/pay/recharge_test_uuid_123",
                "amount": "100",
                "currency": "TON"
            }
        }
        
        # Mock Cache services
        payment_cache = Mock()
        payment_cache.cache_payment_details = AsyncMock()
        payment_cache.get_payment_details = AsyncMock(return_value=None)
        
        user_cache = Mock()
        user_cache.cache_user_balance = AsyncMock()
        user_cache.get_user_balance = AsyncMock(return_value=None)
        user_cache.invalidate_user_cache = AsyncMock()
        
        return {
            "user_repository": user_repository,
            "balance_repository": balance_repository,
            "payment_service": payment_service,
            "payment_cache": payment_cache,
            "user_cache": user_cache
        }
    
    @pytest.fixture
    def star_purchase_service(self, mock_repositories_and_services):
        """Фикстура для создания экземпляра StarPurchaseService"""
        return StarPurchaseService(
            user_repository=mock_repositories_and_services["user_repository"],
            balance_repository=mock_repositories_and_services["balance_repository"],
            payment_service=mock_repositories_and_services["payment_service"],
            payment_cache=mock_repositories_and_services["payment_cache"],
            user_cache=mock_repositories_and_services["user_cache"]
        )
    
    @pytest.fixture
    def webhook_handler(self, mock_repositories_and_services):
        """Фикстура для создания WebhookHandler"""
        return WebhookHandlerFactory.create_webhook_handler(
            user_repository=mock_repositories_and_services["user_repository"],
            balance_repository=mock_repositories_and_services["balance_repository"],
            payment_service=mock_repositories_and_services["payment_service"],
            user_cache=mock_repositories_and_services["user_cache"],
            payment_cache=mock_repositories_and_services["payment_cache"],
            webhook_secret="test_secret"
        )

    @pytest.mark.asyncio
    async def test_create_recharge_success(self, star_purchase_service):
        """Тест успешного создания счета на пополнение баланса"""
        result = await star_purchase_service.create_recharge(
            user_id=123456789,
            amount=100.0
        )
        
        # Проверяем результат
        assert result["status"] == "success"
        assert result["recharge_amount"] == 100.0
        assert "transaction_id" in result
        assert "result" in result
        assert result["result"]["uuid"] == "recharge_test_uuid_123"
        
        # Проверяем, что были вызваны необходимые методы
        star_purchase_service.payment_service.create_recharge_invoice_for_user.assert_called_once()
        star_purchase_service.balance_repository.create_transaction.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_recharge_invalid_amount(self, star_purchase_service):
        """Тест создания пополнения с невалидной суммой"""
        result = await star_purchase_service.create_recharge(
            user_id=123456789,
            amount=5.0  # Меньше минимальной суммы (10 TON)
        )
        
        assert result["status"] == "failed"
        assert "Invalid recharge amount" in result["error"]

    @pytest.mark.asyncio
    async def test_create_recharge_payment_failure(self, star_purchase_service, mock_repositories_and_services):
        """Тест создания пополнения при ошибке платежной системы"""
        # Настраиваем mock для возврата ошибки
        mock_repositories_and_services["payment_service"].create_recharge_invoice_for_user.return_value = {
            "status": "failed",
            "error": "Payment system error"
        }
        
        result = await star_purchase_service.create_recharge(
            user_id=123456789,
            amount=100.0
        )
        
        assert result["status"] == "failed"
        assert "Payment system error" in result["error"]
        star_purchase_service.balance_repository.update_transaction_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_recharge_webhook_success(self, star_purchase_service):
        """Тест успешной обработки вебхука пополнения баланса"""
        webhook_data = {
            "uuid": "recharge_test_uuid_123",
            "status": "paid",
            "amount": "100.0"
        }
        
        # Mock валидации подписи, чтобы пропустить проверку
        with patch.object(star_purchase_service, '_validate_webhook_signature', AsyncMock(return_value=True)):
            # Добавляем отладочную информацию
            print(f"DEBUG: Webhook data: {webhook_data}")
            print(f"DEBUG: Webhook status type: {type(webhook_data['status'])}")
            print(f"DEBUG: Webhook status value: {webhook_data['status']}")
            
            result = await star_purchase_service.process_recharge_webhook(webhook_data)
            
            print(f"DEBUG: Process result: {result}")
        
        assert result is True
        star_purchase_service.balance_repository.update_user_balance.assert_called_once()
        star_purchase_service.balance_repository.update_transaction_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_recharge_webhook_failed(self, star_purchase_service):
        """Тест обработки вебхука с неуспешным статусом"""
        webhook_data = {
            "uuid": "recharge_test_uuid_123",
            "status": "failed",
            "amount": "100.0",
            "error": "Payment failed"
        }
        
        result = await star_purchase_service.process_recharge_webhook(webhook_data)
        
        assert result is True
        star_purchase_service.balance_repository.update_transaction_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_recharge_webhook_invalid_data(self, star_purchase_service):
        """Тест обработки вебхука с невалидными данными"""
        webhook_data = {
            "status": "paid"  # Нет uuid
        }
        
        result = await star_purchase_service.process_recharge_webhook(webhook_data)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_process_recharge_webhook_transaction_not_found(self, star_purchase_service):
        """Тест обработки вебхука когда транзакция не найдена"""
        # Настраиваем mock для возврата None (транзакция не найдена)
        star_purchase_service.balance_repository.get_transaction_by_external_id = AsyncMock(return_value=None)
        
        webhook_data = {
            "uuid": "recharge_non_existent_uuid",
            "status": "paid",
            "amount": "100.0"
        }
        
        result = await star_purchase_service.process_recharge_webhook(webhook_data)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_webhook_handler_recharge_success(self, webhook_handler):
        """Тест успешной обработки вебхука через WebhookHandler"""
        # Mock процесса вебхука
        with patch.object(webhook_handler.star_purchase_service, 'process_recharge_webhook', AsyncMock(return_value=True)):
            # Mock request
            mock_request = Mock()
            mock_request.body = AsyncMock(return_value=b'{"uuid": "recharge_123", "status": "paid", "amount": "100"}')
            mock_request.json = AsyncMock(return_value={"uuid": "recharge_123", "status": "paid", "amount": "100"})
            mock_request.headers = {"x-signature": "test_signature"}
            
            # Mock валидации подписи
            with patch.object(webhook_handler, '_validate_webhook_signature', AsyncMock(return_value=True)):
                response = await webhook_handler.handle_payment_webhook(mock_request)
                
                assert response.status_code == 200
                assert response.body == b'{"status":"ok"}'

    @pytest.mark.asyncio
    async def test_webhook_handler_invalid_signature(self, webhook_handler):
        """Тест обработки вебхука с невалидной подписью"""
        mock_request = Mock()
        mock_request.body = AsyncMock(return_value=b'{"uuid": "test", "status": "paid"}')
        mock_request.json = AsyncMock(return_value={"uuid": "test", "status": "paid"})
        mock_request.headers = {"x-signature": "invalid_signature"}
        
        with patch.object(webhook_handler, '_validate_webhook_signature', AsyncMock(return_value=False)):
            response = await webhook_handler.handle_payment_webhook(mock_request)
            
            assert response.status_code == 401
            assert "Invalid signature" in response.body.decode()

    @pytest.mark.asyncio
    async def test_webhook_handler_json_error(self, webhook_handler):
        """Тест обработки вебхука с невалидным JSON"""
        mock_request = Mock()
        mock_request.body = AsyncMock(return_value=b'invalid json')
        mock_request.json = AsyncMock(side_effect=json.JSONDecodeError("Invalid JSON", "test", 0))
        
        response = await webhook_handler.handle_payment_webhook(mock_request)
        
        assert response.status_code == 400
        assert "Invalid JSON" in response.body.decode()

    @pytest.mark.asyncio
    async def test_complete_heleket_recharge_cycle(self, star_purchase_service, webhook_handler):
        """Комплексный тест полного цикла пополнения баланса через Heleket"""
        # Шаг 1: Создание пополнения баланса
        recharge_result = await star_purchase_service.create_recharge(
            user_id=123456789,
            amount=100.0
        )
        
        assert recharge_result["status"] == "success"
        assert "transaction_id" in recharge_result
        assert "result" in recharge_result
        assert "uuid" in recharge_result["result"]
        assert "url" in recharge_result["result"]
        
        payment_uuid = recharge_result["result"]["uuid"]
        transaction_id = recharge_result["transaction_id"]
        
        # Проверяем, что транзакция создана с правильным статусом
        star_purchase_service.balance_repository.create_transaction.assert_called_once()
        
        # Шаг 2: Имитация успешного платежа через вебхук
        webhook_data = {
            "uuid": payment_uuid,
            "status": "paid",
            "amount": "100.0"
        }
        
        # Mock валидации подписи
        with patch.object(webhook_handler, '_validate_webhook_signature', AsyncMock(return_value=True)):
            # Mock request для вебхука
            mock_request = Mock()
            mock_request.body = AsyncMock(return_value=json.dumps(webhook_data).encode())
            mock_request.json = AsyncMock(return_value=webhook_data)
            mock_request.headers = {"x-signature": "valid_signature"}
            
            # Обработка вебхука
            response = await webhook_handler.handle_payment_webhook(mock_request)
            
            assert response.status_code == 200
            assert response.body == b'{"status":"ok"}'
        
        # Проверяем, что баланс был обновлен
        star_purchase_service.balance_repository.update_user_balance.assert_called_once_with(
            123456789, 
            100.0, 
            "add"
        )
        
        # Проверяем инвалидацию кеша пользователя
        star_purchase_service.user_cache.invalidate_user_cache.assert_called_once_with(123456789)

    @pytest.mark.asyncio
    async def test_heleket_recharge_with_failed_payment(self, star_purchase_service, webhook_handler):
        """Тест обработки неуспешного платежа через вебхук"""
        # Создаем пополнение
        recharge_result = await star_purchase_service.create_recharge(
            user_id=123456789,
            amount=50.0
        )
        
        payment_uuid = recharge_result["result"]["uuid"]
        
        # Имитация неуспешного платежа
        webhook_data = {
            "uuid": payment_uuid,
            "status": "failed",
            "amount": "50.0",
            "error": "Payment declined"
        }
        
        with patch.object(webhook_handler, '_validate_webhook_signature', AsyncMock(return_value=True)):
            mock_request = Mock()
            mock_request.body = AsyncMock(return_value=json.dumps(webhook_data).encode())
            mock_request.json = AsyncMock(return_value=webhook_data)
            mock_request.headers = {"x-signature": "valid_signature"}
            
            response = await webhook_handler.handle_payment_webhook(mock_request)
            
            assert response.status_code == 200
        
        # Убеждаемся, что баланс НЕ был обновлен
        star_purchase_service.balance_repository.update_user_balance.assert_not_called()

    @pytest.mark.asyncio
    async def test_heleket_webhook_signature_validation(self, webhook_handler):
        """Тест валидации подписи вебхука"""
        webhook_data = {
            "uuid": "recharge_test_uuid_123",
            "status": "paid",
            "amount": "100.0"
        }
        
        # Mock запроса с невалидной подписью
        mock_request = Mock()
        mock_request.body = AsyncMock(return_value=json.dumps(webhook_data).encode())
        mock_request.json = AsyncMock(return_value=webhook_data)
        mock_request.headers = {"x-signature": "invalid_signature"}
        
        with patch.object(webhook_handler, '_validate_webhook_signature', AsyncMock(return_value=False)):
            response = await webhook_handler.handle_payment_webhook(mock_request)
            
            assert response.status_code == 401
            assert "Invalid signature" in response.body.decode()

    @pytest.mark.asyncio
    async def test_heleket_recharge_amount_validation(self, star_purchase_service):
        """Тест валидации суммы пополнения"""
        # Слишком маленькая сумма
        result = await star_purchase_service.create_recharge(
            user_id=123456789,
            amount=5.0  # Меньше минимальной (10 TON)
        )
        
        assert result["status"] == "failed"
        assert "Invalid recharge amount" in result["error"]
        
        # Слишком большая сумма
        result = await star_purchase_service.create_recharge(
            user_id=123456789,
            amount=20000.0  # Больше максимальной (10000 TON)
        )
        
        assert result["status"] == "failed"
        assert "Invalid recharge amount" in result["error"]

    @pytest.mark.asyncio
    async def test_heleket_recharge_concurrent_requests(self, star_purchase_service):
        """Тест обработки конкурентных запросов на пополнение"""
        # Создаем несколько одновременных запросов
        tasks = []
        for i in range(3):
            task = star_purchase_service.create_recharge(
                user_id=123456789 + i,
                amount=100.0
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        # Все запросы должны быть успешными
        for result in results:
            assert result["status"] == "success"
            assert "transaction_id" in result
            assert "result" in result

    @pytest.mark.asyncio
    async def test_heleket_webhook_idempotency(self, star_purchase_service, webhook_handler):
        """Тест идемпотентности обработки вебхуков"""
        # Создаем умный mock для отслеживания изменения статуса транзакции
        transaction_state = {
            "id": 12345,
            "user_id": 123456789,
            "status": "pending",  # Начальный статус
            "metadata": {"recharge_amount": 100, "recharge_type": "heleket"}
        }
        
        async def smart_get_transaction(uuid):
            return dict(transaction_state)
        
        # Переопределяем mock для возврата динамического состояния
        star_purchase_service.balance_repository.get_transaction_by_external_id = AsyncMock(side_effect=smart_get_transaction)
        
        # Создаем пополнение
        recharge_result = await star_purchase_service.create_recharge(
            user_id=123456789,
            amount=100.0
        )
        
        payment_uuid = recharge_result["result"]["uuid"]
        
        # Мокируем update_transaction_status для обновления состояния
        original_update = star_purchase_service.balance_repository.update_transaction_status
        
        async def smart_update_transaction_status(transaction_id, status, metadata=None):
            if status == TransactionStatus.COMPLETED:
                transaction_state["status"] = "completed"
            return True
        
        star_purchase_service.balance_repository.update_transaction_status = AsyncMock(side_effect=smart_update_transaction_status)
        
        # Обрабатываем первый вебхук
        webhook_data = {
            "uuid": payment_uuid,
            "status": "paid",
            "amount": "100.0"
        }
        
        with patch.object(webhook_handler, '_validate_webhook_signature', AsyncMock(return_value=True)):
            mock_request = Mock()
            mock_request.body = AsyncMock(return_value=json.dumps(webhook_data).encode())
            mock_request.json = AsyncMock(return_value=webhook_data)
            mock_request.headers = {"x-signature": "valid_signature"}
            
            # Первый вызов - должен обновить баланс
            response1 = await webhook_handler.handle_payment_webhook(mock_request)
            assert response1.status_code == 200
            
            # Второй вызов с теми же данными - должен быть идемпотентным
            response2 = await webhook_handler.handle_payment_webhook(mock_request)
            assert response2.status_code == 200
            
            # Проверяем, что баланс обновлялся только один раз
            star_purchase_service.balance_repository.update_user_balance.assert_called_once()
            
            # Проверяем, что транзакция завершалась только один раз
            # update_transaction_status вызывается один раз при завершении (completed)
            # так как создание транзакции происходит в другом методе (create_recharge)
            star_purchase_service.balance_repository.update_transaction_status.assert_called_once()
            
            # Проверяем, что вызов был с правильными параметрами (игнорируя метаданные)
            call_args = star_purchase_service.balance_repository.update_transaction_status.call_args
            assert call_args[0][0] == 12345  # transaction_id
            assert call_args[0][1] == TransactionStatus.COMPLETED  # status
            
            # Восстанавливаем оригинальный mock
            star_purchase_service.balance_repository.update_transaction_status = original_update


if __name__ == "__main__":
    pytest.main([__file__])