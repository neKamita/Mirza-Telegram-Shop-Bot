"""
Comprehensive tests for User Cache Service
"""
import pytest
import json
import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime, timedelta, timezone

from services.cache.user_cache import UserCache, LocalCache


class TestUserCacheComprehensive:
    """Comprehensive tests for UserCache"""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client"""
        mock_client = AsyncMock()
        return mock_client

    @pytest.fixture
    def user_cache(self, mock_redis):
        """UserCache instance with mock Redis"""
        return UserCache(mock_redis)

    @pytest.fixture
    def user_cache_no_redis(self):
        """UserCache instance without Redis"""
        cache = UserCache(None)
        cache.local_cache_enabled = True
        cache.local_cache = LocalCache(max_size=100, ttl=300)
        return cache

    @pytest.fixture
    def test_user_data(self):
        """Test user data"""
        return {
            "id": 123,
            "username": "test_user",
            "first_name": "Test",
            "last_name": "User",
            "is_premium": False
        }

    def test_local_cache_remove_key(self):
        """Тест удаления ключа из локального кэша"""
        cache = LocalCache(max_size=100, ttl=300)
        test_data = {"name": "test"}
        
        # Добавляем данные
        cache.set("test_key", test_data)
        assert cache.get("test_key") is not None
        
        # Удаляем ключ
        cache._remove_key("test_key")
        assert cache.get("test_key") is None
        assert "test_key" not in cache.access_times

    def test_local_cache_cleanup_expired_multiple(self):
        """Тест очистки нескольких устаревших записей"""
        cache = LocalCache(max_size=100, ttl=1)
        
        # Добавляем записи
        cache.set("key1", {"value": 1})
        cache.set("key2", {"value": 2})
        
        # Ждем истечения TTL
        time.sleep(1.1)
        
        # Добавляем новую запись для вызова cleanup
        cache.set("key3", {"value": 3})
        
        # Старые записи должны быть удалены
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.get("key3") is not None

    @pytest.mark.asyncio
    async def test_execute_redis_operation_no_client(self, user_cache):
        """Тест выполнения Redis операции без клиента"""
        user_cache.redis_client = None
        
        with pytest.raises(ConnectionError, match="Redis client is not available"):
            await user_cache._execute_redis_operation('get', 'test_key')

    @pytest.mark.asyncio
    async def test_execute_redis_operation_sync_method(self, user_cache):
        """Тест выполнения синхронной Redis операции"""
        # Создаем sync метод
        def sync_method():
            return "sync_result"
        
        user_cache.redis_client.sync_get = sync_method
        
        # Мокаем asyncio.to_thread
        with patch('asyncio.to_thread', return_value="sync_result") as mock_to_thread:
            result = await user_cache._execute_redis_operation('sync_get')
            assert result == "sync_result"
            mock_to_thread.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_user_profile_no_redis_no_local(self, user_cache, test_user_data):
        """Тест кеширования профиля без Redis и локального кэша"""
        user_cache.redis_client = None
        user_cache.local_cache = None
        
        result = await user_cache.cache_user_profile(123, test_user_data)
        assert result is False

    @pytest.mark.asyncio
    async def test_cache_user_profile_redis_success_with_local(self, user_cache, test_user_data):
        """Тест успешного кеширования в Redis с сохранением в локальный кэш"""
        user_cache.redis_client.setex = AsyncMock()
        user_cache.local_cache = LocalCache(max_size=100, ttl=300)
        
        result = await user_cache.cache_user_profile(123, test_user_data)
        
        assert result is True
        user_cache.redis_client.setex.assert_called_once()
        # Проверяем сохранение в локальный кэш
        local_data = user_cache.local_cache.get("user:123:profile")
        assert local_data is not None

    @pytest.mark.asyncio
    async def test_get_user_profile_local_cache_with_data_field(self, user_cache, test_user_data):
        """Тест получения профиля из локального кэша с полем data"""
        user_cache.local_cache = LocalCache(max_size=100, ttl=300)
        
        # Сохраняем данные через нормальный LocalCache API
        user_cache.local_cache.set("user:123:profile", test_user_data)
        
        result = await user_cache.get_user_profile(123)
        assert result == test_user_data

    @pytest.mark.asyncio
    async def test_get_user_profile_expired_cached_at(self, user_cache, test_user_data):
        """Тест получения профиля с истекшим cached_at"""
        # Данные с устаревшим временем
        expired_time = datetime.now(timezone.utc) - timedelta(hours=2)
        test_data_expired = test_user_data.copy()
        test_data_expired['cached_at'] = expired_time.isoformat()
        
        user_cache.redis_client.get = AsyncMock(return_value=json.dumps(test_data_expired))
        user_cache.redis_client.delete = AsyncMock()
        
        result = await user_cache.get_user_profile(123)
        
        assert result is None
        user_cache.redis_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_profile_invalid_cached_at(self, user_cache, test_user_data):
        """Тест получения профиля с некорректным cached_at"""
        test_data_invalid = test_user_data.copy()
        test_data_invalid['cached_at'] = "invalid_datetime"
        
        user_cache.redis_client.get = AsyncMock(return_value=json.dumps(test_data_invalid))
        user_cache.redis_client.delete = AsyncMock()
        
        result = await user_cache.get_user_profile(123)
        
        assert result is None
        user_cache.redis_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_profile_no_cached_at(self, user_cache, test_user_data):
        """Тест получения профиля без поля cached_at"""
        user_cache.redis_client.get = AsyncMock(return_value=json.dumps(test_user_data))
        user_cache.redis_client.delete = AsyncMock()
        
        result = await user_cache.get_user_profile(123)
        
        assert result is None
        user_cache.redis_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_profile_invalid_json(self, user_cache):
        """Тест получения профиля с некорректным JSON"""
        user_cache.redis_client.get = AsyncMock(return_value="invalid json")
        user_cache.redis_client.delete = AsyncMock()
        
        result = await user_cache.get_user_profile(123)
        
        assert result is None
        user_cache.redis_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_profile_redis_error_fallback(self, user_cache, test_user_data):
        """Тест fallback на локальный кэш при ошибке Redis"""
        user_cache.redis_client.get = AsyncMock(side_effect=Exception("Redis error"))
        user_cache.local_cache = LocalCache(max_size=100, ttl=300)
        
        # Сохраняем в локальный кэш
        user_cache.local_cache.set("user:123:profile", test_user_data)
        
        result = await user_cache.get_user_profile(123)
        assert result == test_user_data

    @pytest.mark.asyncio
    async def test_get_user_profile_redis_error_no_fallback(self, user_cache):
        """Тест ошибки Redis без fallback"""
        user_cache.redis_client.get = AsyncMock(side_effect=Exception("Redis error"))
        user_cache.local_cache = None
        
        result = await user_cache.get_user_profile(123)
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_user_balance_redis_error(self, user_cache):
        """Тест ошибки Redis при кешировании баланса"""
        user_cache.redis_client.setex = AsyncMock(side_effect=Exception("Redis error"))
        user_cache.local_cache = LocalCache(max_size=100, ttl=300)
        
        result = await user_cache.cache_user_balance(123, 1000)
        assert result is True  # Успешно сохранено в локальный кэш

    @pytest.mark.asyncio
    async def test_cache_user_balance_all_fail(self, user_cache):
        """Тест неудачи всех методов кеширования баланса"""
        user_cache.redis_client.setex = AsyncMock(side_effect=Exception("Redis error"))
        user_cache.local_cache = Mock()
        user_cache.local_cache.set = Mock(side_effect=Exception("Local cache error"))
        
        result = await user_cache.cache_user_balance(123, 1000)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_user_balance_local_cache_data_field(self, user_cache):
        """Тест получения баланса из локального кэша с полем data"""
        user_cache.local_cache = LocalCache(max_size=100, ttl=300)
        
        # Данные сохраняем через нормальный API LocalCache
        balance_data = {'balance': 1000}
        user_cache.local_cache.set("user:123:balance", balance_data)
        
        result = await user_cache.get_user_balance(123)
        assert result == 1000

    @pytest.mark.asyncio
    async def test_get_user_balance_local_cache_direct(self, user_cache):
        """Тест получения баланса из локального кэша напрямую"""
        user_cache.local_cache = LocalCache(max_size=100, ttl=300)
        
        # Данные сохраняем через LocalCache API
        balance_data = {'balance': 1500}
        user_cache.local_cache.set("user:123:balance", balance_data)
        
        result = await user_cache.get_user_balance(123)
        assert result == 1500

    @pytest.mark.asyncio
    async def test_get_user_balance_local_cache_error(self, user_cache):
        """Тест ошибки локального кэша при получении баланса"""
        user_cache.local_cache = Mock()
        user_cache.local_cache.get = Mock(side_effect=Exception("Local cache error"))
        
        result = await user_cache.get_user_balance(123)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_balance_redis_client_bool(self, user_cache):
        """Тест с redis_client как boolean"""
        user_cache.redis_client = True  # Не асинхронный клиент
        user_cache.local_cache = None
        
        result = await user_cache.get_user_balance(123)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_balance_redis_expired(self, user_cache):
        """Тест получения устаревшего баланса из Redis"""
        expired_time = datetime.now(timezone.utc) - timedelta(hours=1)
        balance_data = {"balance": 1000, "cached_at": expired_time.isoformat()}
        
        user_cache.redis_client.get = AsyncMock(return_value=json.dumps(balance_data))
        user_cache.redis_client.delete = AsyncMock()
        
        result = await user_cache.get_user_balance(123)
        
        assert result is None
        user_cache.redis_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_balance_redis_fallback_success(self, user_cache):
        """Тест успешного fallback при ошибке Redis"""
        user_cache.redis_client.get = AsyncMock(side_effect=Exception("Redis error"))
        user_cache.local_cache = LocalCache(max_size=100, ttl=300)
        
        # Сохраняем в локальный кэш
        balance_data = {'balance': 2000}
        user_cache.local_cache.set("user:123:balance", balance_data)
        
        result = await user_cache.get_user_balance(123)
        assert result == 2000

    @pytest.mark.asyncio
    async def test_update_user_balance_redis_bool(self, user_cache):
        """Тест обновления баланса с redis_client как boolean"""
        user_cache.redis_client = True
        user_cache.local_cache = LocalCache(max_size=100, ttl=300)
        
        result = await user_cache.update_user_balance(123, 1500)
        assert result is True  # Успешно через локальный кэш

    @pytest.mark.asyncio
    async def test_update_user_balance_redis_error(self, user_cache):
        """Тест ошибки Redis при обновлении баланса"""
        user_cache.redis_client.setex = AsyncMock(side_effect=Exception("Redis error"))
        user_cache.local_cache = LocalCache(max_size=100, ttl=300)
        
        result = await user_cache.update_user_balance(123, 1500)
        assert result is True

    @pytest.mark.asyncio
    async def test_update_user_balance_all_fail(self, user_cache):
        """Тест неудачи всех методов обновления баланса"""
        user_cache.redis_client = True  # Не асинхронный клиент
        user_cache.local_cache = Mock()
        user_cache.local_cache.set = Mock(side_effect=Exception("Local cache error"))
        
        result = await user_cache.update_user_balance(123, 1500)
        assert result is False

    @pytest.mark.asyncio
    async def test_cache_user_activity_redis_error(self, user_cache):
        """Тест ошибки Redis при кешировании активности"""
        activity_data = {"last_action": "buy", "timestamp": time.time()}
        
        user_cache.redis_client.setex = AsyncMock(side_effect=Exception("Redis error"))
        user_cache.local_cache = LocalCache(max_size=100, ttl=300)
        
        result = await user_cache.cache_user_activity(123, activity_data)
        assert result is True

    @pytest.mark.asyncio
    async def test_cache_user_activity_all_fail(self, user_cache):
        """Тест неудачи всех методов кеширования активности"""
        activity_data = {"last_action": "buy", "timestamp": time.time()}
        
        user_cache.redis_client.setex = AsyncMock(side_effect=Exception("Redis error"))
        user_cache.local_cache = Mock()
        user_cache.local_cache.set = Mock(side_effect=Exception("Local cache error"))
        
        result = await user_cache.cache_user_activity(123, activity_data)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_user_activity_local_success(self, user_cache):
        """Тест получения активности из локального кэша"""
        activity_data = {"last_action": "buy", "timestamp": time.time()}
        
        user_cache.local_cache = LocalCache(max_size=100, ttl=300)
        user_cache.local_cache.set("user:123:activity", activity_data)
        
        result = await user_cache.get_user_activity(123)
        # LocalCache возвращает данные в структуре {'data': value}
        assert result == {'data': activity_data}

    @pytest.mark.asyncio
    async def test_get_user_activity_redis_non_string(self, user_cache):
        """Тест получения активности с non-string данными из Redis"""
        user_cache.redis_client.get = AsyncMock(return_value=123)  # Non-string data
        
        result = await user_cache.get_user_activity(123)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_activity_redis_string_data(self, user_cache):
        """Тест получения активности из Redis как строка"""
        activity_data = {
            "last_action": "buy",
            "timestamp": time.time(),
            "cached_at": datetime.now(timezone.utc).isoformat()
        }
        
        user_cache.local_cache = None
        user_cache.redis_client.get = AsyncMock(return_value=json.dumps(activity_data))
        
        result = await user_cache.get_user_activity(123)
        
        # Код просто логирует строковые данные, но не парсит их
        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_activity_redis_fallback(self, user_cache):
        """Тест fallback при ошибке Redis для активности"""
        activity_data = {"last_action": "buy", "timestamp": time.time()}
        
        user_cache.redis_client.get = AsyncMock(side_effect=Exception("Redis error"))
        user_cache.local_cache = LocalCache(max_size=100, ttl=300)
        user_cache.local_cache.set("user:123:activity", activity_data)
        
        result = await user_cache.get_user_activity(123)
        # LocalCache возвращает данные в структуре {'data': value}
        assert result == {'data': activity_data}

    @pytest.mark.asyncio
    async def test_invalidate_user_cache_redis_error(self, user_cache):
        """Тест ошибки Redis при инвалидации кэша"""
        user_cache.redis_client.keys = AsyncMock(side_effect=Exception("Redis error"))
        user_cache.local_cache = LocalCache(max_size=100, ttl=300)
        
        # Добавляем данные в локальный кэш
        user_cache.local_cache.set("user:123:profile", {"test": "data"})
        
        result = await user_cache.invalidate_user_cache(123)
        
        assert result is False  # Redis ошибка означает неполную инвалидацию

    @pytest.mark.asyncio
    async def test_invalidate_user_cache_no_redis(self, user_cache):
        """Тест инвалидации без Redis клиента"""
        user_cache.redis_client = None
        user_cache.local_cache = LocalCache(max_size=100, ttl=300)
        
        # Добавляем данные в локальный кэш
        user_cache.local_cache.set("user:123:profile", {"test": "data"})
        
        result = await user_cache.invalidate_user_cache(123)
        assert result is True

    @pytest.mark.asyncio
    async def test_invalidate_user_cache_no_keys_found(self, user_cache):
        """Тест инвалидации когда ключи не найдены"""
        user_cache.redis_client.keys = AsyncMock(return_value=[])
        user_cache.local_cache = LocalCache(max_size=100, ttl=300)
        
        result = await user_cache.invalidate_user_cache(123)
        assert result is True

    @pytest.mark.asyncio
    async def test_invalidate_user_cache_local_error(self, user_cache):
        """Тест ошибки локального кэша при инвалидации"""
        user_cache.redis_client.keys = AsyncMock(return_value=["user:123:profile"])
        user_cache.redis_client.delete = AsyncMock()
        
        user_cache.local_cache = Mock()
        user_cache.local_cache.cache = Mock()
        user_cache.local_cache.cache.keys = Mock(side_effect=Exception("Local cache error"))
        
        result = await user_cache.invalidate_user_cache(123)
        assert result is False

    @pytest.mark.asyncio
    async def test_is_user_cached_redis_error(self, user_cache):
        """Тест ошибки Redis при проверке кеша"""
        user_cache.redis_client.exists = AsyncMock(side_effect=Exception("Redis error"))
        user_cache.local_cache = LocalCache(max_size=100, ttl=300)
        user_cache.local_cache.set("user:123:profile", {"test": "data"})
        
        result = await user_cache.is_user_cached(123)
        assert result is True  # Fallback к локальному кэшу

    @pytest.mark.asyncio
    async def test_is_user_cached_no_redis(self, user_cache):
        """Тест проверки кеша без Redis"""
        user_cache.redis_client = None
        user_cache.local_cache = LocalCache(max_size=100, ttl=300)
        user_cache.local_cache.set("user:123:profile", {"test": "data"})
        
        result = await user_cache.is_user_cached(123)
        assert result is True

    @pytest.mark.asyncio
    async def test_is_user_cached_local_error(self, user_cache):
        """Тест ошибки локального кэша при проверке"""
        user_cache.redis_client = None
        user_cache.local_cache = Mock()
        user_cache.local_cache.get = Mock(side_effect=Exception("Local cache error"))
        
        result = await user_cache.is_user_cached(123)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_cache_stats_no_redis(self, user_cache):
        """Тест получения статистики без Redis"""
        user_cache.redis_client = None
        user_cache.local_cache = LocalCache(max_size=100, ttl=300)
        user_cache.local_cache.set("user:123:profile", {"test": "data"})
        
        result = await user_cache.get_cache_stats(123)
        
        assert 'profile' in result
        assert result['profile']['local_cache'] is True

    @pytest.mark.asyncio
    async def test_get_cache_stats_redis_error(self, user_cache):
        """Тест ошибки Redis при получении статистики"""
        user_cache.redis_client.exists = AsyncMock(side_effect=Exception("Redis error"))
        user_cache.local_cache = None
        
        result = await user_cache.get_cache_stats(123)
        
        # Должны получить пустую статистику из-за ошибок
        assert 'profile' in result
        assert 'balance' in result
        assert 'activity' in result

    @pytest.mark.asyncio
    async def test_get_cache_stats_local_cache_error(self, user_cache):
        """Тест ошибки локального кэша в статистике"""
        user_cache.redis_client.exists = AsyncMock(return_value=0)
        user_cache.local_cache = Mock()
        user_cache.local_cache.get = Mock(side_effect=Exception("Local cache error"))
        
        result = await user_cache.get_cache_stats(123)
        
        assert 'profile' in result
        # Ошибки должны быть обработаны gracefully
