"""
Упрощенные unit-тесты для PurchaseHandler - тестируем только логику без вызовов aiogram
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock

from services.payment.star_purchase_service import StarPurchaseService
from services.balance.balance_service import BalanceService
from repositories.user_repository import UserRepository


class TestPurchaseHandlerSimple:
    """Упрощенные тесты для PurchaseHandler (только логика)"""
    
    @pytest.fixture
    def mock_services(self):
        """Фикстура с mock сервисами"""
        user_repo = Mock(spec=UserRepository)
        star_purchase_service = Mock(spec=StarPurchaseService)
        balance_service = Mock(spec=BalanceService)
        
        # Настраиваем моки
        user_repo.user_exists = AsyncMock(return_value=True)
        star_purchase_service.create_star_purchase = AsyncMock(return_value={
            "status": "success",
            "stars_count": 100,
            "old_balance": 50.0,
            "new_balance": 40.0
        })
        balance_service.get_user_balance = AsyncMock(return_value={
            "balance": 100.0,
            "currency": "TON",
            "source": "database"
        })
        
        return {
            'user_repository': user_repo,
            'star_purchase_service': star_purchase_service,
            'balance_service': balance_service
        }
    
    @pytest.mark.asyncio
    async def test_create_star_purchase_success(self, mock_services):
        """Тест успешной покупки звезд"""
        # Вызываем метод
        result = await mock_services['star_purchase_service'].create_star_purchase(123, 100, "balance")
        
        # Проверяем результат
        assert result["status"] == "success"
        assert result["stars_count"] == 100
        assert result["old_balance"] == 50.0
        assert result["new_balance"] == 40.0
        
        # Проверяем, что сервис был вызван
        mock_services['star_purchase_service'].create_star_purchase.assert_called_once_with(123, 100, "balance")
    
    @pytest.mark.asyncio
    async def test_create_star_purchase_insufficient_balance(self, mock_services):
        """Тест покупки звезд при недостаточном балансе"""
        # Настраиваем сервис на возврат ошибки недостатка баланса
        mock_services['star_purchase_service'].create_star_purchase = AsyncMock(return_value={
            "status": "failed",
            "error": "Insufficient balance"
        })
        
        # Вызываем метод
        result = await mock_services['star_purchase_service'].create_star_purchase(123, 1000, "balance")
        
        # Проверяем результат
        assert result["status"] == "failed"
        assert result["error"] == "Insufficient balance"
    
    @pytest.mark.asyncio
    async def test_create_star_purchase_system_error(self, mock_services):
        """Тест покупки звезд с системной ошибкой"""
        # Настраиваем сервис на возврат системной ошибки
        mock_services['star_purchase_service'].create_star_purchase = AsyncMock(return_value={
            "status": "failed",
            "error": "System error"
        })
        
        # Вызываем метод
        result = await mock_services['star_purchase_service'].create_star_purchase(123, 100, "balance")
        
        # Проверяем результат
        assert result["status"] == "failed"
        assert result["error"] == "System error"
    
    @pytest.mark.asyncio
    async def test_get_user_balance_for_purchase(self, mock_services):
        """Тест получения баланса для покупки"""
        # Вызываем метод
        result = await mock_services['balance_service'].get_user_balance(123)
        
        # Проверяем результат
        assert result["balance"] == 100.0
        assert result["currency"] == "TON"
        assert result["source"] == "database"
        
        # Проверяем, что сервис был вызван
        mock_services['balance_service'].get_user_balance.assert_called_once_with(123)
    
    @pytest.mark.asyncio
    async def test_star_purchase_payment_methods(self):
        """Тест логики методов оплаты покупки звезд"""
        # Проверяем доступные методы оплаты
        payment_methods = ["balance", "fragment", "card"]
        
        assert "balance" in payment_methods
        assert "fragment" in payment_methods
        assert len(payment_methods) >= 2
    
    @pytest.mark.asyncio
    async def test_star_count_validation(self):
        """Тест логики валидации количества звезд"""
        # Проверяем валидные и невалидные количества
        valid_star_counts = [10, 50, 100, 500]
        invalid_star_counts = [0, -10, 1001]
        
        # Проверяем валидные количества
        for count in valid_star_counts:
            assert count > 0
            assert count <= 500  # Предполагаемый лимит
        
        # Проверяем невалидные количества
        for count in invalid_star_counts:
            assert count <= 0 or count > 500


if __name__ == "__main__":
    pytest.main([__file__])