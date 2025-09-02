"""
Unit-тесты для BalanceService с комплексным покрытием основных сценариев
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from datetime import datetime, timezone
from decimal import Decimal

from services.balance.balance_service import BalanceService
from repositories.user_repository import TransactionType, TransactionStatus
from services.cache.user_cache import UserCache


class TestBalanceService:
    """Комплексные тесты для BalanceService"""

    @pytest.fixture
    def mock_repositories(self):
        """Фикстура с mock репозиториями"""
        user_repo = Mock()
        balance_repo = Mock()
        user_cache = Mock(spec=UserCache)
        
        return {
            'user_repository': user_repo,
            'balance_repository': balance_repo,
            'user_cache': user_cache
        }

    @pytest.fixture
    def balance_service(self, mock_repositories):
        """Фикстура для создания BalanceService с моками"""
        return BalanceService(
            user_repository=mock_repositories['user_repository'],
            balance_repository=mock_repositories['balance_repository'],
            user_cache=mock_repositories['user_cache']
        )

    @pytest.fixture
    def test_balance_data(self):
        """Фикстура с тестовыми данными баланса"""
        return {
            "user_id": 123,
            "balance": 100.0,
            "currency": "TON",
            "updated_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        }

    @pytest.fixture
    def test_transaction_data(self):
        """Фикстура с тестовыми данными транзакции"""
        return {
            "id": 1,
            "user_id": 123,
            "transaction_type": "recharge",
            "status": "completed",
            "amount": 50.0,
            "currency": "TON",
            "description": "Пополнение баланса",
            "external_id": "test_payment_123",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "metadata": {"payment_uuid": "test_payment_123"}
        }

    @pytest.mark.asyncio
    async def test_get_user_balance_from_cache(self, balance_service, mock_repositories, test_balance_data):
        """Тест получения баланса из кеша"""
        # Настраиваем моки
        mock_repositories['user_cache'].get_user_balance = AsyncMock(return_value=100.0)
        
        result = await balance_service.get_user_balance(123)
        
        # Проверяем, что данные получены из кеша
        assert result["source"] == "cache"
        assert result["balance"] == 100.0
        assert result["user_id"] == 123
        mock_repositories['user_cache'].get_user_balance.assert_called_once_with(123)

    @pytest.mark.asyncio
    async def test_get_user_balance_from_database(self, balance_service, mock_repositories, test_balance_data):
        """Тест получения баланса из базы данных при отсутствии в кеше"""
        # Настраиваем моки - кеш пустой
        mock_repositories['user_cache'].get_user_balance = AsyncMock(return_value=None)
        mock_repositories['balance_repository'].get_user_balance = AsyncMock(return_value=test_balance_data)
        
        result = await balance_service.get_user_balance(123)
        
        # Проверяем, что данные получены из базы
        assert result["source"] == "database"
        assert result["balance"] == 100.0
        mock_repositories['user_cache'].get_user_balance.assert_called_once_with(123)
        mock_repositories['balance_repository'].get_user_balance.assert_called_once_with(123)

    @pytest.mark.asyncio
    async def test_get_user_balance_create_new(self, balance_service, mock_repositories):
        """Тест создания нового баланса для пользователя"""
        # Настраиваем моки - баланса нет нигде
        mock_repositories['user_cache'].get_user_balance = AsyncMock(return_value=None)
        mock_repositories['balance_repository'].get_user_balance = AsyncMock(return_value=None)
        mock_repositories['balance_repository'].create_user_balance = AsyncMock(return_value=True)
        
        result = await balance_service.get_user_balance(123)
        
        # Проверяем создание нулевого баланса
        assert result["balance"] == 0
        assert result["source"] == "database"
        mock_repositories['balance_repository'].create_user_balance.assert_called_once_with(123, 0)

    @pytest.mark.asyncio
    async def test_update_user_balance_success(self, balance_service, mock_repositories, test_balance_data):
        """Тест успешного обновления баланса"""
        # Настраиваем моки
        mock_repositories['balance_repository'].update_user_balance = AsyncMock(return_value=True)
        mock_repositories['balance_repository'].get_user_balance = AsyncMock(return_value=test_balance_data)
        
        result = await balance_service.update_user_balance(123, 50.0, "add")
        
        assert result is True
        mock_repositories['balance_repository'].update_user_balance.assert_called_once_with(123, 50.0, "add")
        mock_repositories['user_cache'].update_user_balance.assert_called_once_with(123, 100)

    @pytest.mark.asyncio
    async def test_update_user_balance_failure(self, balance_service, mock_repositories):
        """Тест неудачного обновления баланса"""
        mock_repositories['balance_repository'].update_user_balance = AsyncMock(return_value=False)
        
        result = await balance_service.update_user_balance(123, 50.0, "add")
        
        assert result is False
        mock_repositories['balance_repository'].update_user_balance.assert_called_once_with(123, 50.0, "add")
        mock_repositories['user_cache'].update_user_balance.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_transaction_success(self, balance_service, mock_repositories):
        """Тест успешного создания транзакции"""
        # Настраиваем моки
        mock_repositories['balance_repository'].create_transaction = AsyncMock(return_value=1)
        
        result = await balance_service.create_transaction(
            user_id=123,
            transaction_type="recharge",
            amount=50.0,
            description="Test transaction",
            external_id="test_123"
        )
        
        assert result == 1
        mock_repositories['balance_repository'].create_transaction.assert_called_once()
        mock_repositories['user_cache'].invalidate_user_cache.assert_called_once_with(123)

    @pytest.mark.asyncio
    async def test_create_transaction_invalid_type(self, balance_service, mock_repositories):
        """Тест создания транзакции с невалидным типом"""
        result = await balance_service.create_transaction(
            user_id=123,
            transaction_type="invalid_type",
            amount=50.0
        )
        
        assert result is None
        mock_repositories['balance_repository'].create_transaction.assert_not_called()

    @pytest.mark.asyncio
    async def test_complete_transaction_success(self, balance_service, mock_repositories, test_transaction_data):
        """Тест успешного завершения транзакции"""
        # Настраиваем моки
        mock_repositories['balance_repository'].update_transaction_status = AsyncMock(return_value=True)
        mock_repositories['balance_repository'].get_transaction_by_external_id = AsyncMock(
            return_value=test_transaction_data
        )
        
        result = await balance_service.complete_transaction(1, {"completed_at": "2024-01-01T10:00:00Z"})
        
        assert result is True
        mock_repositories['balance_repository'].update_transaction_status.assert_called_once()
        mock_repositories['user_cache'].invalidate_user_cache.assert_called_once_with(123)

    @pytest.mark.asyncio
    async def test_process_recharge_success(self, balance_service, mock_repositories):
        """Тест успешной обработки пополнения баланса"""
        # Настраиваем моки
        mock_repositories['balance_repository'].get_transaction_by_external_id = AsyncMock(return_value=None)
        mock_repositories['balance_repository'].create_transaction = AsyncMock(return_value=1)
        mock_repositories['balance_repository'].update_user_balance = AsyncMock(return_value=True)
        
        result = await balance_service.process_recharge(123, 50.0, "payment_123")
        
        assert result is True
        mock_repositories['balance_repository'].update_user_balance.assert_called_once_with(123, 50.0, "add")
        # Метод invalidate_user_cache вызывается дважды: в create_transaction и в process_recharge
        assert mock_repositories['user_cache'].invalidate_user_cache.call_count == 2
        mock_repositories['user_cache'].invalidate_user_cache.assert_any_call(123)

    @pytest.mark.asyncio
    async def test_process_recharge_duplicate(self, balance_service, mock_repositories, test_transaction_data):
        """Тест обработки дублирующего пополнения"""
        # Настраиваем моки для уже завершенной транзакции
        test_transaction_data["status"] = "completed"
        mock_repositories['balance_repository'].get_transaction_by_external_id = AsyncMock(
            return_value=test_transaction_data
        )
        
        result = await balance_service.process_recharge(123, 50.0, "payment_123")
        
        assert result is True  # Дубликат должен вернуть True
        mock_repositories['balance_repository'].update_user_balance.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_transaction_amount_valid(self, balance_service):
        """Тест валидации корректной суммы транзакции"""
        result = await balance_service.validate_transaction_amount(50.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_transaction_amount_invalid(self, balance_service):
        """Тест валидации невалидной суммы транзакции"""
        result = await balance_service.validate_transaction_amount(0.0)
        assert result is False
        
        result = await balance_service.validate_transaction_amount(-10.0)
        assert result is False
        
        result = await balance_service.validate_transaction_amount(1000001.0)
        assert result is False

    @pytest.mark.asyncio
    async def test_check_balance_sufficiency_sufficient(self, balance_service, mock_repositories, test_balance_data):
        """Тест проверки достаточности баланса (достаточно)"""
        mock_repositories['balance_repository'].get_user_balance = AsyncMock(return_value=test_balance_data)
        
        result = await balance_service.check_balance_sufficiency(123, 50.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_check_balance_sufficiency_insufficient(self, balance_service, mock_repositories, test_balance_data):
        """Тест проверки достаточности баланса (недостаточно)"""
        mock_repositories['balance_repository'].get_user_balance = AsyncMock(return_value=test_balance_data)
        
        result = await balance_service.check_balance_sufficiency(123, 150.0)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_user_balance_history(self, balance_service, mock_repositories, test_transaction_data):
        """Тест получения истории баланса"""
        # Настраиваем моки
        test_balance_data = {"balance": 100.0, "currency": "TON"}
        mock_repositories['balance_repository'].get_user_transactions = AsyncMock(
            return_value=[test_transaction_data]
        )
        mock_repositories['balance_repository'].get_user_balance = AsyncMock(return_value=test_balance_data)
        
        result = await balance_service.get_user_balance_history(123, 30)
        
        assert result["user_id"] == 123
        assert result["period_days"] == 30
        assert "initial_balance" in result
        assert "final_balance" in result
        assert len(result["transactions"]) == 1

    @pytest.mark.asyncio
    async def test_add_bonus_success(self, balance_service, mock_repositories):
        """Тест успешного начисления бонуса"""
        # Настраиваем моки для цепочки вызовов
        with patch.object(balance_service, 'create_transaction', AsyncMock(return_value=1)):
            with patch.object(balance_service, 'complete_transaction', AsyncMock(return_value=True)):
                result = await balance_service.add_bonus(123, 50.0, "Test bonus")
                
                assert result is True
                balance_service.create_transaction.assert_called_once()
                balance_service.complete_transaction.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_refund_success(self, balance_service, mock_repositories):
        """Тест успешной обработки возврата"""
        # Настраиваем моки для цепочки вызовов
        with patch.object(balance_service, 'create_transaction', AsyncMock(return_value=1)):
            with patch.object(balance_service, 'complete_transaction', AsyncMock(return_value=True)):
                result = await balance_service.process_refund(123, 50.0, "Test refund", "refund_123")
                
                assert result is True
                balance_service.create_transaction.assert_called_once()
                balance_service.complete_transaction.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_pending_transactions(self, balance_service, mock_repositories, test_transaction_data):
        """Тест получения ожидающих транзакций"""
        mock_repositories['balance_repository'].get_pending_transactions = AsyncMock(
            return_value=[test_transaction_data]
        )
        
        result = await balance_service.get_pending_transactions(10)
        
        assert len(result) == 1
        assert result[0]["id"] == 1
        mock_repositories['balance_repository'].get_pending_transactions.assert_called_once_with(10)

    @pytest.mark.asyncio
    async def test_get_recharge_history(self, balance_service, mock_repositories, test_transaction_data):
        """Тест получения истории пополнений"""
        mock_repositories['balance_repository'].get_user_transactions = AsyncMock(
            return_value=[test_transaction_data]
        )
        
        result = await balance_service.get_recharge_history(123, 5)
        
        assert len(result) == 1
        assert result[0]["amount"] == 50.0
        mock_repositories['balance_repository'].get_user_transactions.assert_called_once()


class TestBalanceServiceEdgeCases:
    """Тесты для edge-cases BalanceService"""
    
    @pytest.fixture
    def mock_repositories(self):
        """Фикстура с mock репозиториями"""
        user_repo = Mock()
        balance_repo = Mock()
        user_cache = Mock(spec=UserCache)
        
        return {
            'user_repository': user_repo,
            'balance_repository': balance_repo,
            'user_cache': user_cache
        }
    
    @pytest.fixture
    def balance_service(self, mock_repositories):
        """Фикстура для создания BalanceService с моками"""
        return BalanceService(
            user_repository=mock_repositories['user_repository'],
            balance_repository=mock_repositories['balance_repository'],
            user_cache=mock_repositories['user_cache']
        )
    
    @pytest.fixture
    def balance_service_no_cache(self):
        """Фикстура для BalanceService без кеша"""
        user_repo = Mock()
        balance_repo = Mock()
        return BalanceService(user_repo, balance_repo, None)

    @pytest.mark.asyncio
    async def test_get_user_balance_no_cache(self, balance_service_no_cache):
        """Тест получения баланса без кеша"""
        test_balance_data = {
            "user_id": 123,
            "balance": 100.0,
            "currency": "TON",
            "updated_at": datetime.utcnow().isoformat()
        }
        
        balance_service_no_cache.balance_repository.get_user_balance = AsyncMock(return_value=test_balance_data)
        
        result = await balance_service_no_cache.get_user_balance(123)
        
        assert result["source"] == "database"
        assert result["balance"] == 100.0

    @pytest.mark.asyncio
    async def test_update_user_balance_no_cache(self, balance_service_no_cache):
        """Тест обновления баланса без кеша"""
        balance_service_no_cache.balance_repository.update_user_balance = AsyncMock(return_value=True)
        
        result = await balance_service_no_cache.update_user_balance(123, 50.0, "add")
        
        assert result is True
        # Не должно быть вызовов к кешу
        if hasattr(balance_service_no_cache, 'user_cache'):
            assert balance_service_no_cache.user_cache is None

    @pytest.mark.asyncio
    async def test_create_transaction_error_handling(self, balance_service, mock_repositories):
        """Тест обработки ошибок при создании транзакции"""
        mock_repositories['balance_repository'].create_transaction = AsyncMock(side_effect=Exception("DB error"))
        # Мокируем логгер
        balance_service.logger.error = Mock()

        result = await balance_service.create_transaction(123, "recharge", 50.0)

        assert result is None
        # Проверяем, что логгер вызван с ошибкой
        balance_service.logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_transaction_not_found(self, balance_service, mock_repositories):
        """Тест завершения несуществующей транзакции"""
        mock_repositories['balance_repository'].update_transaction_status = AsyncMock(return_value=False)
        mock_repositories['balance_repository'].get_transaction_by_external_id = AsyncMock(return_value=None)
        
        result = await balance_service.complete_transaction(999, {})
        
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])