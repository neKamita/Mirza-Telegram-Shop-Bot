"""
Comprehensive tests for Rate Limit Cache service
"""
import pytest
import time
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timezone, timedelta

from services.cache.rate_limit_cache import RateLimitCache


class TestRateLimitCacheComprehensive:
    """Comprehensive tests for RateLimitCache"""

    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client"""
        mock_client = AsyncMock()
        # Setup default returns
        mock_client.llen.return_value = 0
        mock_client.lpush.return_value = 1
        mock_client.expire.return_value = True
        mock_client.delete.return_value = 1
        mock_client.keys.return_value = []
        mock_client.ttl.return_value = 60
        mock_client.lrem.return_value = 0
        return mock_client

    @pytest.fixture
    def rate_limit_cache(self, mock_redis_client):
        """RateLimitCache instance with mocked Redis client"""
        return RateLimitCache(mock_redis_client)

    def test_init(self, rate_limit_cache, mock_redis_client):
        """Тест инициализации RateLimitCache"""
        assert rate_limit_cache.redis_client == mock_redis_client
        assert rate_limit_cache.RATE_LIMIT_PREFIX == "rate_limit:"
        assert rate_limit_cache.GLOBAL_RATE_LIMIT_PREFIX == "global_rate_limit:"
        assert rate_limit_cache.USER_RATE_LIMIT_PREFIX == "user_rate_limit:"
        assert rate_limit_cache.ACTION_RATE_LIMIT_PREFIX == "action_rate_limit:"

    @pytest.mark.asyncio
    async def test_execute_redis_operation_async_method(self, rate_limit_cache):
        """Тест выполнения асинхронной Redis операции"""
        # Мокаем асинхронный метод
        rate_limit_cache.redis_client.get = AsyncMock(return_value=b'test_value')
        
        result = await rate_limit_cache._execute_redis_operation('get', 'test_key')
        
        assert result == b'test_value'
        rate_limit_cache.redis_client.get.assert_called_once_with('test_key')

    @pytest.mark.asyncio
    async def test_execute_redis_operation_sync_method(self, rate_limit_cache):
        """Тест выполнения синхронной Redis операции"""
        # Мокаем синхронный метод
        sync_method = Mock(return_value='sync_result')
        rate_limit_cache.redis_client.test_sync = sync_method
        
        with patch('asyncio.to_thread', return_value='sync_result') as mock_to_thread:
            result = await rate_limit_cache._execute_redis_operation('test_sync', 'arg1')
            
            assert result == 'sync_result'
            mock_to_thread.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_redis_operation_exception(self, rate_limit_cache):
        """Тест обработки исключения в Redis операции"""
        rate_limit_cache.redis_client.get = AsyncMock(side_effect=Exception("Redis error"))
        
        with pytest.raises(Exception, match="Redis error"):
            await rate_limit_cache._execute_redis_operation('get', 'test_key')

    @pytest.mark.asyncio
    async def test_check_rate_limit_success(self, rate_limit_cache, mock_redis_client):
        """Тест успешной проверки rate limit"""
        mock_redis_client.llen.return_value = 5  # Меньше лимита
        
        result = await rate_limit_cache.check_rate_limit("192.168.1.1", "api", 10, 60)
        
        assert result is True
        mock_redis_client.lpush.assert_called_once()
        mock_redis_client.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded(self, rate_limit_cache, mock_redis_client):
        """Тест превышения rate limit"""
        mock_redis_client.llen.return_value = 15  # Больше лимита
        
        result = await rate_limit_cache.check_rate_limit("192.168.1.1", "api", 10, 60)
        
        assert result is False
        mock_redis_client.lpush.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_rate_limit_exception(self, rate_limit_cache, mock_redis_client):
        """Тест обработки исключения в check_rate_limit"""
        mock_redis_client.llen.side_effect = Exception("Redis error")
        
        result = await rate_limit_cache.check_rate_limit("192.168.1.1", "api", 10, 60)
        
        # Fail open для надежности
        assert result is True

    @pytest.mark.asyncio
    async def test_check_global_rate_limit_success(self, rate_limit_cache, mock_redis_client):
        """Тест успешной проверки глобального rate limit"""
        mock_redis_client.llen.return_value = 5
        
        result = await rate_limit_cache.check_global_rate_limit("api", 10, 60)
        
        assert result is True
        mock_redis_client.lpush.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_global_rate_limit_exceeded(self, rate_limit_cache, mock_redis_client):
        """Тест превышения глобального rate limit"""
        mock_redis_client.llen.return_value = 15
        
        result = await rate_limit_cache.check_global_rate_limit("api", 10, 60)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_check_user_rate_limit_success(self, rate_limit_cache, mock_redis_client):
        """Тест успешной проверки пользовательского rate limit"""
        mock_redis_client.llen.return_value = 5
        
        result = await rate_limit_cache.check_user_rate_limit(123, "message", 10, 60)
        
        assert result is True
        mock_redis_client.lpush.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_user_rate_limit_exceeded(self, rate_limit_cache, mock_redis_client):
        """Тест превышения пользовательского rate limit"""
        mock_redis_client.llen.return_value = 15
        
        result = await rate_limit_cache.check_user_rate_limit(123, "message", 10, 60)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_check_action_rate_limit_success(self, rate_limit_cache, mock_redis_client):
        """Тест успешной проверки rate limit действия"""
        mock_redis_client.llen.return_value = 5
        
        result = await rate_limit_cache.check_action_rate_limit("payment", 10, 60)
        
        assert result is True
        mock_redis_client.lpush.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_rate_limit_info_success(self, rate_limit_cache, mock_redis_client):
        """Тест получения информации о rate limit"""
        mock_redis_client.llen.return_value = 3
        mock_redis_client.ttl.return_value = 45
        
        info = await rate_limit_cache.get_rate_limit_info("192.168.1.1", "api", 60, 10)
        
        assert info['identifier'] == "192.168.1.1"
        assert info['action'] == "api"
        assert info['current_count'] == 3
        assert info['limit'] == 10
        assert info['remaining'] == 7
        assert info['window_seconds'] == 60

    @pytest.mark.asyncio
    async def test_get_rate_limit_info_validation_errors(self, rate_limit_cache):
        """Тест валидации в get_rate_limit_info"""
        # Пустой identifier
        info = await rate_limit_cache.get_rate_limit_info("", "api", 60, 10)
        assert info == {}
        
        # Пустой action
        info = await rate_limit_cache.get_rate_limit_info("test", "", 60, 10)
        assert info == {}
        
        # Некорректный window
        info = await rate_limit_cache.get_rate_limit_info("test", "api", 0, 10)
        assert info == {}
        
        # Некорректный limit
        info = await rate_limit_cache.get_rate_limit_info("test", "api", 60, 0)
        assert info == {}

    @pytest.mark.asyncio
    async def test_reset_rate_limit_success(self, rate_limit_cache, mock_redis_client):
        """Тест сброса rate limit"""
        mock_redis_client.delete.return_value = 1
        
        result = await rate_limit_cache.reset_rate_limit("192.168.1.1", "api")
        
        assert result is True
        mock_redis_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_rate_limit_exception(self, rate_limit_cache, mock_redis_client):
        """Тест обработки исключения при сбросе rate limit"""
        mock_redis_client.delete.side_effect = Exception("Redis error")
        
        result = await rate_limit_cache.reset_rate_limit("192.168.1.1", "api")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_reset_user_rate_limits_success(self, rate_limit_cache, mock_redis_client):
        """Тест сброса всех rate limit пользователя"""
        mock_keys = [b'user_rate_limit:123:message', b'user_rate_limit:123:payment']
        mock_redis_client.keys.return_value = mock_keys
        mock_redis_client.delete.return_value = 2
        
        result = await rate_limit_cache.reset_user_rate_limits(123)
        
        assert result == 2
        mock_redis_client.keys.assert_called_once_with("user_rate_limit:123:*")

    @pytest.mark.asyncio
    async def test_reset_user_rate_limits_no_keys(self, rate_limit_cache, mock_redis_client):
        """Тест сброса rate limit для пользователя без ключей"""
        mock_redis_client.keys.return_value = []
        
        result = await rate_limit_cache.reset_user_rate_limits(123)
        
        assert result == 0
        mock_redis_client.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_rate_limit_stats_success(self, rate_limit_cache, mock_redis_client):
        """Тест получения статистики rate limit"""
        mock_keys = [
            b'rate_limit:192.168.1.1:api',
            b'rate_limit:123:message',
            b'rate_limit:456:payment'
        ]
        mock_redis_client.keys.return_value = mock_keys
        
        # Мокаем llen для разных ключей
        def llen_side_effect(key):
            if key == b'rate_limit:192.168.1.1:api':
                return 5
            elif key == b'rate_limit:123:message':
                return 3
            else:
                return 0
        
        mock_redis_client.llen.side_effect = llen_side_effect
        
        stats = await rate_limit_cache.get_rate_limit_stats()
        
        assert stats['total_rate_limits'] == 3
        assert stats['active_rate_limits'] == 2
        assert 'top_limited_actions' in stats
        assert 'top_limited_users' in stats

    @pytest.mark.asyncio
    async def test_get_rate_limit_stats_exception(self, rate_limit_cache, mock_redis_client):
        """Тест обработки исключения в статистике"""
        mock_redis_client.keys.side_effect = Exception("Redis error")
        
        stats = await rate_limit_cache.get_rate_limit_stats()
        
        assert stats == {}

    @pytest.mark.asyncio
    async def test_cleanup_old_entries_success(self, rate_limit_cache, mock_redis_client):
        """Тест очистки старых записей"""
        current_time = int(time.time())
        
        await rate_limit_cache._cleanup_old_entries("test_key", current_time, 60)
        
        mock_redis_client.lrem.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_old_entries_validation_errors(self, rate_limit_cache):
        """Тест валидации в _cleanup_old_entries"""
        current_time = int(time.time())
        
        # Код обрабатывает валидационные ошибки через try/except и логирует их,
        # но не поднимает исключения наружу
        
        # Некорректный key - должен быть обработан gracefully
        await rate_limit_cache._cleanup_old_entries("", current_time, 60)
        # Проверяем что код не падает
        
        # Некорректный current_time 
        await rate_limit_cache._cleanup_old_entries("test", 0, 60)
        # Проверяем что код не падает
        
        # Некорректный window
        await rate_limit_cache._cleanup_old_entries("test", current_time, 0)
        # Проверяем что код не падает

    @pytest.mark.asyncio
    async def test_is_rate_limited_true(self, rate_limit_cache, mock_redis_client):
        """Тест проверки ограничения - true"""
        mock_redis_client.llen.return_value = 5
        
        result = await rate_limit_cache.is_rate_limited("192.168.1.1", "api")
        
        assert result is True

    @pytest.mark.asyncio
    async def test_is_rate_limited_false(self, rate_limit_cache, mock_redis_client):
        """Тест проверки ограничения - false"""
        mock_redis_client.llen.return_value = 0
        
        result = await rate_limit_cache.is_rate_limited("192.168.1.1", "api")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_is_rate_limited_exception(self, rate_limit_cache, mock_redis_client):
        """Тест обработки исключения в is_rate_limited"""
        mock_redis_client.llen.side_effect = Exception("Redis error")
        
        result = await rate_limit_cache.is_rate_limited("192.168.1.1", "api")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_get_remaining_requests_success(self, rate_limit_cache, mock_redis_client):
        """Тест получения оставшихся запросов"""
        mock_redis_client.llen.return_value = 3
        
        remaining = await rate_limit_cache.get_remaining_requests("192.168.1.1", "api", 10, 60)
        
        assert remaining == 7  # 10 - 3 = 7

    @pytest.mark.asyncio
    async def test_get_remaining_requests_zero(self, rate_limit_cache, mock_redis_client):
        """Тест получения оставшихся запросов - ноль"""
        mock_redis_client.llen.return_value = 15
        
        remaining = await rate_limit_cache.get_remaining_requests("192.168.1.1", "api", 10, 60)
        
        assert remaining == 0  # max(0, 10 - 15) = 0

    @pytest.mark.asyncio
    async def test_get_remaining_requests_validation_errors(self, rate_limit_cache):
        """Тест валидации в get_remaining_requests"""
        # Некорректные параметры должны приводить к возврату limit
        remaining = await rate_limit_cache.get_remaining_requests("", "api", 10, 60)
        assert remaining == 10
        
        remaining = await rate_limit_cache.get_remaining_requests("test", "", 10, 60)
        assert remaining == 10

    @pytest.mark.asyncio
    async def test_increment_rate_limit_success(self, rate_limit_cache, mock_redis_client):
        """Тест инкремента rate limit"""
        mock_redis_client.lpush.return_value = 1
        mock_redis_client.expire.return_value = True
        
        result = await rate_limit_cache.increment_rate_limit("192.168.1.1", "api", 120)
        
        assert result is True
        mock_redis_client.lpush.assert_called_once()
        mock_redis_client.expire.assert_called_once_with(
            "rate_limit:192.168.1.1:api", 120
        )

    @pytest.mark.asyncio
    async def test_increment_rate_limit_default_ttl(self, rate_limit_cache, mock_redis_client):
        """Тест инкремента rate limit с TTL по умолчанию"""
        result = await rate_limit_cache.increment_rate_limit("192.168.1.1", "api")
        
        assert result is True
        mock_redis_client.expire.assert_called_once_with(
            "rate_limit:192.168.1.1:api", rate_limit_cache.DEFAULT_TTL
        )

    @pytest.mark.asyncio
    async def test_increment_rate_limit_exception(self, rate_limit_cache, mock_redis_client):
        """Тест обработки исключения в increment_rate_limit"""
        mock_redis_client.lpush.side_effect = Exception("Redis error")
        
        result = await rate_limit_cache.increment_rate_limit("192.168.1.1", "api")
        
        assert result is False
