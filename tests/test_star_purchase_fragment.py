"""
Тесты для интеграции StarPurchaseService с FragmentService
"""
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, Mock

from services.payment.star_purchase_service import StarPurchaseService
from repositories.user_repository import TransactionType, TransactionStatus


class TestStarPurchaseServiceFragmentIntegration:
    """Тесты для интеграции StarPurchaseService с FragmentService"""
    
    @pytest.fixture
    def mock_repositories_and_services(self):
        """Фикстура для создания mock объектов"""
        # Mock UserRepository
        user_repository = Mock()
        user_repository.get_user = AsyncMock(return_value={
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
            "metadata": {"purchase_type": "fragment", "stars_count": 100}
        })
        balance_repository.get_user_transactions = AsyncMock(return_value=[])
        
        # Mock PaymentService - используем AsyncMock для асинхронных методов
        payment_service = AsyncMock()
        
        # Mock Cache services - используем AsyncMock для асинхронных методов
        payment_cache = AsyncMock()
        payment_cache.cache_payment_details = AsyncMock()
        payment_cache.get_payment_details = AsyncMock(return_value=None)
        
        user_cache = AsyncMock()
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
        return StarPurchaseService(**mock_repositories_and_services)
    
    @pytest.mark.asyncio
    async def test_create_star_purchase_with_fragment_success(self, star_purchase_service):
        """Тест успешной покупки звезд через Fragment API"""
        # Мock fragment_service.buy_stars_without_kyc для возврата успешного результата
        fragment_result = {
            "status": "success",
            "result": {
                "status": "completed",
                "stars_count": 100,
                "transaction_id": "fragment_tx_123"
            }
        }
        
        with patch.object(star_purchase_service.fragment_service, 'buy_stars_without_kyc', AsyncMock(return_value=fragment_result)):
            result = await star_purchase_service.create_star_purchase(
                user_id=123456789,
                amount=100,
                purchase_type="fragment"
            )
            
            # Проверяем результат
            assert result["status"] == "success"
            assert result["purchase_type"] == "fragment"
            assert result["stars_count"] == 100
            assert "result" in result
            assert result["transaction_id"] == 12345
            
            # Проверяем, что были вызваны необходимые методы
            star_purchase_service.user_repository.get_user.assert_called_once_with(123456789)
            star_purchase_service.balance_repository.create_transaction.assert_called_once()
            star_purchase_service.balance_repository.update_transaction_status.assert_called_once()
            # Проверяем, что update_transaction_status был вызван с правильными аргументами (без проверки точного времени)
            call_args = star_purchase_service.balance_repository.update_transaction_status.call_args
            assert call_args[0][0] == 12345  # transaction_id
            assert call_args[0][1] == TransactionStatus.COMPLETED  # status
            assert "metadata" in call_args[1]  # metadata present
            metadata = call_args[1]["metadata"]
            assert "purchase_completed_at" in metadata  # timestamp present
            assert metadata["fragment_result"] == fragment_result["result"]  # fragment result
            assert metadata["purchase_type"] == "fragment"  # purchase type
    
    @pytest.mark.asyncio
    async def test_create_star_purchase_with_fragment_failure(self, star_purchase_service):
        """Тест неудачной покупки звезд через Fragment API"""
        # Мock fragment_service.buy_stars_without_kyc для возврата ошибки
        fragment_result = {
            "status": "failed",
            "error": "Insufficient balance"
        }
        
        with patch.object(star_purchase_service.fragment_service, 'buy_stars_without_kyc', AsyncMock(return_value=fragment_result)):
            result = await star_purchase_service.create_star_purchase(
                user_id=123456789,
                amount=100,
                purchase_type="fragment"
            )
            
            # Проверяем результат
            assert result["status"] == "failed"
            assert "Insufficient balance" in result["error"]
            assert result["transaction_id"] == 12345
            
            # Проверяем, что были вызваны необходимые методы
            star_purchase_service.user_repository.get_user.assert_called_once_with(123456789)
            star_purchase_service.balance_repository.create_transaction.assert_called_once()
            star_purchase_service.balance_repository.update_transaction_status.assert_called_once()
            # Проверяем, что update_transaction_status был вызван с правильными аргументами (без проверки точного времени)
            call_args = star_purchase_service.balance_repository.update_transaction_status.call_args
            assert call_args[0][0] == 12345  # transaction_id
            assert call_args[0][1] == TransactionStatus.FAILED  # status
            assert "metadata" in call_args[1]  # metadata present
            metadata = call_args[1]["metadata"]
            assert "error" in metadata  # error present
            assert "failed_at" in metadata  # timestamp present
            assert metadata["error"] == "Insufficient balance"  # error message
    
    @pytest.mark.asyncio
    async def test_create_star_purchase_with_fragment_exception(self, star_purchase_service):
        """Тест покупки звезд через Fragment API с исключением"""
        # Мock fragment_service.buy_stars_without_kyc для выброса исключения
        with patch.object(star_purchase_service.fragment_service, 'buy_stars_without_kyc', AsyncMock(side_effect=Exception("Network error"))):
            result = await star_purchase_service.create_star_purchase(
                user_id=123456789,
                amount=100,
                purchase_type="fragment"
            )
            
            # Проверяем результат
            assert result["status"] == "failed"
            assert "Network error" in result["error"]
            
            # Проверяем, что были вызваны необходимые методы
            star_purchase_service.user_repository.get_user.assert_called_once_with(123456789)
            star_purchase_service.balance_repository.create_transaction.assert_called_once()
            # При исключении update_transaction_status не вызывается, проверяем это
            star_purchase_service.balance_repository.update_transaction_status.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__])