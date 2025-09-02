"""
Комплексные unit-тесты для PaymentService с полным покрытием всех методов и сценариев
"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from typing import Dict, Any
import aiohttp

from services.payment.payment_service import PaymentService
from services.cache.payment_cache import PaymentCache


class TestPaymentServiceComprehensive:
    """Комплексные тесты для PaymentService с полным покрытием"""

    @pytest.fixture
    def mock_payment_cache(self):
        """Фикстура с mock кешем платежей"""
        cache = Mock(spec=PaymentCache)
        cache.get_payment_details = AsyncMock(return_value=None)
        cache.cache_payment_details = AsyncMock()
        cache.redis_client = Mock()
        cache.redis_client.keys = AsyncMock(return_value=[])
        cache.redis_client.delete = AsyncMock(return_value=1)
        return cache

    @pytest.fixture
    def payment_service(self, mock_payment_cache):
        """Фикстура с инициализированным PaymentService"""
        return PaymentService(
            merchant_uuid="test_merchant",
            api_key="test_api_key",
            payment_cache=mock_payment_cache
        )

    @pytest.fixture
    def mock_aiohttp_response(self):
        """Фикстура с mock HTTP ответом"""
        response = Mock(spec=aiohttp.ClientResponse)
        response.status = 200
        response.text = AsyncMock(return_value='{"result": {"invoice_url": "test_url", "uuid": "test_uuid"}}')
        response.json = AsyncMock(return_value={"result": {"invoice_url": "test_url", "uuid": "test_uuid"}})
        return response

    @pytest.mark.asyncio
    async def test_generate_headers(self, payment_service):
        """Тест генерации заголовков"""
        test_data = '{"amount": "1", "currency": "TON", "order_id": "test_order"}'
        
        headers = payment_service._generate_headers(test_data)
        
        assert "merchant" in headers
        assert "sign" in headers
        assert "Content-Type" in headers
        assert headers["Content-Type"] == "application/json"
        assert headers["merchant"] == "test_merchant"

    @pytest.mark.asyncio
    async def test_create_invoice_success(self, payment_service, mock_payment_cache, mock_aiohttp_response):
        """Тест создания счета - успешный сценарий"""
        amount = "1"
        currency = "TON"
        order_id = "test_order_123"
        
        # Создаем mock для асинхронного контекстного менеджера
        mock_context_manager = Mock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_aiohttp_response)
        mock_context_manager.__aexit__ = AsyncMock(return_value=None)
        
        # Mock-объект для session.post
        mock_post = Mock(return_value=mock_context_manager)
        
        # Mock-объект для session
        mock_session = Mock()
        mock_session.post = mock_post
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await payment_service.create_invoice(amount, currency, order_id)
            
            # Проверяем, что запрос был отправлен
            mock_post.assert_called_once()
            
            # Проверяем, что результат содержит ожидаемые поля
            assert "result" in result
            assert result["result"]["invoice_url"] == "test_url"
            assert result["result"]["uuid"] == "test_uuid"
            
            # Проверяем, что кеширование было вызвано
            mock_payment_cache.cache_payment_details.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_invoice_with_cache_hit(self, payment_service, mock_payment_cache):
        """Тест создания счета с попаданием в кеш"""
        amount = "1"
        currency = "TON"
        order_id = "test_order_123"
        
        # Настраиваем кеш для возврата данных
        cached_data = {"result": {"invoice_url": "cached_url", "uuid": "cached_uuid"}}
        mock_payment_cache.get_payment_details = AsyncMock(return_value=cached_data)
        
        result = await payment_service.create_invoice(amount, currency, order_id)
        
        # Проверяем, что вернулись данные из кеша
        assert result == cached_data
        
        # Проверяем, что HTTP запрос не отправлялся
        assert not hasattr(payment_service, '_aiohttp_session') or payment_service._aiohttp_session is None

    @pytest.mark.asyncio
    async def test_create_invoice_network_error(self, payment_service, mock_payment_cache):
        """Тест создания счета - ошибка сети"""
        amount = "1"
        currency = "TON"
        order_id = "test_order_123"
        
        # Mock-объект для session
        mock_session = Mock()
        mock_session.post = Mock(side_effect=aiohttp.ClientError("Network error"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await payment_service.create_invoice(amount, currency, order_id)
            
            # Проверяем, что вернулась ошибка
            assert "error" in result
            assert result["status"] == "failed"
            assert "Network error" in result["error"]

    @pytest.mark.asyncio
    async def test_create_invoice_json_parse_error(self, payment_service, mock_payment_cache, mock_aiohttp_response):
        """Тест создания счета - ошибка парсинга JSON"""
        amount = "1"
        currency = "TON"
        order_id = "test_order_123"
        
        # Настраиваем ответ с невалидным JSON
        mock_aiohttp_response.text = AsyncMock(return_value="invalid json")
        mock_aiohttp_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "invalid json", 0)
        
        # Создаем mock для асинхронного контекстного менеджера
        mock_context_manager = Mock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_aiohttp_response)
        mock_context_manager.__aexit__ = AsyncMock(return_value=None)
        
        # Mock-объект для session.post
        mock_post = Mock(return_value=mock_context_manager)
        
        # Mock-объект для session
        mock_session = Mock()
        mock_session.post = mock_post
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await payment_service.create_invoice(amount, currency, order_id)
            
            # Проверяем, что вернулась ошибка парсинга
            assert "error" in result
            assert result["status"] == "failed"
            assert "Invalid JSON response" in result["error"]

    @pytest.mark.asyncio
    async def test_create_invoice_timeout_error(self, payment_service, mock_payment_cache):
        """Тест создания счета - таймаут"""
        amount = "1"
        currency = "TON"
        order_id = "test_order_123"
        
        # Mock-объект для session
        mock_session = Mock()
        mock_session.post = Mock(side_effect=asyncio.TimeoutError("Timeout error"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await payment_service.create_invoice(amount, currency, order_id)
            
            # Проверяем, что вернулась ошибка
            assert "error" in result
            assert result["status"] == "failed"

    @pytest.mark.asyncio
    async def test_check_payment_success(self, payment_service, mock_payment_cache, mock_aiohttp_response):
        """Тест проверки статуса платежа - успешный сценарий"""
        invoice_uuid = "test_uuid_123"
        
        # Создаем mock для асинхронного контекстного менеджера
        mock_context_manager = Mock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_aiohttp_response)
        mock_context_manager.__aexit__ = AsyncMock(return_value=None)
        
        # Mock-объект для session.post
        mock_post = Mock(return_value=mock_context_manager)
        
        # Mock-объект для session
        mock_session = Mock()
        mock_session.post = mock_post
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await payment_service.check_payment(invoice_uuid)
            
            # Проверяем, что запрос был отправлен
            mock_post.assert_called_once()
            
            # Проверяем, что результат содержит ожидаемые поля
            assert "result" in result
            assert result["result"]["invoice_url"] == "test_url"
            
            # Проверяем, что кеширование было вызвано
            mock_payment_cache.cache_payment_details.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_payment_with_cache_hit(self, payment_service, mock_payment_cache):
        """Тест проверки статуса платежа с попаданием в кеш"""
        invoice_uuid = "test_uuid_123"
        
        # Настраиваем кеш для возврата данных
        cached_data = {"result": {"status": "paid", "amount": "1"}}
        mock_payment_cache.get_payment_details = AsyncMock(return_value=cached_data)
        
        result = await payment_service.check_payment(invoice_uuid)
        
        # Проверяем, что вернулись данные из кеша
        assert result == cached_data
        
        # Проверяем, что HTTP запрос не отправлялся
        assert not hasattr(payment_service, '_aiohttp_session') or payment_service._aiohttp_session is None

    @pytest.mark.asyncio
    async def test_check_payment_error(self, payment_service, mock_payment_cache):
        """Тест проверки статуса платежа - ошибка"""
        invoice_uuid = "test_uuid_123"
        
        # Mock-объект для session
        mock_session = Mock()
        mock_session.post = Mock(side_effect=Exception("Unexpected error"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await payment_service.check_payment(invoice_uuid)
            
            # Проверяем, что вернулась ошибка
            assert "error" in result
            assert result["status"] == "failed"

    @pytest.mark.asyncio
    async def test_create_invoice_for_user_success(self, payment_service, mock_payment_cache, mock_aiohttp_response):
        """Тест создания счета для пользователя - успешный сценарий"""
        user_id = 123
        amount = "1"
        
        with patch.object(payment_service, 'create_invoice', AsyncMock(return_value={"result": {"uuid": "test_uuid"}})):
            result = await payment_service.create_invoice_for_user(user_id, amount)
            
            # Проверяем, что create_invoice был вызван
            payment_service.create_invoice.assert_called_once()
            
            # Проверяем, что кеширование информации о заказе было вызвано
            mock_payment_cache.cache_payment_details.assert_called_once()
            
            # Проверяем структуру результата
            assert "result" in result

    @pytest.mark.asyncio
    async def test_create_invoice_for_user_without_cache(self, payment_service):
        """Тест создания счета для пользователя без кеша"""
        payment_service.payment_cache = None
        user_id = 123
        amount = "1"
        
        with patch.object(payment_service, 'create_invoice', AsyncMock(return_value={"result": {"uuid": "test_uuid"}})):
            result = await payment_service.create_invoice_for_user(user_id, amount)
            
            # Проверяем, что create_invoice был вызван
            payment_service.create_invoice.assert_called_once()
            
            # Проверяем структуру результата
            assert "result" in result

    @pytest.mark.asyncio
    async def test_create_recharge_invoice_success(self, payment_service, mock_payment_cache, mock_aiohttp_response):
        """Тест создания счета на пополнение - успешный сценарий"""
        user_id = 123
        amount = "10"
        
        with patch.object(payment_service, 'create_invoice', AsyncMock(return_value={"result": {"uuid": "test_uuid"}})):
            result = await payment_service.create_recharge_invoice(user_id, amount)
            
            # Проверяем, что create_invoice был вызван
            payment_service.create_invoice.assert_called_once()
            
            # Проверяем, что кеширование информации о пополнении было вызвано
            mock_payment_cache.cache_payment_details.assert_called_once()
            
            # Проверяем структуру результата
            assert "result" in result

    @pytest.mark.asyncio
    async def test_create_recharge_invoice_for_user_success(self, payment_service, mock_payment_cache):
        """Тест создания счета на пополнение для пользователя - успешный сценарий"""
        user_id = 123
        amount = "10"
        
        with patch.object(payment_service, 'create_recharge_invoice', AsyncMock(return_value={"result": {"uuid": "test_uuid"}})):
            result = await payment_service.create_recharge_invoice_for_user(user_id, amount)
            
            # Проверяем, что create_recharge_invoice был вызван
            payment_service.create_recharge_invoice.assert_called_once()
            
            # Проверяем структуру результата
            assert "result" in result

    @pytest.mark.asyncio
    async def test_get_recharge_history_success(self, payment_service, mock_payment_cache):
        """Тест получения истории пополнений - успешный сценарий"""
        user_id = 123
        limit = 5
        
        # Настраиваем mock Redis для возврата ключей
        mock_keys = [b'recharge:123:order1', b'recharge:123:order2']
        mock_payment_cache.redis_client.keys = AsyncMock(return_value=mock_keys)
        
        # Настраиваем mock для возврата данных пополнений
        recharge_data = [
            {"user_id": 123, "amount": "10", "currency": "TON", "type": "recharge"},
            {"user_id": 123, "amount": "20", "currency": "TON", "type": "recharge"}
        ]
        mock_payment_cache.get_payment_details = AsyncMock(side_effect=recharge_data)
        
        result = await payment_service.get_recharge_history(user_id, limit)
        
        # Проверяем структуру результата
        assert result["status"] == "success"
        assert "recharges" in result
        assert result["total"] == 2
        assert len(result["recharges"]) == 2

    @pytest.mark.asyncio
    async def test_get_recharge_history_no_cache(self, payment_service):
        """Тест получения истории пополнений без кеша"""
        payment_service.payment_cache = None
        user_id = 123
        limit = 5
        
        result = await payment_service.get_recharge_history(user_id, limit)
        
        # Проверяем, что вернулась ошибка
        assert result["status"] == "failed"
        assert "Payment cache not available" in result["error"]

    @pytest.mark.asyncio
    async def test_get_recharge_history_error(self, payment_service, mock_payment_cache):
        """Тест получения истории пополнений - ошибка"""
        user_id = 123
        limit = 5
        
        # Настраиваем mock Redis для вызова исключения
        mock_payment_cache.redis_client.keys = AsyncMock(side_effect=Exception("Redis error"))
        
        result = await payment_service.get_recharge_history(user_id, limit)
        
        # Проверяем, что вернулась ошибка
        assert result["status"] == "failed"
        assert "Redis error" in result["error"]

    @pytest.mark.asyncio
    async def test_get_payment_history_success(self, payment_service, mock_payment_cache):
        """Тест получения истории платежей - успешный сценарий"""
        user_id = 123
        limit = 5
        
        # Настраиваем mock Redis для возврата ключей
        mock_keys = [b'user_order:123:order1', b'user_order:123:order2']
        mock_payment_cache.redis_client.keys = AsyncMock(return_value=mock_keys)
        
        # Настраиваем mock для возврата данных платежей
        payment_data = [
            {"user_id": 123, "amount": "1", "currency": "TON"},
            {"user_id": 123, "amount": "2", "currency": "TON"}
        ]
        mock_payment_cache.get_payment_details = AsyncMock(side_effect=payment_data)
        
        result = await payment_service.get_payment_history(user_id, limit)
        
        # Проверяем структуру результата
        assert result["status"] == "success"
        assert "payments" in result
        assert result["total"] == 2
        assert len(result["payments"]) == 2

    @pytest.mark.asyncio
    async def test_get_payment_history_no_cache(self, payment_service):
        """Тест получения истории платежей без кеша"""
        payment_service.payment_cache = None
        user_id = 123
        limit = 5
        
        result = await payment_service.get_payment_history(user_id, limit)
        
        # Проверяем, что вернулась ошибка
        assert result["status"] == "failed"
        assert "Payment cache not available" in result["error"]

    @pytest.mark.asyncio
    async def test_invalidate_payment_cache_success(self, payment_service, mock_payment_cache):
        """Тест инвалидации кеша платежа - успешный сценарий"""
        invoice_uuid = "test_uuid_123"
        
        result = await payment_service.invalidate_payment_cache(invoice_uuid)
        
        # Проверяем, что кеш был очищен
        assert result is True
        mock_payment_cache.redis_client.delete.assert_called_once_with(f"payment_status:{invoice_uuid}")

    @pytest.mark.asyncio
    async def test_invalidate_payment_cache_no_cache(self, payment_service):
        """Тест инвалидации кеша платежа без кеша"""
        payment_service.payment_cache = None
        invoice_uuid = "test_uuid_123"
        
        result = await payment_service.invalidate_payment_cache(invoice_uuid)
        
        # Проверяем, что вернулось False
        assert result is False

    @pytest.mark.asyncio
    async def test_invalidate_payment_cache_error(self, payment_service, mock_payment_cache):
        """Тест инвалидации кеша платежа - ошибка"""
        invoice_uuid = "test_uuid_123"
        
        # Настраиваем mock Redis для вызова исключения
        mock_payment_cache.redis_client.delete = AsyncMock(side_effect=Exception("Delete error"))
        
        result = await payment_service.invalidate_payment_cache(invoice_uuid)
        
        # Проверяем, что вернулось False
        assert result is False

    @pytest.mark.asyncio
    async def test_get_payment_statistics_success(self, payment_service, mock_payment_cache):
        """Тест получения статистики платежей - успешный сценарий"""
        user_id = 123
        
        # Настраиваем mock Redis для возврата ключей
        mock_keys = [b'user_order:123:order1', b'user_order:123:order2']
        mock_payment_cache.redis_client.keys = AsyncMock(return_value=mock_keys)
        
        # Настраиваем mock для возврата данных платежей
        payment_data = [
            {"user_id": 123, "amount": "10", "currency": "TON"},
            {"user_id": 123, "amount": "20", "currency": "TON"}
        ]
        mock_payment_cache.get_payment_details = AsyncMock(side_effect=payment_data)
        
        result = await payment_service.get_payment_statistics(user_id)
        
        # Проверяем структуру результата
        assert result["status"] == "success"
        assert result["total_payments"] == 2
        assert result["total_amount"] == 30.0
        assert result["average_amount"] == 15.0

    @pytest.mark.asyncio
    async def test_get_payment_statistics_no_payments(self, payment_service, mock_payment_cache):
        """Тест получения статистики платежей - нет платежей"""
        user_id = 123
        
        # Настраиваем mock Redis для возврата пустого списка ключей
        mock_payment_cache.redis_client.keys = AsyncMock(return_value=[])
        
        result = await payment_service.get_payment_statistics(user_id)
        
        # Проверяем структуру результата
        assert result["status"] == "success"
        assert result["total_payments"] == 0
        assert result["total_amount"] == 0.0
        assert result["average_amount"] == 0.0

    @pytest.mark.asyncio
    async def test_get_payment_statistics_invalid_amounts(self, payment_service, mock_payment_cache):
        """Тест получения статистики платежей - невалидные суммы"""
        user_id = 123
        
        # Настраиваем mock Redis для возврата ключей
        mock_keys = [b'user_order:123:order1', b'user_order:123:order2']
        mock_payment_cache.redis_client.keys = AsyncMock(return_value=mock_keys)
        
        # Настраиваем mock для возврата данных с невалидными суммами
        payment_data = [
            {"user_id": 123, "amount": "invalid", "currency": "TON"},
            {"user_id": 123, "amount": None, "currency": "TON"}
        ]
        mock_payment_cache.get_payment_details = AsyncMock(side_effect=payment_data)
        
        result = await payment_service.get_payment_statistics(user_id)
        
        # Проверяем структуру результата
        assert result["status"] == "success"
        assert result["total_payments"] == 0  # Оба платежа проигнорированы из-за невалидных сумм
        assert result["total_amount"] == 0.0
        assert result["average_amount"] == 0.0

    @pytest.mark.asyncio
    async def test_get_payment_statistics_no_cache(self, payment_service):
        """Тест получения статистики платежей без кеша"""
        payment_service.payment_cache = None
        user_id = 123
        
        result = await payment_service.get_payment_statistics(user_id)
        
        # Проверяем, что вернулась ошибка
        assert result["status"] == "failed"
        assert "Payment cache not available" in result["error"]

    @pytest.mark.asyncio
    async def test_get_payment_statistics_error(self, payment_service, mock_payment_cache):
        """Тест получения статистики платежей - ошибка"""
        user_id = 123
        
        # Настраиваем mock Redis для вызова исключения
        mock_payment_cache.redis_client.keys = AsyncMock(side_effect=Exception("Redis error"))
        
        result = await payment_service.get_payment_statistics(user_id)
        
        # Проверяем, что вернулась ошибка
        assert result["status"] == "failed"
        assert "Redis error" in result["error"]

    # Тесты для edge cases и boundary conditions
    @pytest.mark.asyncio
    async def test_create_invoice_different_amounts(self, payment_service, mock_payment_cache, mock_aiohttp_response):
        """Тест создания счета с разными суммами"""
        test_amounts = ["0.1", "1", "10", "100", "1000"]
        currency = "TON"
        order_id = "test_order"
        
        for amount in test_amounts:
            mock_payment_cache.get_payment_details.reset_mock()
            mock_payment_cache.cache_payment_details.reset_mock()
            
            # Создаем mock для асинхронного контекстного менеджера
            mock_context_manager = Mock()
            mock_context_manager.__aenter__ = AsyncMock(return_value=mock_aiohttp_response)
            mock_context_manager.__aexit__ = AsyncMock(return_value=None)
            
            # Mock-объект для session.post
            mock_post = Mock(return_value=mock_context_manager)
            
            # Mock-объект для session
            mock_session = Mock()
            mock_session.post = mock_post
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            
            with patch('aiohttp.ClientSession', return_value=mock_session):
                result = await payment_service.create_invoice(amount, currency, order_id)
                
                # Проверяем, что запрос был отправлен
                mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_invoice_different_currencies(self, payment_service, mock_payment_cache, mock_aiohttp_response):
        """Тест создания счета с разными валютами"""
        amount = "1"
        test_currencies = ["TON", "USD", "EUR", "RUB"]
        order_id = "test_order"
        
        for currency in test_currencies:
            mock_payment_cache.get_payment_details.reset_mock()
            mock_payment_cache.cache_payment_details.reset_mock()
            
            # Создаем mock для асинхронного контекстного менеджера
            mock_context_manager = Mock()
            mock_context_manager.__aenter__ = AsyncMock(return_value=mock_aiohttp_response)
            mock_context_manager.__aexit__ = AsyncMock(return_value=None)
            
            # Mock-объект для session.post
            mock_post = Mock(return_value=mock_context_manager)
            
            # Mock-объект для session
            mock_session = Mock()
            mock_session.post = mock_post
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            
            with patch('aiohttp.ClientSession', return_value=mock_session):
                result = await payment_service.create_invoice(amount, currency, order_id)
                
                # Проверяем, что запрос был отправлен
                mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_payment_different_uuids(self, payment_service, mock_payment_cache, mock_aiohttp_response):
        """Тест проверки статуса платежа с разными UUID"""
        test_uuids = ["uuid1", "uuid2", "uuid3_with_underscores", "uuid4-with-dashes"]
        
        for uuid in test_uuids:
            mock_payment_cache.get_payment_details.reset_mock()
            mock_payment_cache.cache_payment_details.reset_mock()
            
            # Создаем mock для асинхронного контекстного менеджера
            mock_context_manager = Mock()
            mock_context_manager.__aenter__ = AsyncMock(return_value=mock_aiohttp_response)
            mock_context_manager.__aexit__ = AsyncMock(return_value=None)
            
            # Mock-объект для session.post
            mock_post = Mock(return_value=mock_context_manager)
            
            # Mock-объект для session
            mock_session = Mock()
            mock_session.post = mock_post
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            
            with patch('aiohttp.ClientSession', return_value=mock_session):
                result = await payment_service.check_payment(uuid)
                
                # Проверяем, что запрос был отправлен
                mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_service_without_cache(self):
        """Тест работы сервиса без кеша"""
        service = PaymentService(
            merchant_uuid="test_merchant",
            api_key="test_api_key",
            payment_cache=None
        )
        
        # Проверяем, что сервис работает без ошибок
        assert service.merchant_uuid == "test_merchant"
        assert service.api_key == "test_api_key"
        assert service.payment_cache is None

    @pytest.mark.asyncio
    async def test_service_logging_configuration(self, payment_service):
        """Тест конфигурации логирования"""
        assert hasattr(payment_service, 'logger')
        assert payment_service.logger.name == 'services.payment.payment_service'

if __name__ == "__main__":
    pytest.main([__file__, "-v"])