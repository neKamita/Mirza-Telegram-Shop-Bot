"""
Comprehensive tests for Star Purchase Service
"""
import pytest
import time
import hashlib
import hmac
from unittest.mock import AsyncMock, Mock, patch, ANY
from datetime import datetime, timezone

from services.payment.star_purchase_service import StarPurchaseService
from repositories.user_repository import UserRepository, TransactionType, TransactionStatus
from repositories.balance_repository import BalanceRepository
from services.payment.payment_service import PaymentService
from services.cache.payment_cache import PaymentCache
from services.cache.user_cache import UserCache
from services.fragment.fragment_service import FragmentService


class TestStarPurchaseServiceComprehensive:
    """Comprehensive tests for StarPurchaseService"""

    @pytest.fixture
    def mock_dependencies(self):
        """Mock all dependencies"""
        user_repo = AsyncMock(spec=UserRepository)
        balance_repo = AsyncMock(spec=BalanceRepository)
        payment_service = AsyncMock(spec=PaymentService)
        payment_cache = AsyncMock(spec=PaymentCache)
        user_cache = AsyncMock(spec=UserCache)
        
        return user_repo, balance_repo, payment_service, payment_cache, user_cache

    @pytest.fixture
    def star_purchase_service(self, mock_dependencies):
        """StarPurchaseService instance with mocked dependencies"""
        user_repo, balance_repo, payment_service, payment_cache, user_cache = mock_dependencies
        
        service = StarPurchaseService(
            user_repository=user_repo,
            balance_repository=balance_repo,
            payment_service=payment_service,
            payment_cache=payment_cache,
            user_cache=user_cache
        )
        
        # Mock fragment service
        service.fragment_service = AsyncMock(spec=FragmentService)
        
        return service

    def test_init(self, mock_dependencies):
        """Тест инициализации StarPurchaseService"""
        user_repo, balance_repo, payment_service, payment_cache, user_cache = mock_dependencies
        
        service = StarPurchaseService(
            user_repository=user_repo,
            balance_repository=balance_repo,
            payment_service=payment_service,
            payment_cache=payment_cache,
            user_cache=user_cache
        )
        
        assert service.user_repository == user_repo
        assert service.balance_repository == balance_repo
        assert service.payment_service == payment_service
        assert service.payment_cache == payment_cache
        assert service.user_cache == user_cache
        assert isinstance(service.fragment_service, FragmentService)

    @pytest.mark.asyncio
    async def test_create_star_purchase_invalid_amount(self, star_purchase_service):
        """Тест создания покупки с некорректной суммой"""
        result = await star_purchase_service.create_star_purchase(123, 0, "balance")
        
        assert result["status"] == "failed"
        assert "Invalid purchase amount" in result["error"]

    @pytest.mark.asyncio
    async def test_create_star_purchase_balance_type(self, star_purchase_service, mock_dependencies):
        """Тест создания покупки с баланса"""
        _, _, _, _, user_cache = mock_dependencies
        user_cache.get_user_balance.return_value = 200.0
        
        with patch.object(star_purchase_service, '_process_balance_purchase_fast') as mock_fast:
            mock_fast.return_value = {"status": "success", "stars_count": 100}
            
            result = await star_purchase_service.create_star_purchase(123, 100, "balance")
            
            assert result["status"] == "success"
            mock_fast.assert_called_once_with(123, 100, 200.0)

    @pytest.mark.asyncio
    async def test_create_star_purchase_fragment_type(self, star_purchase_service):
        """Тест создания покупки через Fragment"""
        with patch.object(star_purchase_service, '_create_star_purchase_with_fragment') as mock_fragment:
            mock_fragment.return_value = {"status": "success", "purchase_type": "fragment"}
            
            result = await star_purchase_service.create_star_purchase(123, 100, "fragment")
            
            assert result["status"] == "success"
            mock_fragment.assert_called_once_with(123, 100)

    @pytest.mark.asyncio
    async def test_create_star_purchase_payment_type(self, star_purchase_service):
        """Тест создания покупки через платежную систему"""
        with patch.object(star_purchase_service, '_create_star_purchase_with_payment') as mock_payment:
            mock_payment.return_value = {"status": "success", "purchase_type": "payment"}
            
            result = await star_purchase_service.create_star_purchase(123, 100, "payment")
            
            assert result["status"] == "success"
            mock_payment.assert_called_once_with(123, 100)

    @pytest.mark.asyncio
    async def test_create_star_purchase_exception(self, star_purchase_service):
        """Тест обработки исключения в create_star_purchase"""
        with patch.object(star_purchase_service, '_validate_purchase_amount', side_effect=Exception("Test error")):
            result = await star_purchase_service.create_star_purchase(123, 100, "balance")
            
            assert result["status"] == "failed"
            assert "Test error" in result["error"]

    @pytest.mark.asyncio
    async def test_create_star_purchase_with_balance_insufficient_funds(self, star_purchase_service, mock_dependencies):
        """Тест покупки с недостаточным балансом"""
        _, _, _, _, user_cache = mock_dependencies
        user_cache.get_user_balance.return_value = 50.0  # Меньше чем нужно
        
        result = await star_purchase_service._create_star_purchase_with_balance(123, 100)
        
        assert result["status"] == "failed"
        assert "Insufficient balance" in result["error"]
        assert result["current_balance"] == 50.0
        assert result["required_amount"] == 100

    @pytest.mark.asyncio
    async def test_create_star_purchase_with_balance_no_cache(self, star_purchase_service, mock_dependencies):
        """Тест покупки без кеша баланса"""
        _, balance_repo, _, _, user_cache = mock_dependencies
        user_cache.get_user_balance.return_value = None
        
        # Мокаем создание нового баланса
        balance_repo.get_user_balance.side_effect = [None, {"balance": 0.0}]
        balance_repo.create_user_balance.return_value = True
        
        result = await star_purchase_service._create_star_purchase_with_balance(123, 100)
        
        assert result["status"] == "failed"
        assert "Insufficient balance" in result["error"]

    @pytest.mark.asyncio
    async def test_create_star_purchase_with_balance_transaction_creation_failed(self, star_purchase_service, mock_dependencies):
        """Тест ошибки создания транзакции"""
        _, balance_repo, _, _, user_cache = mock_dependencies
        user_cache.get_user_balance.return_value = None  # Нет кеша, идем через основной путь
        balance_repo.get_user_balance.return_value = {"balance": 200.0}
        balance_repo.create_transaction.return_value = None
        
        result = await star_purchase_service._create_star_purchase_with_balance(123, 100)
        
        assert result["status"] == "failed"
        assert "Failed to create transaction" in result["error"]

    @pytest.mark.asyncio
    async def test_create_star_purchase_with_balance_balance_update_failed(self, star_purchase_service, mock_dependencies):
        """Тест ошибки обновления баланса"""
        _, balance_repo, _, _, user_cache = mock_dependencies
        user_cache.get_user_balance.return_value = None  # Нет кеша, идем через основной путь
        balance_repo.get_user_balance.return_value = {"balance": 200.0}
        balance_repo.create_transaction.return_value = 123
        balance_repo.update_user_balance.return_value = False
        
        result = await star_purchase_service._create_star_purchase_with_balance(123, 100)
        
        assert result["status"] == "failed"
        assert "Failed to update balance" in result["error"]
        
        # Проверяем, что транзакция была отменена
        balance_repo.update_transaction_status.assert_called_with(
            123, TransactionStatus.FAILED, metadata=ANY
        )

    @pytest.mark.asyncio
    async def test_create_star_purchase_with_fragment_user_not_found(self, star_purchase_service, mock_dependencies):
        """Тест покупки через Fragment - пользователь не найден"""
        user_repo, _, _, _, _ = mock_dependencies
        user_repo.get_user.return_value = None
        
        result = await star_purchase_service._create_star_purchase_with_fragment(123, 100)
        
        assert result["status"] == "failed"
        assert "User not found" in result["error"]

    @pytest.mark.asyncio
    async def test_create_star_purchase_with_fragment_no_username(self, star_purchase_service, mock_dependencies):
        """Тест покупки через Fragment - нет username"""
        user_repo, _, _, _, _ = mock_dependencies
        user_repo.get_user.return_value = {"id": 123, "first_name": "Test"}
        
        result = await star_purchase_service._create_star_purchase_with_fragment(123, 100)
        
        assert result["status"] == "failed"
        assert "Telegram username not found" in result["error"]

    @pytest.mark.asyncio
    async def test_create_star_purchase_with_fragment_success(self, star_purchase_service, mock_dependencies):
        """Тест успешной покупки через Fragment"""
        user_repo, balance_repo, _, payment_cache, _ = mock_dependencies
        user_repo.get_user.return_value = {"id": 123, "telegram_username": "testuser"}
        balance_repo.create_transaction.return_value = 456
        
        star_purchase_service.fragment_service.buy_stars_without_kyc.return_value = {
            "status": "success",
            "result": {"stars": 100}
        }
        
        result = await star_purchase_service._create_star_purchase_with_fragment(123, 100)
        
        assert result["status"] == "success"
        assert result["purchase_type"] == "fragment"
        assert result["transaction_id"] == 456

    @pytest.mark.asyncio
    async def test_create_star_purchase_with_fragment_cookie_retry(self, star_purchase_service, mock_dependencies):
        """Тест повтора покупки через Fragment после обновления cookies"""
        user_repo, balance_repo, _, _, _ = mock_dependencies
        user_repo.get_user.return_value = {"id": 123, "telegram_username": "testuser"}
        balance_repo.create_transaction.return_value = 456
        
        # Первый вызов неудачен, второй успешен
        star_purchase_service.fragment_service.buy_stars_without_kyc.side_effect = [
            {"status": "failed", "error": "Invalid cookie authentication"},
            {"status": "success", "result": {"stars": 100}}
        ]
        star_purchase_service.fragment_service.refresh_cookies_if_needed.return_value = True
        
        result = await star_purchase_service._create_star_purchase_with_fragment(123, 100)
        
        assert result["status"] == "success"
        assert star_purchase_service.fragment_service.buy_stars_without_kyc.call_count == 2

    @pytest.mark.asyncio
    async def test_create_star_purchase_with_payment_success(self, star_purchase_service, mock_dependencies):
        """Тест успешной покупки через платежную систему"""
        _, balance_repo, payment_service, payment_cache, _ = mock_dependencies
        balance_repo.create_transaction.return_value = 789
        payment_service.create_invoice_for_user.return_value = {
            "result": {"uuid": "test-uuid", "url": "https://pay.test"}
        }
        
        result = await star_purchase_service._create_star_purchase_with_payment(123, 100)
        
        assert result["status"] == "success"
        assert result["purchase_type"] == "payment"
        assert result["transaction_id"] == 789

    @pytest.mark.asyncio
    async def test_create_star_purchase_with_payment_invoice_error(self, star_purchase_service, mock_dependencies):
        """Тест ошибки создания счета"""
        _, balance_repo, payment_service, _, _ = mock_dependencies
        balance_repo.create_transaction.return_value = 789
        payment_service.create_invoice_for_user.return_value = {"error": "Payment error"}
        
        result = await star_purchase_service._create_star_purchase_with_payment(123, 100)
        
        assert result["status"] == "failed"
        assert "Payment error" in result["error"]

    @pytest.mark.asyncio
    async def test_check_purchase_status_cached(self, star_purchase_service, mock_dependencies):
        """Тест проверки статуса покупки из кеша"""
        _, _, _, payment_cache, _ = mock_dependencies
        cached_data = {"status": "paid", "amount": 100}
        payment_cache.get_payment_details.return_value = cached_data
        
        result = await star_purchase_service.check_purchase_status("test-uuid")
        
        assert result == cached_data

    @pytest.mark.asyncio
    async def test_check_purchase_status_from_service(self, star_purchase_service, mock_dependencies):
        """Тест проверки статуса покупки через платежный сервис"""
        _, balance_repo, payment_service, payment_cache, _ = mock_dependencies
        payment_cache.get_payment_details.return_value = None
        payment_service.check_payment.return_value = {"status": "paid", "amount": 100}
        balance_repo.get_transaction_by_external_id.return_value = {
            "id": 123, "user_id": 456
        }
        
        result = await star_purchase_service.check_purchase_status("test-uuid")
        
        assert result["status"] == "paid"
        balance_repo.update_transaction_status.assert_called()

    @pytest.mark.asyncio
    async def test_process_payment_webhook_invalid_signature(self, star_purchase_service):
        """Тест обработки вебхука с неверной подписью"""
        with patch.object(star_purchase_service, '_validate_webhook_signature', return_value=False):
            result = await star_purchase_service.process_payment_webhook({"uuid": "test"})
            
            assert result is False

    @pytest.mark.asyncio
    async def test_process_payment_webhook_success(self, star_purchase_service, mock_dependencies):
        """Тест успешной обработки вебхука"""
        _, balance_repo, _, _, user_cache = mock_dependencies
        
        webhook_data = {"uuid": "test-uuid", "status": "paid", "amount": 100}
        balance_repo.get_transaction_by_external_id.return_value = {
            "id": 123, "user_id": 456, "metadata": {"purchase_type": "payment"}
        }
        
        with patch.object(star_purchase_service, '_validate_webhook_signature', return_value=True):
            result = await star_purchase_service.process_payment_webhook(webhook_data)
            
            assert result is True
            balance_repo.update_user_balance.assert_called_with(456, 100.0, "add")
            balance_repo.update_transaction_status.assert_called()
            user_cache.invalidate_user_cache.assert_called_with(456)

    @pytest.mark.asyncio
    async def test_get_purchase_history(self, star_purchase_service, mock_dependencies):
        """Тест получения истории покупок"""
        _, balance_repo, _, _, _ = mock_dependencies
        
        transactions = [
            {
                "id": 1,
                "amount": 100,
                "currency": "TON",
                "status": "completed",
                "created_at": datetime.now(timezone.utc),
                "metadata": {"stars_count": 100, "payment_uuid": "uuid1"}
            }
        ]
        balance_repo.get_user_transactions.return_value = transactions
        
        history = await star_purchase_service.get_purchase_history(123, 10)
        
        assert len(history) == 1
        assert history[0]["stars_count"] == 100

    @pytest.mark.asyncio
    async def test_validate_purchase_amount_valid(self, star_purchase_service):
        """Тест валидации корректных сумм"""
        assert await star_purchase_service._validate_purchase_amount(1) is True
        assert await star_purchase_service._validate_purchase_amount(100) is True
        assert await star_purchase_service._validate_purchase_amount(10000) is True

    @pytest.mark.asyncio
    async def test_validate_purchase_amount_invalid(self, star_purchase_service):
        """Тест валидации некорректных сумм"""  
        assert await star_purchase_service._validate_purchase_amount(0) is False
        assert await star_purchase_service._validate_purchase_amount(-1) is False
        assert await star_purchase_service._validate_purchase_amount(100001) is False

    @pytest.mark.asyncio
    async def test_validate_webhook_signature_no_secret(self, star_purchase_service):
        """Тест валидации подписи без секрета"""
        with patch('config.settings.settings') as mock_settings:
            mock_settings.webhook_secret = None
            
            result = await star_purchase_service._validate_webhook_signature({"uuid": "test"})
            assert result is True

    @pytest.mark.asyncio
    async def test_validate_webhook_signature_missing_fields(self, star_purchase_service):
        """Тест валидации подписи с пропущенными полями"""
        with patch('config.settings.settings') as mock_settings:
            mock_settings.webhook_secret = "secret"
            
            result = await star_purchase_service._validate_webhook_signature({"uuid": "test"})
            assert result is False

    @pytest.mark.asyncio
    async def test_validate_webhook_signature_valid(self, star_purchase_service):
        """Тест валидации корректной подписи"""
        webhook_data = {"uuid": "test", "status": "paid", "amount": 100}
        
        with patch('config.settings.settings') as mock_settings:
            mock_settings.webhook_secret = "secret"
            
            # Создаем корректную подпись
            import json
            payload = json.dumps(webhook_data, sort_keys=True, separators=(',', ':'))
            signature = hmac.new(
                "secret".encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            star_purchase_service._webhook_signature = signature
            
            result = await star_purchase_service._validate_webhook_signature(webhook_data)
            assert result is True

    @pytest.mark.asyncio
    async def test_get_purchase_statistics(self, star_purchase_service, mock_dependencies):
        """Тест получения статистики покупок"""
        _, balance_repo, _, _, _ = mock_dependencies
        
        transactions = [
            {"status": "completed", "amount": 100, "metadata": {"stars_count": 100}},
            {"status": "completed", "amount": 50, "metadata": {"stars_count": 50}},
            {"status": "failed", "amount": 25, "metadata": {"stars_count": 25}}
        ]
        balance_repo.get_user_transactions.return_value = transactions
        
        stats = await star_purchase_service.get_purchase_statistics(123)
        
        assert stats["total_purchases"] == 3
        assert stats["successful_purchases"] == 2
        assert stats["failed_purchases"] == 1
        assert abs(stats["success_rate"] - 66.66666666666667) < 0.001
        assert stats["total_stars"] == 150
        assert stats["total_amount"] == 150

    @pytest.mark.asyncio
    async def test_cancel_pending_purchase(self, star_purchase_service, mock_dependencies):
        """Тест отмены ожидающей покупки"""
        _, balance_repo, _, _, user_cache = mock_dependencies
        
        balance_repo.get_transaction_by_external_id.return_value = {
            "id": 123, "status": "pending"
        }
        balance_repo.update_transaction_status.return_value = True
        
        result = await star_purchase_service.cancel_pending_purchase(456, 123)
        
        assert result is True
        balance_repo.update_transaction_status.assert_called_with(
            123, TransactionStatus.CANCELLED, metadata=ANY
        )

    @pytest.mark.asyncio
    async def test_create_recharge_success(self, star_purchase_service, mock_dependencies):
        """Тест успешного создания пополнения"""
        _, balance_repo, payment_service, _, _ = mock_dependencies
        
        balance_repo.create_transaction.return_value = 789
        payment_service.create_recharge_invoice_for_user.return_value = {
            "result": {"uuid": "recharge-uuid", "url": "https://recharge.test"}
        }
        
        result = await star_purchase_service.create_recharge(123, 100.0)
        
        assert result["status"] == "success"
        assert result["transaction_id"] == 789
        assert result["recharge_amount"] == 100.0

    @pytest.mark.asyncio
    async def test_create_recharge_invalid_amount(self, star_purchase_service):
        """Тест создания пополнения с некорректной суммой"""
        result = await star_purchase_service.create_recharge(123, 5.0)  # Меньше минимума
        
        assert result["status"] == "failed"
        assert "Invalid recharge amount" in result["error"]

    @pytest.mark.asyncio 
    async def test_process_recharge_webhook_success(self, star_purchase_service, mock_dependencies):
        """Тест успешной обработки вебхука пополнения"""
        _, balance_repo, _, _, user_cache = mock_dependencies
        
        webhook_data = {"uuid": "recharge-uuid", "status": "paid", "amount": 100}
        balance_repo.get_transaction_by_external_id.return_value = {
            "id": 123,
            "user_id": 456,
            "status": "pending",
            "metadata": {"recharge_amount": 100}
        }
        
        with patch.object(star_purchase_service, '_validate_webhook_signature', return_value=True):
            result = await star_purchase_service.process_recharge_webhook(webhook_data)
            
            assert result is True
            balance_repo.update_user_balance.assert_called_with(456, 100.0, "add")

    @pytest.mark.asyncio
    async def test_validate_recharge_amount_valid(self, star_purchase_service):
        """Тест валидации корректных сумм пополнения"""
        assert await star_purchase_service._validate_recharge_amount(10.0) is True
        assert await star_purchase_service._validate_recharge_amount(100.0) is True
        assert await star_purchase_service._validate_recharge_amount(1000.0) is True

    @pytest.mark.asyncio
    async def test_validate_recharge_amount_invalid(self, star_purchase_service):
        """Тест валидации некорректных сумм пополнения"""
        assert await star_purchase_service._validate_recharge_amount(None) is False
        assert await star_purchase_service._validate_recharge_amount(5.0) is False  # Меньше минимума
        assert await star_purchase_service._validate_recharge_amount(15000.0) is False  # Больше максимума

    @pytest.mark.asyncio
    async def test_cancel_pending_recharges(self, star_purchase_service, mock_dependencies):
        """Тест отмены всех ожидающих пополнений"""
        _, balance_repo, _, _, user_cache = mock_dependencies
        
        pending_recharges = [
            {"id": 123}, {"id": 124}
        ]
        balance_repo.get_user_transactions.return_value = pending_recharges
        balance_repo.update_transaction_status.return_value = True
        
        cancelled_count = await star_purchase_service.cancel_pending_recharges(456)
        
        assert cancelled_count == 2
        assert balance_repo.update_transaction_status.call_count == 2

    @pytest.mark.asyncio
    async def test_cancel_specific_recharge(self, star_purchase_service, mock_dependencies):
        """Тест отмены конкретного пополнения"""
        _, balance_repo, _, _, _ = mock_dependencies
        
        pending_recharges = [
            {
                "id": 123,
                "user_id": 456,
                "status": "pending",
                "metadata": {"payment_uuid": "target-uuid"}
            }
        ]
        balance_repo.get_user_transactions.return_value = pending_recharges
        balance_repo.update_transaction_status.return_value = True
        
        result = await star_purchase_service.cancel_specific_recharge(456, "target-uuid")
        
        assert result is True
        balance_repo.update_transaction_status.assert_called_with(
            123, TransactionStatus.CANCELLED, metadata=ANY
        )

    @pytest.mark.asyncio 
    async def test_process_balance_purchase_fast_success(self, star_purchase_service, mock_dependencies):
        """Тест быстрой обработки покупки с баланса"""
        _, balance_repo, _, _, user_cache = mock_dependencies
        
        balance_repo.create_transaction.return_value = 123
        balance_repo.update_user_balance.return_value = True
        balance_repo.update_transaction_status.return_value = True
        user_cache.invalidate_user_cache.return_value = None
        
        result = await star_purchase_service._process_balance_purchase_fast(456, 100, 200.0)
        
        assert result["status"] == "success"
        assert result["transaction_id"] == 123
        assert result["old_balance"] == 200.0
        assert result["new_balance"] == 100.0

    @pytest.mark.asyncio
    async def test_process_balance_purchase_fast_exception(self, star_purchase_service, mock_dependencies):
        """Тест обработки исключения в быстрой покупке"""
        _, balance_repo, _, _, _ = mock_dependencies
        
        balance_repo.create_transaction.side_effect = Exception("Database error")
        
        result = await star_purchase_service._process_balance_purchase_fast(456, 100, 200.0)
        
        assert result["status"] == "failed"
        assert "Failed to process transaction" in result["error"]
