"""
Дополнительные интеграционные тесты для покупки звезд через Fragment API
"""
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, Mock
from datetime import datetime

from services.payment.star_purchase_service import StarPurchaseService
from repositories.user_repository import TransactionType, TransactionStatus
from services.fragment.fragment_service import FragmentService


class TestFragmentPurchaseIntegration:
    """Дополнительные интеграционные тесты для Fragment API"""

    @pytest.fixture
    def mock_repositories_and_services(self):
        """Фикстура для создания mock объектов"""
        # Mock UserRepository
        user_repository = Mock()
        user_repository.get_user_by_id = AsyncMock(return_value={
            "user_id": 123456789,
            "telegram_username": "@testuser"
        })
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
        
        # Mock FragmentService - используем AsyncMock для асинхронных методов
        fragment_service = AsyncMock()
        fragment_service.buy_stars_without_kyc = AsyncMock(return_value={
            "status": "success",
            "result": {
                "status": "completed",
                "stars_count": 100,
                "transaction_id": "fragment_tx_123"
            }
        })
        fragment_service.refresh_cookies_if_needed = AsyncMock(return_value=True)
        
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
        # Создаем mock для FragmentService отдельно - используем AsyncMock для асинхронных методов
        fragment_service = AsyncMock()
        fragment_service.buy_stars_without_kyc = AsyncMock(return_value={
            "status": "success",
            "result": {
                "status": "completed",
                "stars_count": 100,
                "transaction_id": "fragment_tx_123"
            }
        })
        fragment_service.refresh_cookies_if_needed = AsyncMock(return_value=True)
        
        # Создаем сервис с правильными параметрами
        service = StarPurchaseService(**mock_repositories_and_services)
        # Переопределяем fragment_service на mock
        service.fragment_service = fragment_service
        return service

    @pytest.mark.asyncio
    async def test_fragment_purchase_user_not_found(self, star_purchase_service):
        """Тест покупки звезд для несуществующего пользователя"""
        # Настраиваем mock для возврата None (пользователь не найден)
        star_purchase_service.user_repository.get_user = AsyncMock(return_value=None)
        
        result = await star_purchase_service._create_star_purchase_with_fragment(
            user_id=999999999,  # Несуществующий пользователь
            amount=100
        )
        
        assert result["status"] == "failed"
        assert "User not found" in result["error"]

    @pytest.mark.asyncio
    async def test_fragment_purchase_no_telegram_username(self, star_purchase_service):
        """Тест покупки звезд для пользователя без Telegram username"""
        # Настраиваем mock для пользователя без username
        star_purchase_service.user_repository.get_user = AsyncMock(return_value={
            "user_id": 123456789,
            "telegram_username": None  # Нет username
        })
        
        result = await star_purchase_service._create_star_purchase_with_fragment(
            user_id=123456789,
            amount=100
        )
        
        assert result["status"] == "failed"
        assert "Telegram username not found" in result["error"]

    @pytest.mark.asyncio
    async def test_fragment_purchase_cookie_refresh_success(self, star_purchase_service):
        """Тест покупки звезд с успешным обновлением cookies"""
        # Первый вызов возвращает ошибку авторизации
        first_call_result = {
            "status": "failed",
            "error": "Invalid cookies"
        }
        
        # Второй вызов после обновления cookies успешен
        second_call_result = {
            "status": "success",
            "result": {
                "status": "completed",
                "stars_count": 100,
                "transaction_id": "fragment_tx_123"
            }
        }
        
        # Настраиваем side_effect для последовательных вызовов
        star_purchase_service.fragment_service.buy_stars_without_kyc = AsyncMock(
            side_effect=[first_call_result, second_call_result]
        )
        
        # Настраиваем успешное обновление cookies
        star_purchase_service.fragment_service.refresh_cookies_if_needed = AsyncMock(return_value=True)
        
        result = await star_purchase_service._create_star_purchase_with_fragment(
            user_id=123456789,
            amount=100
        )
        
        assert result["status"] == "success"
        assert result["stars_count"] == 100
        # Проверяем, что метод вызвался дважды
        assert star_purchase_service.fragment_service.buy_stars_without_kyc.call_count == 2

    @pytest.mark.asyncio
    async def test_fragment_purchase_cookie_refresh_failed(self, star_purchase_service):
        """Тест покупки звезд с неудачным обновлением cookies"""
        # Настраиваем ошибку авторизации
        fragment_result = {
            "status": "failed",
            "error": "Invalid cookies"
        }
        
        star_purchase_service.fragment_service.buy_stars_without_kyc = AsyncMock(return_value=fragment_result)
        
        # Настраиваем неудачное обновление cookies
        star_purchase_service.fragment_service.refresh_cookies_if_needed = AsyncMock(return_value=False)
        
        result = await star_purchase_service._create_star_purchase_with_fragment(
            user_id=123456789,
            amount=100
        )
        
        assert result["status"] == "failed"
        assert "Invalid cookies" in result["error"]
        # Проверяем, что метод вызвался только один раз (без повтора)
        star_purchase_service.fragment_service.buy_stars_without_kyc.assert_called_once()

    @pytest.mark.asyncio
    async def test_fragment_purchase_cache_operations(self, star_purchase_service):
        """Тест операций кеширования при покупке звезд"""
        # Настраиваем успешную покупку
        fragment_result = {
            "status": "success",
            "result": {
                "status": "completed",
                "stars_count": 100,
                "transaction_id": "fragment_tx_123"
            }
        }
        
        star_purchase_service.fragment_service.buy_stars_without_kyc = AsyncMock(return_value=fragment_result)
        
        result = await star_purchase_service._create_star_purchase_with_fragment(
            user_id=123456789,
            amount=100
        )
        
        assert result["status"] == "success"
        
        # Проверяем операции кеширования
        star_purchase_service.payment_cache.cache_payment_details.assert_called()
        # Должно быть два вызова: при создании и при завершении
        assert star_purchase_service.payment_cache.cache_payment_details.call_count == 2

    @pytest.mark.asyncio
    async def test_fragment_purchase_transaction_creation_failure(self, star_purchase_service):
        """Тест неудачного создания транзакции"""
        # Настраиваем ошибку создания транзакции
        star_purchase_service.balance_repository.create_transaction = AsyncMock(return_value=None)
        
        result = await star_purchase_service._create_star_purchase_with_fragment(
            user_id=123456789,
            amount=100
        )
        
        assert result["status"] == "failed"
        assert "Failed to create transaction" in result["error"]
        # Проверяем, что Fragment API не вызывался
        star_purchase_service.fragment_service.buy_stars_without_kyc.assert_not_called()

    @pytest.mark.asyncio
    async def test_fragment_purchase_exception_handling(self, star_purchase_service):
        """Тест обработки исключений при покупке звезд"""
        # Настраиваем исключение при вызове Fragment API
        star_purchase_service.fragment_service.buy_stars_without_kyc = AsyncMock(
            side_effect=Exception("Network timeout")
        )
        
        result = await star_purchase_service._create_star_purchase_with_fragment(
            user_id=123456789,
            amount=100
        )
        
        assert result["status"] == "failed"
        assert "Network timeout" in result["error"]
        # Проверяем, что транзакция создалась, но не обновлялась
        star_purchase_service.balance_repository.create_transaction.assert_called_once()
        star_purchase_service.balance_repository.update_transaction_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_fragment_service_ping_success(self):
        """Тест успешного ping FragmentService"""
        fragment_service = FragmentService()
        
        with patch.object(fragment_service.client, 'ping', return_value={"status": "ok"}):
            result = await fragment_service.ping()
            
            assert result["status"] == "success"
            assert result["result"] == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_fragment_service_ping_failure(self):
        """Тест неудачного ping FragmentService"""
        fragment_service = FragmentService()
        
        with patch.object(fragment_service.client, 'ping', side_effect=Exception("Connection failed")):
            result = await fragment_service.ping()
            
            assert result["status"] == "failed"
            assert "Connection failed" in result["error"]

    @pytest.mark.asyncio
    async def test_fragment_service_get_balance_no_seed(self):
        """Тест получения баланса без seed phrase"""
        fragment_service = FragmentService()
        fragment_service.seed_phrase = ""  # Пустая seed phrase
        
        result = await fragment_service.get_balance()
        
        assert result["status"] == "failed"
        assert "Seed phrase is not configured" in result["error"]

    @pytest.mark.asyncio
    async def test_fragment_service_api_call_with_retry(self):
        """Тест API вызова с повторной попыткой после ошибки авторизации"""
        fragment_service = FragmentService()
        fragment_service.fragment_cookies = "test_cookies"
        
        # Используем список для отслеживания вызовов
        call_count = [0]
        
        def mock_api_method(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Invalid cookies")
            return {"data": "success"}
        
        with patch.object(fragment_service, 'refresh_cookies_if_needed', AsyncMock(return_value=True)):
            # Используем _make_api_call напрямую
            result = await fragment_service._make_api_call(mock_api_method)
            
            assert result["status"] == "success"
            assert result["result"] == {"data": "success"}
            assert call_count[0] == 2  # Должно быть два вызова


if __name__ == "__main__":
    pytest.main([__file__])