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
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat()
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
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
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

    @pytest.mark.asyncio
    async def test_get_user_transactions_success(self, balance_service, mock_repositories, test_transaction_data):
        """Тест успешного получения транзакций пользователя"""
        mock_repositories['balance_repository'].get_user_transactions = AsyncMock(
            return_value=[test_transaction_data]
        )
        
        result = await balance_service.get_user_transactions(123, 25)
        
        assert len(result) == 1
        assert result[0]["id"] == 1
        assert result[0]["amount"] == 50.0
        mock_repositories['balance_repository'].get_user_transactions.assert_called_once_with(123, 25)

    @pytest.mark.asyncio
    async def test_get_user_transactions_default_limit(self, balance_service, mock_repositories, test_transaction_data):
        """Тест получения транзакций с лимитом по умолчанию"""
        mock_repositories['balance_repository'].get_user_transactions = AsyncMock(
            return_value=[test_transaction_data]
        )
        
        result = await balance_service.get_user_transactions(123)
        
        assert len(result) == 1
        mock_repositories['balance_repository'].get_user_transactions.assert_called_once_with(123, 50)

    @pytest.mark.asyncio
    async def test_get_user_transactions_error_handling(self, balance_service, mock_repositories):
        """Тест обработки ошибок при получении транзакций"""
        mock_repositories['balance_repository'].get_user_transactions = AsyncMock(
            side_effect=Exception("Database error")
        )
        balance_service.logger.error = Mock()
        
        result = await balance_service.get_user_transactions(123)
        
        assert result == []
        balance_service.logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_fail_transaction_success(self, balance_service, mock_repositories, test_transaction_data):
        """Тест успешного завершения транзакции с ошибкой"""
        mock_repositories['balance_repository'].update_transaction_status = AsyncMock(return_value=True)
        mock_repositories['balance_repository'].get_transaction_by_external_id = AsyncMock(
            return_value=test_transaction_data
        )
        
        result = await balance_service.fail_transaction(1, {"failed_at": "2024-01-01T10:00:00Z"})
        
        assert result is True
        mock_repositories['balance_repository'].update_transaction_status.assert_called_once()
        mock_repositories['user_cache'].invalidate_user_cache.assert_called_once_with(123)

    @pytest.mark.asyncio
    async def test_fail_transaction_error_handling(self, balance_service, mock_repositories, test_transaction_data):
        """Тест обработки ошибок при завершении транзакции с ошибкой"""
        mock_repositories['balance_repository'].update_transaction_status = AsyncMock(
            side_effect=Exception("Database error")
        )
        mock_repositories['balance_repository'].get_transaction_by_external_id = AsyncMock(
            return_value=test_transaction_data
        )
        balance_service.logger.error = Mock()
        
        result = await balance_service.fail_transaction(1, {})
        
        assert result is False
        balance_service.logger.error.assert_called_once()
        mock_repositories['user_cache'].invalidate_user_cache.assert_not_called()

    @pytest.mark.asyncio
    async def test_fail_transaction_error_no_cache(self, balance_service, mock_repositories, test_transaction_data):
        """Тест обработки ошибок при завершении транзакции без кеша"""
        # Временно отключаем кеш
        original_cache = balance_service.user_cache
        balance_service.user_cache = None
        
        mock_repositories['balance_repository'].update_transaction_status = AsyncMock(
            side_effect=Exception("Database error")
        )
        mock_repositories['balance_repository'].get_transaction_by_external_id = AsyncMock(
            return_value=test_transaction_data
        )
        balance_service.logger.error = Mock()
        
        result = await balance_service.fail_transaction(1, {})
        
        assert result is False
        balance_service.logger.error.assert_called_once()
        
        # Восстанавливаем кеш
        balance_service.user_cache = original_cache

    @pytest.mark.asyncio
    async def test_get_transaction_statistics_success(self, balance_service, mock_repositories):
        """Тест успешного получения статистики транзакций"""
        test_stats = {
            "total_transactions": 5,
            "successful_transactions": 4,
            "failed_transactions": 1,
            "total_amount": 250.0,
            "average_amount": 50.0
        }
        mock_repositories['balance_repository'].get_transaction_statistics = AsyncMock(
            return_value=test_stats
        )
        
        result = await balance_service.get_transaction_statistics(123)
        
        assert result == test_stats
        mock_repositories['balance_repository'].get_transaction_statistics.assert_called_once_with(123)

    @pytest.mark.asyncio
    async def test_get_transaction_statistics_error_handling(self, balance_service, mock_repositories):
        """Тест обработки ошибок при получении статистики транзакций"""
        mock_repositories['balance_repository'].get_transaction_statistics = AsyncMock(
            side_effect=Exception("Database error")
        )
        balance_service.logger.error = Mock()
        
        result = await balance_service.get_transaction_statistics(123)
        
        assert result == {}
        balance_service.logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_transaction_statistics_empty_result(self, balance_service, mock_repositories):
        """Тест получения пустой статистики транзакций"""
        mock_repositories['balance_repository'].get_transaction_statistics = AsyncMock(
            return_value={}
        )
        
        result = await balance_service.get_transaction_statistics(123)
        
        assert result == {}
        mock_repositories['balance_repository'].get_transaction_statistics.assert_called_once_with(123)

    @pytest.mark.asyncio
    async def test_get_user_balance_with_transactions_success(self, balance_service, mock_repositories):
        """Тест успешного получения баланса с транзакциями"""
        test_balance_data = {
            "balance": 100.0,
            "currency": "TON",
            "transactions": [
                {"id": 1, "amount": 50.0, "type": "recharge"},
                {"id": 2, "amount": 30.0, "type": "purchase"}
            ]
        }
        mock_repositories['balance_repository'].get_user_balance_with_transactions = AsyncMock(
            return_value=test_balance_data
        )
        
        result = await balance_service.get_user_balance_with_transactions(123, 10)
        
        assert result == test_balance_data
        mock_repositories['balance_repository'].get_user_balance_with_transactions.assert_called_once_with(123, 10)

    @pytest.mark.asyncio
    async def test_get_user_balance_with_transactions_default_limit(self, balance_service, mock_repositories):
        """Тест получения баланса с транзакциями с лимитом по умолчанию"""
        test_balance_data = {"balance": 100.0, "currency": "TON", "transactions": []}
        mock_repositories['balance_repository'].get_user_balance_with_transactions = AsyncMock(
            return_value=test_balance_data
        )
        
        result = await balance_service.get_user_balance_with_transactions(123)
        
        assert result == test_balance_data
        mock_repositories['balance_repository'].get_user_balance_with_transactions.assert_called_once_with(123, 50)

    @pytest.mark.asyncio
    async def test_get_user_balance_with_transactions_error_handling(self, balance_service, mock_repositories):
        """Тест обработки ошибок при получении баланса с транзакциями"""
        mock_repositories['balance_repository'].get_user_balance_with_transactions = AsyncMock(
            side_effect=Exception("Database error")
        )
        balance_service.logger.error = Mock()
        
        result = await balance_service.get_user_balance_with_transactions(123)
        
        assert result == {"balance": 0, "currency": "TON", "transactions": []}
        balance_service.logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_transaction_and_refund_success(self, balance_service, mock_repositories):
        """Тест успешной отмены транзакции и возврата средств"""
        mock_repositories['balance_repository'].cancel_transaction_and_refund = AsyncMock(return_value=True)
        
        result = await balance_service.cancel_transaction_and_refund(1)
        
        assert result is True
        mock_repositories['balance_repository'].cancel_transaction_and_refund.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_cancel_transaction_and_refund_error_handling(self, balance_service, mock_repositories):
        """Тест обработки ошибок при отмене транзакции и возврате средств"""
        mock_repositories['balance_repository'].cancel_transaction_and_refund = AsyncMock(
            side_effect=Exception("Database error")
        )
        balance_service.logger.error = Mock()
        
        result = await balance_service.cancel_transaction_and_refund(1)
        
        assert result is False
        balance_service.logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_purchase_history_with_balance_success(self, balance_service, mock_repositories):
        """Тест успешного получения истории покупок с балансом"""
        test_balance_data = {"balance": 100.0, "currency": "TON", "source": "database"}
        test_transactions = [{"id": 1, "amount": 50.0, "transaction_type": "purchase"}]
        test_stats = {"total_purchases": 5, "total_amount": 250.0}
        
        mock_repositories['balance_repository'].get_user_transactions = AsyncMock(return_value=test_transactions)
        mock_repositories['balance_repository'].get_transaction_statistics = AsyncMock(return_value=test_stats)
        
        # Мокируем get_user_balance, который вызывается внутри метода
        with patch.object(balance_service, 'get_user_balance', AsyncMock(return_value=test_balance_data)):
            result = await balance_service.get_purchase_history_with_balance(123, 5)
            
            assert result["current_balance"] == 100.0
            assert result["currency"] == "TON"
            assert len(result["purchase_history"]) == 1
            assert result["purchase_statistics"]["total_purchases"] == 5
            assert result["total_purchases"] == 1
            mock_repositories['balance_repository'].get_user_transactions.assert_called_once_with(
                user_id=123, limit=5, transaction_type=TransactionType.PURCHASE
            )
            mock_repositories['balance_repository'].get_transaction_statistics.assert_called_once_with(123)

    @pytest.mark.asyncio
    async def test_get_purchase_history_with_balance_error_handling(self, balance_service, mock_repositories):
        """Тест обработки ошибок при получении истории покупок с балансом"""
        mock_repositories['balance_repository'].get_user_transactions = AsyncMock(
            side_effect=Exception("Database error")
        )
        balance_service.logger.error = Mock()
        
        result = await balance_service.get_purchase_history_with_balance(123)
        
        assert result["current_balance"] == 0
        assert result["currency"] == "TON"
        assert result["purchase_history"] == []
        assert result["purchase_statistics"] == {}
        assert result["total_purchases"] == 0
        balance_service.logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_purchase_history_with_balance_empty_transactions(self, balance_service, mock_repositories):
        """Тест получения истории покупок с пустыми транзакциями"""
        test_balance_data = {"balance": 100.0, "currency": "TON", "source": "database"}
        test_stats = {"total_purchases": 0, "total_amount": 0}
        
        mock_repositories['balance_repository'].get_user_transactions = AsyncMock(return_value=[])
        mock_repositories['balance_repository'].get_transaction_statistics = AsyncMock(return_value=test_stats)
        
        with patch.object(balance_service, 'get_user_balance', AsyncMock(return_value=test_balance_data)):
            result = await balance_service.get_purchase_history_with_balance(123, 5)
            
            assert result["current_balance"] == 100.0
            assert result["purchase_history"] == []
            assert result["purchase_statistics"]["total_purchases"] == 0
            assert result["total_purchases"] == 0


class TestBalanceServiceEdgeCases:
    """Тесты для edge cases и дополнительных сценариев"""

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

    @pytest.mark.asyncio
    async def test_get_user_balance_edge_cases(self, balance_service, mock_repositories):
        """Тест edge cases для получения баланса пользователя"""
        # Тест с нулевым балансом
        mock_repositories['balance_repository'].get_user_balance = AsyncMock(
            return_value={"balance": 0.0, "currency": "TON", "source": "database"}
        )
        mock_repositories['user_cache'].get_user_balance = AsyncMock(return_value=None)
        
        result = await balance_service.get_user_balance(123)
        assert result["balance"] == 0.0
        
        # Тест с большим балансом
        mock_repositories['balance_repository'].get_user_balance = AsyncMock(
            return_value={"balance": 999999.99, "currency": "TON", "source": "database"}
        )
        mock_repositories['user_cache'].get_user_balance = AsyncMock(return_value=None)
        
        result = await balance_service.get_user_balance(123)
        assert result["balance"] == 999999.99

    @pytest.mark.asyncio
    async def test_update_user_balance_edge_cases(self, balance_service, mock_repositories):
        """Тест edge cases для обновления баланса"""
        # Настраиваем моки для всех вызовов внутри update_user_balance
        test_balance_data = {"balance": 150.0, "currency": "TON", "source": "database"}
        
        # Тест с минимальной суммой
        mock_repositories['balance_repository'].update_user_balance = AsyncMock(return_value=True)
        mock_repositories['balance_repository'].get_user_balance = AsyncMock(return_value=test_balance_data)
        result = await balance_service.update_user_balance(123, 0.01, "add")
        assert result is True
        
        # Тест с большой суммой
        mock_repositories['balance_repository'].update_user_balance = AsyncMock(return_value=True)
        mock_repositories['balance_repository'].get_user_balance = AsyncMock(return_value=test_balance_data)
        result = await balance_service.update_user_balance(123, 1000000.0, "add")
        assert result is True
        
        # Тест с отрицательной суммой (должно быть обработано корректно)
        mock_repositories['balance_repository'].update_user_balance = AsyncMock(return_value=True)
        mock_repositories['balance_repository'].get_user_balance = AsyncMock(return_value=test_balance_data)
        result = await balance_service.update_user_balance(123, -50.0, "refund")
        assert result is True

    @pytest.mark.asyncio
    async def test_create_transaction_edge_cases(self, balance_service, mock_repositories):
        """Тест edge cases для создания транзакции"""
        # Тест с минимальной суммой
        mock_repositories['balance_repository'].create_transaction = AsyncMock(return_value=1)
        result = await balance_service.create_transaction(
            user_id=123,
            transaction_type="purchase",
            amount=0.01,
            description="test"
        )
        assert result == 1
        
        # Тест с большой суммой
        mock_repositories['balance_repository'].create_transaction = AsyncMock(return_value=1)
        result = await balance_service.create_transaction(
            user_id=123,
            transaction_type="purchase",
            amount=999999.99,
            description="test"
        )
        assert result == 1

    @pytest.mark.asyncio
    async def test_get_user_transactions_edge_cases(self, balance_service, mock_repositories):
        """Тест edge cases для получения транзакций"""
        # Тест с лимитом 0
        mock_repositories['balance_repository'].get_user_transactions = AsyncMock(return_value=[])
        result = await balance_service.get_user_transactions(123, 0)
        assert result == []
        
        # Тест с большим лимитом
        mock_repositories['balance_repository'].get_user_transactions = AsyncMock(return_value=[{"id": 1}])
        result = await balance_service.get_user_transactions(123, 1000)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_transaction_statistics_edge_cases(self, balance_service, mock_repositories):
        """Тест edge cases для получения статистики транзакций"""
        # Тест с пользователем без транзакций
        mock_repositories['balance_repository'].get_transaction_statistics = AsyncMock(
            return_value={"total_purchases": 0, "total_amount": 0}
        )
        result = await balance_service.get_transaction_statistics(123)
        assert result["total_purchases"] == 0
        assert result["total_amount"] == 0

    @pytest.mark.asyncio
    async def test_error_handling_comprehensive(self, balance_service, mock_repositories):
        """Комплексный тест обработки ошибок для всех методов"""
        # Тест ошибок для всех основных методов
        methods_to_test = [
            ('get_user_balance', Exception("DB error")),
            ('update_user_balance', Exception("Update failed")),
            ('create_transaction', Exception("Create failed")),
            ('get_user_transactions', Exception("Query failed")),
            ('get_transaction_statistics', Exception("Stats failed")),
            ('fail_transaction', Exception("Fail failed")),
            ('cancel_transaction_and_refund', Exception("Cancel failed")),
        ]
        
        balance_service.logger.error = Mock()
        
        for method_name, error in methods_to_test:
            mock_method = getattr(mock_repositories['balance_repository'], method_name)
            mock_method.side_effect = error
            
            try:
                if method_name == 'get_user_balance':
                    # Для get_user_balance нужно настроить дополнительные моки, так как метод имеет сложную логику
                    # Временно отключаем кеш для упрощения тестирования
                    original_cache = balance_service.user_cache
                    balance_service.user_cache = None
                    
                    result = await balance_service.get_user_balance(123)
                    assert result["balance"] == 0
                    
                    # Восстанавливаем кеш
                    balance_service.user_cache = original_cache
                elif method_name == 'update_user_balance':
                    result = await balance_service.update_user_balance(123, 100, "test")
                    assert result is False
                elif method_name == 'create_transaction':
                    result = await balance_service.create_transaction(
                        user_id=123,
                        transaction_type="purchase",
                        amount=100,
                        description="test"
                    )
                    assert result is None
                elif method_name == 'get_user_transactions':
                    result = await balance_service.get_user_transactions(123)
                    assert result == []
                elif method_name == 'get_transaction_statistics':
                    result = await balance_service.get_transaction_statistics(123)
                    assert result == {}
                elif method_name == 'fail_transaction':
                    result = await balance_service.fail_transaction(1, {})
                    assert result is False
                elif method_name == 'cancel_transaction_and_refund':
                    result = await balance_service.cancel_transaction_and_refund(1)
                    assert result is False
                    
            except Exception:
                pytest.fail(f"Method {method_name} should handle exceptions gracefully")
            
            balance_service.logger.error.assert_called()
            balance_service.logger.error.reset_mock()

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, balance_service, mock_repositories):
        """Тест конкурентных операций (имитация)"""
        # Временно отключаем кеш для упрощения тестирования
        original_cache = balance_service.user_cache
        balance_service.user_cache = None
        
        try:
            # Настраиваем моки для последовательных вызовов
            mock_repositories['balance_repository'].get_user_balance = AsyncMock(
                side_effect=[
                    {"balance": 100.0, "currency": "TON", "source": "database"},
                    {"balance": 150.0, "currency": "TON", "source": "database"},
                    {"balance": 50.0, "currency": "TON", "source": "database"}
                ]
            )
            
            # Имитация последовательных вызовов (не совсем конкурентных, но проверяющих side_effect)
            results = []
            for _ in range(3):
                result = await balance_service.get_user_balance(123)
                results.append(result["balance"])
            
            assert results == [100.0, 150.0, 50.0]
            assert mock_repositories['balance_repository'].get_user_balance.call_count == 3
        finally:
            # Восстанавливаем кеш
            balance_service.user_cache = original_cache
    @pytest.mark.asyncio
    async def test_concurrent_operations_edge_case(self, balance_service, mock_repositories):
        """Тест конкурентных операций с edge case - быстрая смена баланса"""
        # Временно отключаем кеш для упрощения тестирования
        original_cache = balance_service.user_cache
        balance_service.user_cache = None
        
        try:
            # Настраиваем моки для последовательных вызовов
            mock_repositories['balance_repository'].get_user_balance = AsyncMock(
                side_effect=[
                    {"balance": 100.0, "currency": "TON", "source": "database"},
                    {"balance": 50.0, "currency": "TON", "source": "database"},
                    {"balance": 75.0, "currency": "TON", "source": "database"}
                ]
            )
            
            # Имитация последовательных вызовов (не совсем конкурентных, но проверяющих side_effect)
            results = []
            for _ in range(3):
                result = await balance_service.get_user_balance(123)
                results.append(result["balance"])
            
            assert results == [100.0, 50.0, 75.0]  # Проверяем последовательность
            assert len(set(results)) == 3  # Должны быть разные значения
            assert mock_repositories['balance_repository'].get_user_balance.call_count == 3
        finally:
            # Восстанавливаем кеш
            balance_service.user_cache = original_cache

    @pytest.mark.asyncio
    async def test_edge_case_zero_amount_transactions(self, balance_service, mock_repositories):
        """Тест edge case с нулевыми суммами транзакций"""
        # Тест с нулевой суммой для валидации
        result = await balance_service.validate_transaction_amount(0.0)
        assert result is False
        
        # Тест с очень маленькой, но положительной суммой
        result = await balance_service.validate_transaction_amount(0.001)
        assert result is True
        
        # Тест с отрицательной суммой
        result = await balance_service.validate_transaction_amount(-0.1)
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])