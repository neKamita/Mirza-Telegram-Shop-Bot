"""
Comprehensive tests for PaymentCache service - увеличение coverage до 80%+
"""
import pytest
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone
from services.cache.payment_cache import PaymentCache, LocalCache


class TestPaymentCacheComprehensive:
    """Комплексные тесты для PaymentCache"""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client fixture"""
        mock = AsyncMock()
        mock.get = AsyncMock()
        mock.setex = AsyncMock()
        mock.delete = AsyncMock()
        mock.keys = AsyncMock()
        mock.lrange = AsyncMock()
        mock.lpush = AsyncMock()
        mock.lrem = AsyncMock()
        mock.expire = AsyncMock()
        mock.exists = AsyncMock()
        return mock

    @pytest.fixture
    def payment_cache(self, mock_redis):
        """PaymentCache instance with mock Redis"""
        cache = PaymentCache(mock_redis)
        # Включаем локальный кэш для тестов
        cache.local_cache_enabled = True
        cache.local_cache = LocalCache(max_size=1000, ttl=300)
        return cache

    # LocalCache тесты

    @pytest.mark.asyncio
    async def test_local_cache_remove_key(self):
        """Тест удаления ключа из локального кэша"""
        cache = LocalCache(max_size=100, ttl=300)
        cache.set("test_key", {"data": "value"})
        
        # Проверяем что ключ есть
        assert cache.get("test_key") is not None
        
        # Удаляем ключ
        cache._remove_key("test_key")
        
        # Проверяем что ключ удален
        assert cache.get("test_key") is None
        assert "test_key" not in cache.access_times

    @pytest.mark.asyncio
    async def test_local_cache_cleanup_expired_multiple(self):
        """Тест очистки нескольких устаревших записей"""
        cache = LocalCache(max_size=100, ttl=1)  # 1 секунда TTL
        
        # Добавляем несколько записей
        cache.set("key1", {"data": "value1"})
        cache.set("key2", {"data": "value2"})
        cache.set("key3", {"data": "value3"})
        
        # Ждем истечения TTL
        time.sleep(1.1)
        
        # Запускаем очистку явно
        cache._cleanup_expired()
        
        # Все ключи должны быть удалены
        assert cache.get("key1") is None
        assert cache.get("key2") is None  
        assert cache.get("key3") is None

    # Execute Redis operation тесты

    @pytest.mark.asyncio
    async def test_execute_redis_operation_no_client(self, payment_cache):
        """Тест выполнения Redis операций без клиента"""
        payment_cache.redis_client = None
        
        with pytest.raises(ConnectionError):
            await payment_cache._execute_redis_operation('get', 'test_key')

    @pytest.mark.asyncio
    async def test_execute_redis_operation_sync_method(self, payment_cache):
        """Тест выполнения синхронной Redis операции"""
        # Создаем sync Redis client
        sync_redis = MagicMock()
        sync_redis.sync_get = MagicMock(return_value="sync_result")
        payment_cache.redis_client = sync_redis
        
        result = await payment_cache._execute_redis_operation('sync_get', 'test_key')
        
        assert result == "sync_result"
        sync_redis.sync_get.assert_called_once_with('test_key')

    # Cache invoice advanced тесты

    @pytest.mark.asyncio
    async def test_cache_invoice_general_exception(self, payment_cache, mock_redis):
        """Тест общего исключения в cache_invoice"""
        # Отключаем локальный кэш и Redis чтобы получить False
        payment_cache.local_cache = None
        mock_redis.setex = AsyncMock(side_effect=Exception("Redis error"))
        
        result = await payment_cache.cache_invoice("test_invoice", {"data": "test"})
            
        assert result is False

    # Get invoice advanced тесты

    @pytest.mark.asyncio
    async def test_get_invoice_invalid_cached_at_format(self, payment_cache, mock_redis):
        """Тест получения invoice с невалидным форматом cached_at"""
        invoice_data = {
            "invoice_id": "test",
            "cached_at": "invalid-datetime-format"
        }
        mock_redis.get = AsyncMock(return_value=json.dumps(invoice_data))
        mock_redis.delete = AsyncMock()
        
        result = await payment_cache.get_invoice("test_invoice")
        
        assert result is None
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_invoice_no_cached_at_field(self, payment_cache, mock_redis):
        """Тест получения invoice без поля cached_at"""
        invoice_data = {"invoice_id": "test", "amount": 100}  # Без cached_at
        mock_redis.get = AsyncMock(return_value=json.dumps(invoice_data))
        mock_redis.delete = AsyncMock()
        
        result = await payment_cache.get_invoice("test_invoice")
        
        assert result is None
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_invoice_redis_non_string_with_valid_data(self, payment_cache, mock_redis):
        """Тест получения invoice с non-string данными из Redis, но валидными"""
        invoice_data = {
            "invoice_id": "test",
            "cached_at": datetime.now(timezone.utc).isoformat()
        }
        # Возвращаем как bytes чтобы попасть в elif ветку
        mock_redis.get = AsyncMock(return_value=json.dumps(invoice_data).encode())
        
        result = await payment_cache.get_invoice("test_invoice")
        
        expected = invoice_data.copy()
        expected.pop('cached_at', None)
        assert result == expected

    @pytest.mark.asyncio
    async def test_get_invoice_redis_non_string_expired(self, payment_cache, mock_redis):
        """Тест получения устаревшего invoice с non-string данными"""
        expired_time = datetime.now(timezone.utc) - timedelta(hours=2)
        invoice_data = {
            "invoice_id": "test",
            "cached_at": expired_time.isoformat()
        }
        # Возвращаем как bytes чтобы попасть в elif ветку
        mock_redis.get = AsyncMock(return_value=json.dumps(invoice_data).encode())
        mock_redis.delete = AsyncMock()
        
        result = await payment_cache.get_invoice("test_invoice")
        
        assert result is None
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_invoice_redis_error_with_local_fallback_error(self, payment_cache, mock_redis):
        """Тест ошибки Redis с ошибкой в локальном fallback"""
        mock_redis.get = AsyncMock(side_effect=Exception("Redis error"))
        
        # Создаем локальный кэш который будет падать
        payment_cache.local_cache = MagicMock()
        payment_cache.local_cache.get = MagicMock(side_effect=Exception("Local cache error"))
        
        result = await payment_cache.get_invoice("test_invoice")
        
        assert result is None

    @pytest.mark.asyncio 
    async def test_get_invoice_general_exception(self, payment_cache, mock_redis):
        """Тест общего исключения в get_invoice"""
        # Принудительно вызываем ошибку в методе
        payment_cache.INVOICE_PREFIX = None  # Вызовет TypeError
        
        result = await payment_cache.get_invoice("test_invoice")
        
        assert result is None

    # Payment status тесты

    @pytest.mark.asyncio
    async def test_cache_payment_status_redis_error(self, payment_cache, mock_redis):
        """Тест кэширования статуса платежа с ошибкой Redis"""
        mock_redis.setex = AsyncMock(side_effect=Exception("Redis error"))
        
        result = await payment_cache.cache_payment_status("test_payment", "pending")
        
        # Должно упасть на локальный кэш
        assert result is True

    @pytest.mark.asyncio
    async def test_cache_payment_status_all_fail(self, payment_cache, mock_redis):
        """Тест кэширования статуса когда все методы падают"""
        mock_redis.setex = AsyncMock(side_effect=Exception("Redis error"))
        payment_cache.local_cache = None
        
        result = await payment_cache.cache_payment_status("test_payment", "pending")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_get_payment_status_redis_non_string_expired(self, payment_cache, mock_redis):
        """Тест получения устаревшего статуса из Redis non-string"""
        expired_time = datetime.now(timezone.utc) - timedelta(hours=1)
        status_data = {
            "status": "pending", 
            "updated_at": expired_time.isoformat()
        }
        # Возвращаем как dict чтобы попасть в else ветку
        mock_redis.get = AsyncMock(return_value=status_data)
        mock_redis.delete = AsyncMock()
        
        result = await payment_cache.get_payment_status("test_payment")
        
        assert result is None
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_payment_status_redis_non_string_no_updated_at(self, payment_cache, mock_redis):
        """Тест получения статуса без поля updated_at из Redis non-string"""
        status_data = {"status": "pending"}  # Без updated_at
        mock_redis.get = AsyncMock(return_value=status_data)
        mock_redis.delete = AsyncMock()
        
        result = await payment_cache.get_payment_status("test_payment")
        
        assert result is None
        mock_redis.delete.assert_called_once()

    # Payment details тесты

    @pytest.mark.asyncio
    async def test_cache_payment_details_redis_error_with_local(self, payment_cache, mock_redis):
        """Тест кэширования деталей с ошибкой Redis но успехом локально"""
        mock_redis.setex = AsyncMock(side_effect=Exception("Redis error"))
        
        result = await payment_cache.cache_payment_details("test_payment", {"amount": 100})
        
        assert result is True
        # Проверяем что данные в локальном кэше
        local_data = payment_cache.local_cache.get("payment_details:test_payment")
        assert local_data is not None

    @pytest.mark.asyncio
    async def test_get_payment_details_redis_non_string_invalid_cached_at(self, payment_cache, mock_redis):
        """Тест получения деталей с невалидным cached_at в non-string данных"""
        details_data = {
            "amount": 100,
            "cached_at": "invalid-format"
        }
        mock_redis.get = AsyncMock(return_value=details_data)  # Не как строка
        mock_redis.delete = AsyncMock()
        
        result = await payment_cache.get_payment_details("test_payment")
        
        assert result is None
        mock_redis.delete.assert_called_once()

    # Payment transaction тесты

    @pytest.mark.asyncio
    async def test_cache_payment_transaction_all_fail(self, payment_cache, mock_redis):
        """Тест кэширования транзакции когда все методы падают"""
        mock_redis.setex = AsyncMock(side_effect=Exception("Redis error"))
        payment_cache.local_cache = None
        
        result = await payment_cache.cache_payment_transaction("test_payment", {"tx_id": "123"})
        
        assert result is False

    @pytest.mark.asyncio
    async def test_get_payment_transaction_redis_non_string_no_cached_at(self, payment_cache, mock_redis):
        """Тест получения транзакции без cached_at в non-string данных"""
        transaction_data = {"tx_id": "123"}  # Без cached_at
        mock_redis.get = AsyncMock(return_value=transaction_data)  # Не строка
        mock_redis.delete = AsyncMock()
        
        result = await payment_cache.get_payment_transaction("test_payment")
        
        assert result is None
        mock_redis.delete.assert_called_once()

    # Update payment status тесты

    @pytest.mark.asyncio
    async def test_update_payment_status_redis_error(self, payment_cache, mock_redis):
        """Тест обновления статуса с ошибкой Redis"""
        mock_redis.setex = AsyncMock(side_effect=Exception("Redis error"))
        
        result = await payment_cache.update_payment_status("test_payment", "completed")
        
        # Должно упасть на локальный кэш
        assert result is True

    @pytest.mark.asyncio
    async def test_update_payment_status_all_fail(self, payment_cache, mock_redis):
        """Тест обновления статуса когда все методы падают"""
        mock_redis.setex = AsyncMock(side_effect=Exception("Redis error"))
        payment_cache.local_cache = None
        
        result = await payment_cache.update_payment_status("test_payment", "completed")
        
        assert result is False

    # Get payments by status тесты

    @pytest.mark.asyncio
    async def test_get_payments_by_status_error(self, payment_cache, mock_redis):
        """Тест получения платежей по статусу с ошибкой"""
        mock_redis.lrange = AsyncMock(side_effect=Exception("Redis error"))
        
        result = await payment_cache.get_payments_by_status("pending")
        
        assert result == []

    @pytest.mark.asyncio
    async def test_get_payments_by_status_status_mismatch(self, payment_cache, mock_redis):
        """Тест получения платежей когда статус не совпадает"""
        mock_redis.lrange = AsyncMock(return_value=[b"pay_1"])
        
        with patch.object(payment_cache, 'get_payment_status') as mock_status:
            mock_status.return_value = {"status": "completed"}  # Не совпадает с pending
            
            result = await payment_cache.get_payments_by_status("pending")
            
            assert result == []  # Пустой список из-за несовпадения статусов

    # Invalidate cache тесты

    @pytest.mark.asyncio
    async def test_invalidate_payment_cache_error(self, payment_cache, mock_redis):
        """Тест ошибки при инвалидации кэша"""
        mock_redis.keys = AsyncMock(side_effect=Exception("Redis error"))
        
        result = await payment_cache.invalidate_payment_cache("test_payment")
        
        assert result is False

    # Payment stats тесты

    @pytest.mark.asyncio
    async def test_get_payment_stats_error(self, payment_cache, mock_redis):
        """Тест ошибки при получении статистики"""
        mock_redis.keys = AsyncMock(side_effect=Exception("Redis error"))
        
        result = await payment_cache.get_payment_stats()
        
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_payment_stats_with_recent_payments(self, payment_cache, mock_redis):
        """Тест статистики с недавними платежами"""
        mock_redis.keys = AsyncMock(return_value=[b"payment_status:pay_1"])
        
        recent_time = datetime.now(timezone.utc) - timedelta(minutes=30)
        with patch.object(payment_cache, 'get_payment_status') as mock_status:
            mock_status.return_value = {
                "status": "completed",
                "updated_at": recent_time.isoformat()
            }
            
            result = await payment_cache.get_payment_stats()
            
            assert result['total_cached_payments'] == 1
            assert len(result['recent_payments']) == 1
            assert result['recent_payments'][0]['status'] == 'completed'

    # Helper method тесты

    @pytest.mark.asyncio
    async def test_update_payment_status_index_error(self, payment_cache, mock_redis):
        """Тест ошибки при обновлении индекса статусов"""
        mock_redis.lpush = AsyncMock(side_effect=Exception("Redis error"))
        
        # Не должно падать, только логировать
        await payment_cache._update_payment_status_index("test_payment", "pending")
        
        # Проверяем что метод был вызван несмотря на ошибку
        mock_redis.lpush.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_payment_from_indices_error(self, payment_cache, mock_redis):
        """Тест ошибки при удалении из индексов"""
        mock_redis.lrem = AsyncMock(side_effect=Exception("Redis error"))
        
        # Не должно падать, только логировать
        await payment_cache._remove_payment_from_indices("test_payment")
        
        # Проверяем что метод был вызван
        assert mock_redis.lrem.call_count > 0

    @pytest.mark.asyncio
    async def test_is_payment_cached_error(self, payment_cache, mock_redis):
        """Тест ошибки при проверке наличия в кэше"""
        mock_redis.exists = AsyncMock(side_effect=Exception("Redis error"))
        
        result = await payment_cache.is_payment_cached("test_payment")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_extend_payment_cache_error(self, payment_cache, mock_redis):
        """Тест ошибки при продлении кэша"""
        mock_redis.expire = AsyncMock(side_effect=Exception("Redis error"))
        
        result = await payment_cache.extend_payment_cache("test_payment")
        
        assert result is False

    # Additional coverage тесты

    @pytest.mark.asyncio
    async def test_get_payment_details_redis_non_string_success(self, payment_cache, mock_redis):
        """Тест успешного получения деталей из non-string Redis данных"""
        details_data = {
            "amount": 100,
            "cached_at": datetime.now(timezone.utc).isoformat()
        }
        mock_redis.get = AsyncMock(return_value=details_data)  # Не как строка
        
        result = await payment_cache.get_payment_details("test_payment")
        
        expected = details_data.copy()
        expected.pop('cached_at', None)
        assert result == expected

    @pytest.mark.asyncio
    async def test_get_payment_transaction_redis_non_string_success(self, payment_cache, mock_redis):
        """Тест успешного получения транзакции из non-string Redis данных"""
        transaction_data = {
            "tx_id": "123",
            "cached_at": datetime.now(timezone.utc).isoformat()
        }
        mock_redis.get = AsyncMock(return_value=transaction_data)  # Не строка
        
        result = await payment_cache.get_payment_transaction("test_payment")
        
        expected = transaction_data.copy()
        expected.pop('cached_at', None)
        assert result == expected

    @pytest.mark.asyncio
    async def test_get_payments_by_status_with_details(self, payment_cache, mock_redis):
        """Тест получения платежей с деталями"""
        mock_redis.lrange = AsyncMock(return_value=[b"pay_1"])
        
        with patch.object(payment_cache, 'get_payment_status') as mock_status:
            with patch.object(payment_cache, 'get_payment_details') as mock_details:
                mock_status.return_value = {"status": "pending"}
                mock_details.return_value = {"amount": 100}
                
                result = await payment_cache.get_payments_by_status("pending")
                
                assert len(result) == 1
                assert result[0]['payment_id'] == "pay_1"
                assert result[0]['status']['status'] == 'pending'
                assert result[0]['details']['amount'] == 100

    @pytest.mark.asyncio
    async def test_get_payment_stats_no_recent_payments(self, payment_cache, mock_redis):
        """Тест статистики без недавних платежей"""
        mock_redis.keys = AsyncMock(return_value=[b"payment_status:pay_1"])
        
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)  # Старше 1 часа
        with patch.object(payment_cache, 'get_payment_status') as mock_status:
            mock_status.return_value = {
                "status": "completed",
                "updated_at": old_time.isoformat()
            }
            
            result = await payment_cache.get_payment_stats()
            
            assert result['total_cached_payments'] == 1
            assert len(result['recent_payments']) == 0  # Нет недавних

    @pytest.mark.asyncio
    async def test_extend_payment_cache_success(self, payment_cache, mock_redis):
        """Тест успешного продления кэша"""
        mock_redis.expire = AsyncMock(return_value=True)
        
        result = await payment_cache.extend_payment_cache("test_payment", 3600)
        
        assert result is True
        # Проверяем что expire вызван для всех ключей
        expected_calls = 3  # invoice, status, details
        assert mock_redis.expire.call_count == expected_calls

    # Дополнительные тесты для покрытия недостающих веток

    @pytest.mark.asyncio
    async def test_cache_invoice_local_cache_success(self, payment_cache, mock_redis):
        """Тест кэширования invoice только в локальный кэш"""
        # Redis недоступен, но локальный кэш работает
        payment_cache.redis_client = None
        
        result = await payment_cache.cache_invoice("test_invoice", {"amount": 100})
        
        assert result is True
        # Проверяем данные в локальном кэше
        local_data = payment_cache.local_cache.get("invoice:test_invoice")
        assert local_data is not None

    @pytest.mark.asyncio
    async def test_get_invoice_redis_string_json_error(self, payment_cache, mock_redis):
        """Тест получения invoice с ошибкой JSON парсинга из строки"""
        mock_redis.get = AsyncMock(return_value="invalid json string")
        mock_redis.delete = AsyncMock()
        
        # Устанавливаем локальный кэш как None чтобы попасть в Redis путь
        payment_cache.local_cache = None
        
        result = await payment_cache.get_invoice("test_invoice")
        
        assert result is None
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_invoice_local_cache_with_data_field(self, payment_cache, mock_redis):
        """Тест получения invoice из локального кэша с полем data"""
        invoice_data = {"amount": 100}
        
        # Redis недоступен
        payment_cache.redis_client = None
        
        # Создаем локальный кэш с данными в формате {data: actual_data}
        payment_cache.local_cache.set("invoice:test_invoice", invoice_data)
        
        result = await payment_cache.get_invoice("test_invoice")
        
        assert result == invoice_data

    @pytest.mark.asyncio
    async def test_cache_payment_details_redis_success_with_local(self, payment_cache, mock_redis):
        """Тест кэширования деталей в Redis с сохранением в локальный кэш"""
        mock_redis.setex = AsyncMock(return_value=True)
        
        details = {"amount": 100, "currency": "USD"}
        result = await payment_cache.cache_payment_details("test_payment", details)
        
        assert result is True
        # Проверяем что данные также сохранены в локальный кэш
        local_data = payment_cache.local_cache.get("payment_details:test_payment")
        assert local_data is not None

    @pytest.mark.asyncio 
    async def test_get_payment_status_local_cache_fallback_success(self, payment_cache, mock_redis):
        """Тест fallback на локальный кэш при ошибке Redis для статуса"""
        status_data = {"status": "pending", "metadata": "test"}
        
        mock_redis.get = AsyncMock(side_effect=Exception("Redis error"))
        payment_cache.local_cache.set("payment_status:test_payment", status_data)
        
        result = await payment_cache.get_payment_status("test_payment")
        
        assert result == status_data

    @pytest.mark.asyncio
    async def test_get_payment_details_local_cache_fallback_success(self, payment_cache, mock_redis):
        """Тест fallback на локальный кэш при ошибке Redis для деталей"""
        details_data = {"amount": 100}
        
        mock_redis.get = AsyncMock(side_effect=Exception("Redis error"))
        payment_cache.local_cache.set("payment_details:test_payment", details_data)
        
        result = await payment_cache.get_payment_details("test_payment")
        
        assert result == details_data

    @pytest.mark.asyncio
    async def test_get_payment_transaction_local_cache_fallback_success(self, payment_cache, mock_redis):
        """Тест fallback на локальный кэш при ошибке Redis для транзакций"""
        transaction_data = {"tx_id": "123"}
        
        mock_redis.get = AsyncMock(side_effect=Exception("Redis error"))
        payment_cache.local_cache.set("payment:test_payment:transaction", transaction_data)
        
        result = await payment_cache.get_payment_transaction("test_payment")
        
        assert result == transaction_data

    @pytest.mark.asyncio
    async def test_update_payment_status_with_index_success(self, payment_cache, mock_redis):
        """Тест обновления статуса с успешным обновлением индекса"""
        mock_redis.setex = AsyncMock(return_value=True)
        mock_redis.lpush = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)
        
        result = await payment_cache.update_payment_status("test_payment", "completed", {"reason": "paid"})
        
        assert result is True
        mock_redis.setex.assert_called_once()
        mock_redis.lpush.assert_called_once()
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalidate_payment_cache_success_with_keys(self, payment_cache, mock_redis):
        """Тест успешной инвалидации кэша с найденными ключами"""
        # Mock keys для каждого паттерна
        mock_redis.keys = AsyncMock(side_effect=[
            [b"invoice:test_payment"],  # invoice pattern
            [b"payment_status:test_payment"],  # status pattern  
            [b"payment_details:test_payment"],  # details pattern
            [b"payment:test_payment:transaction"]  # transaction pattern
        ])
        mock_redis.delete = AsyncMock(return_value=1)
        mock_redis.lrem = AsyncMock(return_value=1)
        
        result = await payment_cache.invalidate_payment_cache("test_payment")
        
        assert result is True
        assert mock_redis.delete.call_count >= 1

    @pytest.mark.asyncio
    async def test_get_payment_stats_with_status_data_no_updated_at(self, payment_cache, mock_redis):
        """Тест статистики со статусом без updated_at"""
        mock_redis.keys = AsyncMock(return_value=[b"payment_status:pay_1"])
        
        with patch.object(payment_cache, 'get_payment_status') as mock_status:
            mock_status.return_value = {"status": "completed"}  # Без updated_at
            
            result = await payment_cache.get_payment_stats()
            
            assert result['total_cached_payments'] == 1
            assert 'completed' in result['payments_by_status']
            assert len(result['recent_payments']) == 0  # Нет updated_at

    @pytest.mark.asyncio
    async def test_get_payment_stats_status_data_none(self, payment_cache, mock_redis):
        """Тест статистики когда get_payment_status возвращает None"""
        mock_redis.keys = AsyncMock(return_value=[b"payment_status:pay_1"])
        
        with patch.object(payment_cache, 'get_payment_status') as mock_status:
            mock_status.return_value = None
            
            result = await payment_cache.get_payment_stats()
            
            assert result['total_cached_payments'] == 1
            # Статистика по статусам будет пустой из-за None
            assert result['payments_by_status'] == {}

    @pytest.mark.asyncio
    async def test_is_payment_cached_true(self, payment_cache, mock_redis):
        """Тест проверки наличия платежа в кэше - найден"""
        mock_redis.exists = AsyncMock(return_value=1)  # Ключ существует
        
        result = await payment_cache.is_payment_cached("test_payment")
        
        assert result is True

    @pytest.mark.asyncio
    async def test_is_payment_cached_false(self, payment_cache, mock_redis):
        """Тест проверки наличия платежа в кэше - не найден"""
        mock_redis.exists = AsyncMock(return_value=0)  # Ключ не существует
        
        result = await payment_cache.is_payment_cached("test_payment")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_extend_payment_cache_default_ttl(self, payment_cache, mock_redis):
        """Тест продления кэша с TTL по умолчанию"""
        mock_redis.expire = AsyncMock(return_value=True)
        
        result = await payment_cache.extend_payment_cache("test_payment")  # Без additional_ttl
        
        assert result is True
        # Проверяем что использован DEFAULT_TTL
        expected_calls = 3
        assert mock_redis.expire.call_count == expected_calls
