"""
Тест функциональности отмены инвойса при нажатии кнопки "Назад"
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import CallbackQuery, User, Message
from aiogram import Bot

from services.payment.star_purchase_service import StarPurchaseService
from handlers.payment_handler import PaymentHandler
from repositories.user_repository import TransactionType, TransactionStatus


class TestCancelInvoiceFunctionality:
    """Тесты отмены инвойса"""

    @pytest.fixture
    def mock_repositories(self):
        """Мок репозиториев"""
        user_repo = AsyncMock()
        balance_repo = AsyncMock()
        return user_repo, balance_repo

    @pytest.fixture
    def mock_services(self, mock_repositories):
        """Мок сервисов"""
        user_repo, balance_repo = mock_repositories
        payment_service = AsyncMock()
        payment_cache = AsyncMock()
        user_cache = AsyncMock()
        
        star_purchase_service = StarPurchaseService(
            user_repository=user_repo,
            balance_repository=balance_repo,
            payment_service=payment_service,
            payment_cache=payment_cache,
            user_cache=user_cache
        )
        
        return star_purchase_service, user_repo, balance_repo

    @pytest.fixture
    def mock_callback_query(self):
        """Мок callback query"""
        callback = MagicMock()
        callback.from_user = MagicMock()
        callback.from_user.id = 12345
        callback.data = "cancel_recharge_test_uuid_123"
        callback.message = MagicMock()
        callback.message.edit_text = AsyncMock()
        callback.answer = AsyncMock()
        return callback

    @pytest.mark.asyncio
    async def test_successful_invoice_cancellation(self, mock_services, mock_callback_query):
        """Тест успешной отмены инвойса"""
        star_purchase_service, user_repo, balance_repo = mock_services
        
        # Настраиваем мок для получения pending транзакций
        pending_transaction = {
            "id": 1,
            "user_id": 12345,
            "transaction_type": "recharge",
            "status": "pending",
            "amount": 100.0,
            "external_id": "recharge_12345_test_uuid_123",
            "metadata": '{"payment_uuid": "test_uuid_123", "payment_url": "https://example.com"}'
        }
        
        balance_repo.get_user_transactions.return_value = [pending_transaction]
        balance_repo.update_transaction_status.return_value = True
        
        # Тестируем отмену
        result = await star_purchase_service.cancel_specific_recharge(12345, "test_uuid_123")
        
        # Проверяем результат
        assert result is True
        balance_repo.get_user_transactions.assert_called_once_with(
            user_id=12345,
            transaction_type=TransactionType.RECHARGE,
            status=TransactionStatus.PENDING
        )
        balance_repo.update_transaction_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_cancellation_when_uuid_not_found(self, mock_services):
        """Тест fallback отмены когда UUID не найден"""
        star_purchase_service, user_repo, balance_repo = mock_services
        
        # Настраиваем мок для получения pending транзакций без нужного UUID
        pending_transaction = {
            "id": 1,
            "user_id": 12345,
            "transaction_type": "recharge", 
            "status": "pending",
            "amount": 100.0,
            "external_id": "recharge_12345_other_uuid",
            "metadata": '{"payment_uuid": "other_uuid", "payment_url": "https://example.com"}'
        }
        
        balance_repo.get_user_transactions.return_value = [pending_transaction]
        balance_repo.update_transaction_status.return_value = True
        
        # Тестируем отмену с неизвестным UUID
        result = await star_purchase_service.cancel_specific_recharge(12345, "unknown_uuid")
        
        # Должен сработать fallback и отменить последнюю pending транзакцию
        assert result is True
        balance_repo.update_transaction_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_pending_transactions_to_cancel(self, mock_services):
        """Тест когда нет pending транзакций для отмены"""
        star_purchase_service, user_repo, balance_repo = mock_services
        
        # Настраиваем мок для пустого списка pending транзакций
        balance_repo.get_user_transactions.return_value = []
        
        # Тестируем отмену
        result = await star_purchase_service.cancel_specific_recharge(12345, "test_uuid")
        
        # Должен вернуть False
        assert result is False
        balance_repo.update_transaction_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_payment_handler_cancel_integration(self, mock_callback_query):
        """Тест интеграции с PaymentHandler"""
        
        # Мок всех необходимых сервисов для PaymentHandler
        user_repository = AsyncMock()
        payment_service = AsyncMock()
        balance_service = AsyncMock()
        star_purchase_service = AsyncMock()
        star_purchase_service.cancel_specific_recharge.return_value = True
        
        payment_handler = PaymentHandler(
            user_repository=user_repository,
            payment_service=payment_service,
            balance_service=balance_service,
            star_purchase_service=star_purchase_service
        )
        bot = AsyncMock()
        
        # Тестируем обработчик отмены
        await payment_handler.cancel_specific_recharge(mock_callback_query, bot, "test_uuid_123")
        
        # Проверяем что сервис был вызван
        star_purchase_service.cancel_specific_recharge.assert_called_once_with(12345, "test_uuid_123")

    @pytest.mark.asyncio
    async def test_cancel_with_database_error(self, mock_services):
        """Тест обработки ошибки базы данных при отмене"""
        star_purchase_service, user_repo, balance_repo = mock_services
        
        # Настраиваем мок для ошибки базы данных
        balance_repo.get_user_transactions.side_effect = Exception("Database error")
        
        # Тестируем отмену
        result = await star_purchase_service.cancel_specific_recharge(12345, "test_uuid")
        
        # Должен вернуть False при ошибке
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_with_external_id_matching(self, mock_services):
        """Тест отмены по external_id содержащему UUID"""
        star_purchase_service, user_repo, balance_repo = mock_services
        
        # Настраиваем мок для транзакции с UUID в external_id
        pending_transaction = {
            "id": 1,
            "user_id": 12345,
            "transaction_type": "recharge",
            "status": "pending", 
            "amount": 100.0,
            "external_id": "recharge_12345_1703123456_uuid_abc123",
            "metadata": "{}"
        }
        
        balance_repo.get_user_transactions.return_value = [pending_transaction]
        balance_repo.update_transaction_status.return_value = True
        
        # Тестируем отмену по UUID в external_id
        result = await star_purchase_service.cancel_specific_recharge(12345, "uuid_abc123")
        
        # Должен найти и отменить транзакцию
        assert result is True
        balance_repo.update_transaction_status.assert_called_once()

    @pytest.mark.asyncio 
    async def test_cancel_updates_cache(self, mock_services):
        """Тест что отмена обновляет кеш"""
        star_purchase_service, user_repo, balance_repo = mock_services
        
        # Настраиваем мок
        pending_transaction = {
            "id": 1,
            "user_id": 12345,
            "transaction_type": "recharge",
            "status": "pending",
            "amount": 100.0,
            "external_id": "recharge_12345_test_uuid",
            "metadata": '{"payment_uuid": "test_uuid"}'
        }
        
        balance_repo.get_user_transactions.return_value = [pending_transaction]
        balance_repo.update_transaction_status.return_value = True
        
        # Тестируем отмену
        result = await star_purchase_service.cancel_specific_recharge(12345, "test_uuid")
        
        # Проверяем что кеш инвалидирован
        assert result is True
        star_purchase_service.user_cache.invalidate_user_cache.assert_called_once_with(12345)


if __name__ == "__main__":
    # Запуск тестов
    pytest.main([__file__, "-v"])
