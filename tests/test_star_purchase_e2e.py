"""
Комплексные E2E тесты для процесса покупки звезд через Fragment API
Тестирует полный цикл от проверки баланса до завершения транзакции
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from datetime import datetime, timezone
from typing import Dict, Any
import json

from services.payment.star_purchase_service import StarPurchaseService
from services.fragment.fragment_service import FragmentService
from repositories.user_repository import UserRepository
from repositories.balance_repository import BalanceRepository
from services.payment.payment_service import PaymentService
from services.cache.payment_cache import PaymentCache
from services.cache.user_cache import UserCache
from repositories.user_repository import TransactionType, TransactionStatus


class TestStarPurchaseE2E:
    """E2E тесты для процесса покупки звезд через Fragment API"""
    
    @pytest.fixture
    async def star_purchase_service(self):
        """Фикстура для создания сервиса покупки звезд с моками"""
        # Создаем моки всех зависимостей
        user_repo_mock = AsyncMock(spec=UserRepository)
        balance_repo_mock = AsyncMock(spec=BalanceRepository)
        payment_service_mock = AsyncMock(spec=PaymentService)
        payment_cache_mock = AsyncMock(spec=PaymentCache)
        user_cache_mock = AsyncMock(spec=UserCache)
        
        # Создаем реальный экземпляр FragmentService для тестирования
        fragment_service = FragmentService()
        
        service = StarPurchaseService(
            user_repository=user_repo_mock,
            balance_repository=balance_repo_mock,
            payment_service=payment_service_mock,
            payment_cache=payment_cache_mock,
            user_cache=user_cache_mock
        )
        
        # Заменяем fragment_service на мок для изоляции тестов
        service.fragment_service = AsyncMock(spec=FragmentService)
        
        return service, user_repo_mock, balance_repo_mock, payment_service_mock, payment_cache_mock, user_cache_mock
    
    @pytest.mark.asyncio
    async def test_e2e_successful_fragment_purchase(self, star_purchase_service):
        """E2E тест успешной покупки звезд через Fragment API"""
        service, user_repo_mock, balance_repo_mock, payment_service_mock, payment_cache_mock, user_cache_mock = star_purchase_service
        
        # Тестовые данные
        user_id = 12345
        amount = 100
        telegram_username = "testuser"
        transaction_id = 67890
        
        # Мокируем данные пользователя
        user_repo_mock.get_user.return_value = {
            "id": user_id,
            "telegram_username": telegram_username,
            "first_name": "Test",
            "last_name": "User"
        }
        
        # Мокируем успешное создание транзакции
        balance_repo_mock.create_transaction.return_value = transaction_id
        
        # Мокируем успешную покупку через Fragment API
        fragment_result = {
            "status": "success",
            "stars": amount,
            "transaction_id": "frag_tx_123",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        service.fragment_service.buy_stars_without_kyc.return_value = {
            "status": "success",
            "result": fragment_result
        }
        
        # Мокируем успешное обновление статуса транзакции
        balance_repo_mock.update_transaction_status.return_value = True
        
        # Выполняем покупку
        result = await service.create_star_purchase(user_id, amount, purchase_type="fragment")
        
        # Проверяем результат
        assert result["status"] == "success"
        assert result["purchase_type"] == "fragment"
        assert result["stars_count"] == amount
        assert result["transaction_id"] == transaction_id
        assert "result" in result
        
        # Проверяем вызовы методов
        user_repo_mock.get_user.assert_called_once_with(user_id)
        balance_repo_mock.create_transaction.assert_called_once()
        service.fragment_service.buy_stars_without_kyc.assert_called_once_with(
            username=telegram_username,
            amount=amount
        )
        balance_repo_mock.update_transaction_status.assert_called_once()
        
        # Проверяем кеширование
        payment_cache_mock.cache_payment_details.assert_called()
    
    @pytest.mark.asyncio
    async def test_e2e_fragment_purchase_insufficient_balance_fallback(self, star_purchase_service):
        """E2E тест покупки с недостаточным балансом и fallback на Fragment"""
        service, user_repo_mock, balance_repo_mock, payment_service_mock, payment_cache_mock, user_cache_mock = star_purchase_service
        
        # Тестовые данные
        user_id = 12345
        amount = 100
        current_balance = 50  # Недостаточно для покупки
        
        # Мокируем проверку баланса через кеш
        user_cache_mock.get_user_balance.return_value = current_balance
        
        # Выполняем покупку с баланса (должно вернуть ошибку недостаточного баланса)
        result = await service.create_star_purchase(user_id, amount, purchase_type="balance")
        
        # Проверяем ошибку недостаточного баланса
        assert result["status"] == "failed"
        assert "Insufficient balance" in result["error"]
        assert result["current_balance"] == current_balance
        assert result["required_amount"] == amount
        
        # Теперь пробуем через Fragment API
        telegram_username = "testuser"
        transaction_id = 67890
        
        # Мокируем данные пользователя
        user_repo_mock.get_user.return_value = {
            "id": user_id,
            "telegram_username": telegram_username
        }
        
        # Мокируем создание транзакции
        balance_repo_mock.create_transaction.return_value = transaction_id
        
        # Мокируем успешную покупку через Fragment
        service.fragment_service.buy_stars_without_kyc.return_value = {
            "status": "success",
            "result": {"stars": amount}
        }
        
        # Выполняем покупку через Fragment
        fragment_result = await service.create_star_purchase(user_id, amount, purchase_type="fragment")
        
        # Проверяем успешную покупку через Fragment
        assert fragment_result["status"] == "success"
        assert fragment_result["purchase_type"] == "fragment"
        
        # Проверяем, что Fragment API был вызван
        service.fragment_service.buy_stars_without_kyc.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_e2e_fragment_purchase_cookie_error_with_retry(self, star_purchase_service):
        """E2E тест обработки ошибки cookies в Fragment API с повторной попыткой"""
        service, user_repo_mock, balance_repo_mock, payment_service_mock, payment_cache_mock, user_cache_mock = star_purchase_service
        
        user_id = 12345
        amount = 100
        telegram_username = "testuser"
        transaction_id = 67890
        
        # Мокируем данные пользователя
        user_repo_mock.get_user.return_value = {
            "id": user_id,
            "telegram_username": telegram_username
        }
        
        # Мокируем создание транзакции
        balance_repo_mock.create_transaction.return_value = transaction_id
        
        # Первый вызов возвращает ошибку cookies
        cookie_error_response = {
            "status": "failed",
            "error": "Invalid cookie authentication"
        }
        
        # Второй вызов после обновления cookies успешен
        success_response = {
            "status": "success", 
            "result": {"stars": amount}
        }
        
        # Настраиваем side_effect для последовательных вызовов
        service.fragment_service.buy_stars_without_kyc.side_effect = [
            cookie_error_response,
            success_response
        ]
        
        # Мокируем успешное обновление cookies
        service.fragment_service.refresh_cookies_if_needed.return_value = True
        
        # Выполняем покупку
        result = await service.create_star_purchase(user_id, amount, purchase_type="fragment")
        
        # Проверяем успешный результат после retry
        assert result["status"] == "success"
        assert result["purchase_type"] == "fragment"
        
        # Проверяем, что было 2 вызова API (первый неудачный, второй успешный)
        assert service.fragment_service.buy_stars_without_kyc.call_count == 2
        
        # Проверяем, что обновление cookies было вызвано
        service.fragment_service.refresh_cookies_if_needed.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_e2e_fragment_purchase_network_failure(self, star_purchase_service):
        """E2E тест обработки сетевого сбоя при обращении к Fragment API"""
        service, user_repo_mock, balance_repo_mock, payment_service_mock, payment_cache_mock, user_cache_mock = star_purchase_service
        
        user_id = 12345
        amount = 100
        telegram_username = "testuser"
        transaction_id = 67890
        
        # Мокируем данные пользователя
        user_repo_mock.get_user.return_value = {
            "id": user_id,
            "telegram_username": telegram_username
        }
        
        # Мокируем создание транзакции
        balance_repo_mock.create_transaction.return_value = transaction_id
        
        # Мокируем сетевую ошибку
        service.fragment_service.buy_stars_without_kyc.return_value = {
            "status": "failed",
            "error": "Network error: Connection timed out"
        }
        
        # Мокируем неудачное обновление cookies (сетевая ошибка сохраняется)
        service.fragment_service.refresh_cookies_if_needed.return_value = False
        
        # Выполняем покупку
        result = await service.create_star_purchase(user_id, amount, purchase_type="fragment")
        
        # Проверяем ошибку
        assert result["status"] == "failed"
        assert "Network error" in result["error"]
        
        # Проверяем, что транзакция была отменена
        balance_repo_mock.update_transaction_status.assert_called_with(
            transaction_id,
            TransactionStatus.FAILED,
            metadata={
                "error": "Network error: Connection timed out",
                "failed_at": ANY
            }
        )
    
    @pytest.mark.asyncio
    async def test_e2e_fragment_purchase_user_not_found(self, star_purchase_service):
        """E2E тест обработки случая когда пользователь не найден"""
        service, user_repo_mock, balance_repo_mock, payment_service_mock, payment_cache_mock, user_cache_mock = star_purchase_service
        
        user_id = 99999  # Несуществующий пользователь
        amount = 100
        
        # Мокируем отсутствие пользователя
        user_repo_mock.get_user.return_value = None
        
        # Выполняем покупку
        result = await service.create_star_purchase(user_id, amount, purchase_type="fragment")
        
        # Проверяем ошибку
        assert result["status"] == "failed"
        assert "User not found" in result["error"]
        
        # Проверяем, что Fragment API не вызывался
        service.fragment_service.buy_stars_without_kyc.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_e2e_fragment_purchase_missing_telegram_username(self, star_purchase_service):
        """E2E тест обработки случая когда отсутствует Telegram username"""
        service, user_repo_mock, balance_repo_mock, payment_service_mock, payment_cache_mock, user_cache_mock = star_purchase_service
        
        user_id = 12345
        amount = 100
        
        # Мокируем пользователя без telegram_username
        user_repo_mock.get_user.return_value = {
            "id": user_id,
            "first_name": "Test",
            "last_name": "User"
            # Нет telegram_username
        }
        
        # Выполняем покупку
        result = await service.create_star_purchase(user_id, amount, purchase_type="fragment")
        
        # Проверяем ошибку
        assert result["status"] == "failed"
        assert "Telegram username not found" in result["error"]
        
        # Проверяем, что Fragment API не вызывался
        service.fragment_service.buy_stars_without_kyc.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_e2e_fragment_purchase_transaction_creation_failure(self, star_purchase_service):
        """E2E тест обработки ошибки создания транзакции"""
        service, user_repo_mock, balance_repo_mock, payment_service_mock, payment_cache_mock, user_cache_mock = star_purchase_service
        
        user_id = 12345
        amount = 100
        telegram_username = "testuser"
        
        # Мокируем данные пользователя
        user_repo_mock.get_user.return_value = {
            "id": user_id,
            "telegram_username": telegram_username
        }
        
        # Мокируем ошибку создания транзакции
        balance_repo_mock.create_transaction.return_value = None
        
        # Выполняем покупку
        result = await service.create_star_purchase(user_id, amount, purchase_type="fragment")
        
        # Проверяем ошибку
        assert result["status"] == "failed"
        assert "Failed to create transaction" in result["error"]
        
        # Проверяем, что Fragment API не вызывался
        service.fragment_service.buy_stars_without_kyc.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_e2e_balance_purchase_success(self, star_purchase_service):
        """E2E тест успешной покупки с баланса пользователя"""
        service, user_repo_mock, balance_repo_mock, payment_service_mock, payment_cache_mock, user_cache_mock = star_purchase_service
        
        user_id = 12345
        amount = 100
        current_balance = 200.0
        transaction_id = 67890
        
        # Мокируем достаточный баланс в кеше
        user_cache_mock.get_user_balance.return_value = current_balance
        
        # Мокируем быструю обработку покупки
        with patch.object(service, '_process_balance_purchase_fast') as mock_fast_process:
            mock_fast_process.return_value = {
                "status": "success",
                "purchase_type": "balance",
                "transaction_id": transaction_id,
                "stars_count": amount,
                "old_balance": current_balance,
                "new_balance": current_balance - amount,
                "message": f"✅ Успешно куплено {amount} звезд с баланса"
            }
            
            # Выполняем покупку
            result = await service.create_star_purchase(user_id, amount, purchase_type="balance")
            
            # Проверяем успешный результат
            assert result["status"] == "success"
            assert result["purchase_type"] == "balance"
            assert result["stars_count"] == amount
            assert result["old_balance"] == current_balance
            assert result["new_balance"] == current_balance - amount
            
            # Проверяем вызов быстрой обработки
            mock_fast_process.assert_called_once_with(user_id, amount, current_balance)


class TestFragmentPurchaseIntegration:
    """Интеграционные тесты с реальным FragmentService (без моков API)"""
    
    @pytest.mark.asyncio
    async def test_integration_fragment_service_initialization(self):
        """Тест инициализации FragmentService и проверка cookies"""
        fragment_service = FragmentService()
        
        # Проверяем, что сервис инициализирован
        assert fragment_service is not None
        assert hasattr(fragment_service, 'cookie_manager')
        assert hasattr(fragment_service, 'client')
        
        # Проверяем базовые методы
        assert hasattr(fragment_service, 'buy_stars_without_kyc')
        assert hasattr(fragment_service, 'refresh_cookies_if_needed')
        
        # Проверяем, что cookies могут быть загружены (или созданы при необходимости)
        cookies_loaded = await fragment_service.refresh_cookies_if_needed()
        assert isinstance(cookies_loaded, bool)
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Требует реального доступа к Fragment API для E2E тестирования")
    async def test_real_fragment_api_connection(self):
        """REAL E2E тест подключения к Fragment API (требует настройки)"""
        fragment_service = FragmentService()
        
        # Попытка ping API для проверки подключения
        try:
            ping_result = await fragment_service.ping()
            assert ping_result["status"] == "success"
            assert "version" in ping_result
        except Exception as e:
            pytest.skip(f"Fragment API недоступен: {e}")


# Дополнительные утилитарные тесты
@pytest.mark.asyncio
async def test_purchase_amount_validation():
    """Тест валидации количества звезд для покупки"""
    service = StarPurchaseService(
        user_repository=AsyncMock(),
        balance_repository=AsyncMock(),
        payment_service=AsyncMock()
    )
    
    # Valid amounts
    assert await service._validate_purchase_amount(1) is True
    assert await service._validate_purchase_amount(100) is True
    assert await service._validate_purchase_amount(1000) is True
    assert await service._validate_purchase_amount(10000) is True
    
    # Invalid amounts
    assert await service._validate_purchase_amount(0) is False
    assert await service._validate_purchase_amount(-1) is False
    assert await service._validate_purchase_amount(100001) is False  # Превышение лимита


@pytest.mark.asyncio
async def test_concurrent_purchase_requests():
    """Тест обработки concurrent запросов на покупку"""
    # Создаем мок FragmentService и патчим конструктор StarPurchaseService
    fragment_service_mock = AsyncMock(spec=FragmentService)
    
    with patch('services.payment.star_purchase_service.FragmentService', return_value=fragment_service_mock):
        # Используем тот же подход, что и в других тестах - создаем моки для всех зависимостей
        user_repo_mock = AsyncMock(spec=UserRepository)
        balance_repo_mock = AsyncMock(spec=BalanceRepository)
        payment_service_mock = AsyncMock(spec=PaymentService)
        payment_cache_mock = AsyncMock(spec=PaymentCache)
        user_cache_mock = AsyncMock(spec=UserCache)
        
        # Мокируем достаточный баланс в кеше
        user_cache_mock.get_user_balance.return_value = 200.0  # Достаточно для покупки 100 звезд
        
        service = StarPurchaseService(
            user_repository=user_repo_mock,
            balance_repository=balance_repo_mock,
            payment_service=payment_service_mock,
            payment_cache=payment_cache_mock,
            user_cache=user_cache_mock
        )
    
    user_id = 12345
    amount = 100
    
    # Мокируем быструю обработку
    service._process_balance_purchase_fast = AsyncMock()
    service._process_balance_purchase_fast.return_value = {
        "status": "success",
        "stars_count": amount
    }
    
    # Создаем несколько concurrent запросов
    tasks = [
        service.create_star_purchase(user_id, amount, "balance")
        for _ in range(5)
    ]
    
    results = await asyncio.gather(*tasks)
    
    # Проверяем, что все запросы обработаны
    assert len(results) == 5
    for result in results:
        assert result["status"] == "success"
        assert result["stars_count"] == amount
    
    # Проверяем, что быстрая обработка вызывалась для каждого запроса
    assert service._process_balance_purchase_fast.call_count == 5