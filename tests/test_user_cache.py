"""
Unit-тесты для UserCache сервиса
Тестируем кэширование пользовательских данных с graceful degradation
"""
import pytest
import json
import asyncio
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime, timedelta
import time

from services.cache.user_cache import UserCache, LocalCache
from config.settings import settings


class TestLocalCache:
    """Тесты локального кэша"""
    
    def test_local_cache_init(self):
        """Тест инициализации локального кэша"""
        cache = LocalCache(max_size=100, ttl=60)
        assert cache.max_size == 100
        assert cache.ttl == 60
        assert isinstance(cache.cache, dict)
        assert isinstance(cache.access_times, dict)
        
    def test_local_cache_set_get(self):
        """Тест сохранения и получения данных из локального кэша"""
        cache = LocalCache(max_size=100, ttl=60)
        test_data = {"name": "test", "value": 123}
        
        # Сохраняем данные
        result = cache.set("test_key", test_data)
        assert result is True
        
        # Получаем данные - LocalCache сохраняет данные в структуре {'data': value}
        retrieved = cache.get("test_key")
        assert retrieved == {"data": test_data}  # LocalCache возвращает структуру с полем 'data'
        
    def test_local_cache_expiration(self):
        """Тест истечения срока действия данных в локальном кэше"""
        cache = LocalCache(max_size=100, ttl=1)  # 1 секунда TTL
        
        test_data = {"name": "test"}
        cache.set("test_key", test_data)
        
        # Данные должны быть доступны сразу в структуре {'data': value}
        assert cache.get("test_key") == {"data": test_data}
        
        # Ждем истечения TTL
        time.sleep(1.1)
        
        # Данные должны быть удалены
        assert cache.get("test_key") is None
        
    def test_local_cache_cleanup(self):
        """Тест очистки устаревших записей"""
        # Используем минимальный TTL 1 секунда для теста
        cache = LocalCache(max_size=100, ttl=1)
        
        # Добавляем несколько записей
        for i in range(3):
            cache.set(f"key_{i}", {"value": i})
        
        # Ждем истечения TTL
        time.sleep(1.1)
        
        # Все записи должны быть удалены
        for i in range(3):
            assert cache.get(f"key_{i}") is None


class TestUserCache:
    """Тесты UserCache сервиса"""
    
    @pytest.fixture
    def mock_redis(self):
        """Фикстура для мока Redis клиента"""
        mock_client = AsyncMock()
        return mock_client
    
    @pytest.fixture
    def user_cache(self, mock_redis):
        """Фикстура для создания UserCache экземпляра"""
        return UserCache(mock_redis)
    
    @pytest.fixture
    def test_user_data(self):
        """Фикстура с тестовыми данными пользователя"""
        return {
            "id": 123,
            "username": "test_user",
            "first_name": "Test",
            "last_name": "User",
            "is_premium": False
        }
    
    @pytest.mark.asyncio
    async def test_cache_user_profile_success(self, user_cache, mock_redis, test_user_data):
        """Тест успешного кэширования профиля пользователя"""
        # Настраиваем мок Redis
        mock_redis.setex = AsyncMock()
        
        result = await user_cache.cache_user_profile(123, test_user_data)
        
        assert result is True
        mock_redis.setex.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_cache_user_profile_redis_error(self, user_cache, mock_redis, test_user_data):
        """Тест кэширования профиля с ошибкой Redis"""
        # Настраиваем мок Redis для вызова ошибки
        mock_redis.setex = AsyncMock(side_effect=Exception("Redis error"))
        
        # Включаем локальный кэш
        user_cache.local_cache_enabled = True
        user_cache.local_cache = LocalCache(max_size=100, ttl=300)
        
        result = await user_cache.cache_user_profile(123, test_user_data)
        
        # Должен вернуть True благодаря graceful degradation
        assert result is True
        
    @pytest.mark.asyncio
    async def test_get_user_profile_success(self, user_cache, mock_redis, test_user_data):
        """Тест успешного получения профиля из кэша"""
        # Добавляем обязательное поле cached_at в тестовые данные
        test_data_with_cached_at = test_user_data.copy()
        test_data_with_cached_at['cached_at'] = datetime.utcnow().isoformat()
        
        # Настраиваем мок Redis для возврата данных
        serialized_data = json.dumps(test_data_with_cached_at, default=str)
        mock_redis.get = AsyncMock(return_value=serialized_data)
        
        result = await user_cache.get_user_profile(123)
        
        # UserCache удаляет служебное поле cached_at при возврате
        assert result == test_user_data
        mock_redis.get.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_get_user_profile_not_found(self, user_cache, mock_redis):
        """Тест получения профиля, которого нет в кэше"""
        mock_redis.get = AsyncMock(return_value=None)
        
        result = await user_cache.get_user_profile(123)
        
        assert result is None
        mock_redis.get.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_cache_user_balance_success(self, user_cache, mock_redis):
        """Тест успешного кэширования баланса пользователя"""
        mock_redis.setex = AsyncMock()
        
        result = await user_cache.cache_user_balance(123, 1000)
        
        assert result is True
        mock_redis.setex.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_get_user_balance_success(self, user_cache, mock_redis):
        """Тест успешного получения баланса из кэша"""
        balance_data = {"balance": 1000, "cached_at": datetime.utcnow().isoformat()}
        serialized_data = json.dumps(balance_data, default=str)
        mock_redis.get = AsyncMock(return_value=serialized_data)
        
        result = await user_cache.get_user_balance(123)
        
        assert result == 1000
        mock_redis.get.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_update_user_balance_success(self, user_cache, mock_redis):
        """Тест успешного обновления баланса в кэше"""
        mock_redis.setex = AsyncMock()
        
        result = await user_cache.update_user_balance(123, 1500)
        
        assert result is True
        mock_redis.setex.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_invalidate_user_cache_success(self, user_cache, mock_redis):
        """Тест успешной инвалидации кэша пользователя"""
        # Настраиваем мок для возврата списка ключей
        mock_redis.keys = AsyncMock(return_value=[b"user:123:profile", b"user:123:balance"])
        mock_redis.delete = AsyncMock()
        
        result = await user_cache.invalidate_user_cache(123)
        
        assert result is True
        mock_redis.keys.assert_called_once()
        mock_redis.delete.assert_called_once_with(b"user:123:profile", b"user:123:balance")
        
    @pytest.mark.asyncio
    async def test_is_user_cached_success(self, user_cache, mock_redis):
        """Тест проверки наличия пользователя в кэше"""
        mock_redis.exists = AsyncMock(return_value=1)
        
        result = await user_cache.is_user_cached(123)
        
        assert result is True
        mock_redis.exists.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_get_cache_stats_success(self, user_cache, mock_redis):
        """Тест получения статистики кэша"""
        # Настраиваем моки для разных ключей
        mock_redis.exists = AsyncMock(side_effect=[1, 0, 1])  # profile exists, balance not, activity exists
        mock_redis.ttl = AsyncMock(return_value=300)
        
        result = await user_cache.get_cache_stats(123)
        
        assert 'profile' in result
        assert 'balance' in result
        assert 'activity' in result
        assert result['profile']['exists'] is True
        assert result['balance']['exists'] is False
        assert result['activity']['exists'] is True


class TestUserCacheGracefulDegradation:
    """Тесты graceful degradation функциональности"""
    
    @pytest.fixture
    def user_cache_no_redis(self):
        """Фикстура для UserCache без Redis"""
        return UserCache(None)
    
    @pytest.fixture
    def test_user_data(self):
        """Фикстура с тестовыми данными пользователя"""
        return {
            "id": 123,
            "username": "test_user",
            "first_name": "Test",
            "last_name": "User",
            "is_premium": False
        }
    
    @pytest.mark.asyncio
    async def test_cache_without_redis_local_enabled(self, user_cache_no_redis, test_user_data):
        """Тест кэширования без Redis с включенным локальным кэшем"""
        user_cache_no_redis.local_cache_enabled = True
        user_cache_no_redis.local_cache = LocalCache(max_size=100, ttl=300)
        
        result = await user_cache_no_redis.cache_user_profile(123, test_user_data)
        
        # Должен успешно сохранить в локальный кэш
        assert result is True
        
        # Проверяем, что данные действительно в локальном кэше
        # LocalCache возвращает данные в структуре {'data': value}
        cached_data = user_cache_no_redis.local_cache.get("user:123:profile")
        assert cached_data == {"data": test_user_data}
        
    @pytest.mark.asyncio
    async def test_get_without_redis_local_enabled(self, user_cache_no_redis, test_user_data):
        """Тест получения данных без Redis с включенным локальным кэшем"""
        user_cache_no_redis.local_cache_enabled = True
        user_cache_no_redis.local_cache = LocalCache(max_size=100, ttl=300)
        
        # Сначала сохраняем данные (LocalCache использует структуру {'data': value})
        user_cache_no_redis.local_cache.set("user:123:profile", test_user_data)
        
        # Затем получаем
        result = await user_cache_no_redis.get_user_profile(123)
        
        assert result == test_user_data
        
    @pytest.mark.asyncio
    async def test_cache_without_redis_local_disabled(self, user_cache_no_redis, test_user_data):
        """Тест кэширования без Redis с выключенным локальным кэшем"""
        user_cache_no_redis.local_cache_enabled = False
        user_cache_no_redis.local_cache = None
        
        result = await user_cache_no_redis.cache_user_profile(123, test_user_data)
        
        # Должен вернуть False, так как некуда сохранять
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])