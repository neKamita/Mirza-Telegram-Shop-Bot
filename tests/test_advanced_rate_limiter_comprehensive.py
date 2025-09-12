"""
Comprehensive tests for Advanced Rate Limiter
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
import time
from datetime import datetime, timedelta

from services.system.advanced_rate_limiter import AdvancedRateLimiter, UserType
from services.cache.rate_limit_cache import RateLimitCache


class TestAdvancedRateLimiterComprehensive:
    """Comprehensive tests for Advanced Rate Limiter"""

    @pytest.fixture
    def mock_rate_limit_cache(self):
        """Mock для RateLimitCache"""
        cache = Mock(spec=RateLimitCache)
        cache.check_user_rate_limit = AsyncMock(return_value=True)
        cache.check_global_rate_limit = AsyncMock(return_value=True)
        cache._execute_redis_operation = AsyncMock()
        cache._cleanup_old_entries = AsyncMock()
        cache.get_rate_limit_info = AsyncMock(return_value={
            "current": 0,
            "limit": 10,
            "remaining": 10,
            "reset_time": int(time.time()) + 60
        })
        return cache

    @pytest.fixture
    def rate_limiter(self, mock_rate_limit_cache):
        """Fixture с инициализированным AdvancedRateLimiter"""
        return AdvancedRateLimiter(mock_rate_limit_cache)

    @pytest.mark.asyncio
    async def test_init(self, mock_rate_limit_cache):
        """Тест инициализации AdvancedRateLimiter"""
        rate_limiter = AdvancedRateLimiter(mock_rate_limit_cache)
        
        assert rate_limiter.rate_limit_cache is mock_rate_limit_cache
        assert hasattr(rate_limiter, 'logger')
        assert rate_limiter._user_type_cache == {}

    @pytest.mark.asyncio
    async def test_check_rate_limit_success_all_checks_pass(self, rate_limiter, mock_rate_limit_cache):
        """Тест успешной проверки rate limit - все проверки проходят"""
        user_id = 123
        action = "message"
        
        # Настраиваем мocks
        mock_rate_limit_cache._execute_redis_operation.return_value = None  # Новый пользователь
        mock_rate_limit_cache.check_user_rate_limit.return_value = True
        mock_rate_limit_cache.check_global_rate_limit.return_value = True
        mock_rate_limit_cache._cleanup_old_entries.return_value = None
        mock_rate_limit_cache._execute_redis_operation.side_effect = [
            None,  # get user_created
            None,  # setex user_created
            None,  # get premium
            None,  # get suspicious
            0,     # llen burst_key
            None,  # lpush burst_key
            None   # expire burst_key
        ]
        
        allowed, info = await rate_limiter.check_rate_limit(user_id, action)
        
        assert allowed is True
        assert info["user_type"] == UserType.NEW.value
        assert "limits" in info

    @pytest.mark.asyncio
    async def test_check_rate_limit_burst_limit_exceeded(self, rate_limiter, mock_rate_limit_cache):
        """Тест превышения burst лимита"""
        user_id = 123
        action = "message"
        
        # Создаем отдельный mock для _execute_redis_operation
        def mock_redis_calls(*args):
            if args[0] == 'get' and 'user_created' in args[1]:
                return None
            elif args[0] == 'setex':
                return None
            elif args[0] == 'get' and 'premium' in args[1]:
                return None
            elif args[0] == 'get' and 'suspicious' in args[1]:
                return None
            elif args[0] == 'llen':
                return 100  # Превышает лимит
            return None
        
        mock_rate_limit_cache._execute_redis_operation.side_effect = mock_redis_calls
        
        allowed, info = await rate_limiter.check_rate_limit(user_id, action)
        
        assert allowed is False
        assert info["reason"] == "burst_limit_exceeded"
        assert "burst_info" in info

    @pytest.mark.asyncio
    async def test_check_rate_limit_personal_limit_exceeded(self, rate_limiter, mock_rate_limit_cache):
        """Тест превышения персонального лимита"""
        user_id = 123
        action = "message"
        
        # Burst лимит проходит, но персональный не проходит
        mock_rate_limit_cache._execute_redis_operation.side_effect = [
            None,  # get user_created
            None,  # setex user_created
            None,  # get premium
            None,  # get suspicious
            0,     # llen burst_key
            None,  # lpush burst_key
            None   # expire burst_key
        ]
        mock_rate_limit_cache.check_user_rate_limit.return_value = False
        
        allowed, info = await rate_limiter.check_rate_limit(user_id, action)
        
        assert allowed is False
        assert info["reason"] == "personal_limit_exceeded"

    @pytest.mark.asyncio
    async def test_check_rate_limit_global_limit_exceeded(self, rate_limiter, mock_rate_limit_cache):
        """Тест превышения глобального лимита"""
        user_id = 123
        action = "message"
        
        # Персональный лимит проходит, но глобальный не проходит
        mock_rate_limit_cache._execute_redis_operation.side_effect = [
            None,  # get user_created
            None,  # setex user_created
            None,  # get premium
            None,  # get suspicious
            0,     # llen burst_key
            None,  # lpush burst_key
            None   # expire burst_key
        ]
        mock_rate_limit_cache.check_user_rate_limit.return_value = True
        mock_rate_limit_cache.check_global_rate_limit.return_value = False
        
        allowed, info = await rate_limiter.check_rate_limit(user_id, action)
        
        assert allowed is False
        assert info["reason"] == "global_limit_exceeded"

    @pytest.mark.asyncio
    async def test_check_rate_limit_with_exception(self, rate_limiter, mock_rate_limit_cache):
        """Тест обработки исключения в check_rate_limit"""
        user_id = 123
        action = "message"
        
        # Настраиваем исключение в основном методе
        with patch.object(rate_limiter, '_determine_user_type', side_effect=Exception("Redis error")):
            allowed, info = await rate_limiter.check_rate_limit(user_id, action)
        
        # Fail open для надежности
        assert allowed is True
        assert "error" in info

    @pytest.mark.asyncio
    async def test_determine_user_type_cache_hit(self, rate_limiter):
        """Тест определения типа пользователя с попаданием в кеш"""
        user_id = 123
        
        # Добавляем в кеш
        rate_limiter._user_type_cache[user_id] = (UserType.PREMIUM, datetime.now())
        
        user_type = await rate_limiter._determine_user_type(user_id)
        
        assert user_type == UserType.PREMIUM

    @pytest.mark.asyncio
    async def test_determine_user_type_cache_expired(self, rate_limiter, mock_rate_limit_cache):
        """Тест определения типа пользователя с устаревшим кешем"""
        user_id = 123
        
        # Добавляем устаревший кеш
        old_time = datetime.now() - timedelta(minutes=10)
        rate_limiter._user_type_cache[user_id] = (UserType.PREMIUM, old_time)
        
        # Настраиваем возврат обычного пользователя
        mock_rate_limit_cache._execute_redis_operation.side_effect = [
            str(int(time.time() - 25 * 3600)),  # get user_created - старый пользователь
            None,  # get premium
            None   # get suspicious
        ]
        
        user_type = await rate_limiter._determine_user_type(user_id)
        
        assert user_type == UserType.REGULAR

    @pytest.mark.asyncio
    async def test_classify_user_new_user(self, rate_limiter, mock_rate_limit_cache):
        """Тест классификации нового пользователя"""
        user_id = 123
        
        # Новый пользователь
        mock_rate_limit_cache._execute_redis_operation.side_effect = [
            None,  # get user_created - не найден
            None   # setex user_created
        ]
        
        user_type = await rate_limiter._classify_user(user_id)
        
        assert user_type == UserType.NEW

    @pytest.mark.asyncio
    async def test_classify_user_recent_new_user(self, rate_limiter, mock_rate_limit_cache):
        """Тест классификации недавно зарегистрированного пользователя"""
        user_id = 123
        
        # Пользователь зарегистрирован час назад
        mock_rate_limit_cache._execute_redis_operation.side_effect = [
            str(int(time.time() - 3600)),  # get user_created - час назад
        ]
        
        with patch('config.settings.settings.rate_limit_new_user_hours', 24):
            user_type = await rate_limiter._classify_user(user_id)
        
        assert user_type == UserType.NEW

    @pytest.mark.asyncio
    async def test_classify_user_premium_user(self, rate_limiter, mock_rate_limit_cache):
        """Тест классификации премиум пользователя"""
        user_id = 123
        
        mock_rate_limit_cache._execute_redis_operation.side_effect = [
            str(int(time.time() - 25 * 3600)),  # get user_created - старый пользователь
            "1",   # get premium - является премиум
        ]
        
        user_type = await rate_limiter._classify_user(user_id)
        
        assert user_type == UserType.PREMIUM

    @pytest.mark.asyncio
    async def test_classify_user_suspicious_user(self, rate_limiter, mock_rate_limit_cache):
        """Тест классификации подозрительного пользователя"""
        user_id = 123
        
        mock_rate_limit_cache._execute_redis_operation.side_effect = [
            str(int(time.time() - 25 * 3600)),  # get user_created - старый пользователь
            None,  # get premium - не премиум
            "1"    # get suspicious - подозрительный
        ]
        
        user_type = await rate_limiter._classify_user(user_id)
        
        assert user_type == UserType.SUSPICIOUS

    @pytest.mark.asyncio
    async def test_classify_user_regular_user(self, rate_limiter, mock_rate_limit_cache):
        """Тест классификации обычного пользователя"""
        user_id = 123
        
        mock_rate_limit_cache._execute_redis_operation.side_effect = [
            str(int(time.time() - 25 * 3600)),  # get user_created - старый пользователь
            None,  # get premium - не премиум
            None   # get suspicious - не подозрительный
        ]
        
        user_type = await rate_limiter._classify_user(user_id)
        
        assert user_type == UserType.REGULAR

    @pytest.mark.asyncio
    async def test_classify_user_with_exception(self, rate_limiter, mock_rate_limit_cache):
        """Тест классификации пользователя с исключением"""
        user_id = 123
        
        mock_rate_limit_cache._execute_redis_operation.side_effect = Exception("Redis error")
        
        user_type = await rate_limiter._classify_user(user_id)
        
        assert user_type == UserType.REGULAR  # По умолчанию

    def test_get_limits_for_user_type_new_user(self, rate_limiter):
        """Тест получения лимитов для нового пользователя"""
        with patch('config.settings.settings') as mock_settings:
            mock_settings.rate_limit_user_messages = 20
            mock_settings.rate_limit_global_messages = 1000
            mock_settings.rate_limit_burst_messages = 5
            mock_settings.rate_limit_new_user_messages = 15
            mock_settings.rate_limit_new_user_operations = 10
            
            limits = rate_limiter._get_limits_for_user_type(UserType.NEW, "message")
            
            # Логика: min(base_limit, new_user_limit) = min(20, 15) = 15
            assert limits["personal"] == 15  # Минимум между базовым и лимитом для новых
            # Проверяем что burst изначально равен базовому значению
            assert limits["burst"] == 5  # Базовое значение для NEW пользователей

    def test_get_limits_for_user_type_premium_user(self, rate_limiter):
        """Тест получения лимитов для премиум пользователя"""
        with patch('config.settings.settings') as mock_settings:
            mock_settings.rate_limit_user_messages = 20
            mock_settings.rate_limit_global_messages = 1000
            mock_settings.rate_limit_burst_messages = 5
            mock_settings.rate_limit_premium_multiplier = 2.0
            
            limits = rate_limiter._get_limits_for_user_type(UserType.PREMIUM, "message")
            
            assert limits["personal"] == 60  # Умножено на multiplier: 30 (базовый) * 2
            assert limits["burst"] == 20  # Умножено на multiplier: 10 (базовый) * 2

    def test_get_limits_for_user_type_suspicious_user(self, rate_limiter):
        """Тест получения лимитов для подозрительного пользователя"""
        with patch('config.settings.settings') as mock_settings:
            mock_settings.rate_limit_user_messages = 20
            mock_settings.rate_limit_global_messages = 1000
            mock_settings.rate_limit_burst_messages = 5
            
            limits = rate_limiter._get_limits_for_user_type(UserType.SUSPICIOUS, "message")
            
            assert limits["personal"] == 7  # max(1, 30 // 4) = max(1, 7) = 7
            assert limits["burst"] == 1  # Минимальный burst

    def test_get_limits_for_user_type_payment_action(self, rate_limiter):
        """Тест получения лимитов для действий с платежами"""
        with patch('config.settings.settings') as mock_settings:
            mock_settings.rate_limit_user_payments = 10
            mock_settings.rate_limit_global_payments = 100
            
            limits = rate_limiter._get_limits_for_user_type(UserType.REGULAR, "payment")
            
            assert limits["burst"] == 2  # Специальный лимит для платежей

    @pytest.mark.asyncio
    async def test_check_burst_limit_success(self, rate_limiter, mock_rate_limit_cache):
        """Тест успешной проверки burst лимита"""
        user_id = 123
        action = "message"
        limits = {"burst": 5}
        
        mock_rate_limit_cache._cleanup_old_entries.return_value = None
        mock_rate_limit_cache._execute_redis_operation.side_effect = [
            2,     # llen burst_key - текущее количество
            None,  # lpush burst_key
            None   # expire burst_key
        ]
        
        with patch('config.settings.settings.rate_limit_burst_window', 10):
            allowed, burst_info = await rate_limiter._check_burst_limit(user_id, action, limits)
        
        assert allowed is True
        assert burst_info["current_count"] == 2
        assert burst_info["limit"] == 5
        assert burst_info["remaining"] == 3

    @pytest.mark.asyncio
    async def test_check_burst_limit_exceeded(self, rate_limiter, mock_rate_limit_cache):
        """Тест превышения burst лимита"""
        user_id = 123
        action = "message"
        limits = {"burst": 3}
        
        mock_rate_limit_cache._cleanup_old_entries.return_value = None
        mock_rate_limit_cache._execute_redis_operation.return_value = 5  # llen burst_key
        
        allowed, burst_info = await rate_limiter._check_burst_limit(user_id, action, limits)
        
        assert allowed is False
        assert burst_info["current_count"] == 5
        assert burst_info["limit"] == 3

    @pytest.mark.asyncio
    async def test_check_burst_limit_with_exception(self, rate_limiter, mock_rate_limit_cache):
        """Тест обработки исключения в check_burst_limit"""
        user_id = 123
        action = "message"
        limits = {"burst": 5}
        
        mock_rate_limit_cache._cleanup_old_entries.side_effect = Exception("Redis error")
        
        allowed, burst_info = await rate_limiter._check_burst_limit(user_id, action, limits)
        
        assert allowed is True  # Fail open
        assert "error" in burst_info

    @pytest.mark.asyncio
    async def test_mark_user_as_premium_success(self, rate_limiter, mock_rate_limit_cache):
        """Тест успешного маркирования пользователя как премиум"""
        user_id = 123
        duration_hours = 48
        
        mock_rate_limit_cache._execute_redis_operation.return_value = None
        
        result = await rate_limiter.mark_user_as_premium(user_id, duration_hours)
        
        assert result is True
        mock_rate_limit_cache._execute_redis_operation.assert_called_with(
            'setex', f'user_premium:{user_id}', duration_hours * 3600, "1"
        )

    @pytest.mark.asyncio
    async def test_mark_user_as_premium_with_cache_clear(self, rate_limiter, mock_rate_limit_cache):
        """Тест маркирования премиум с очисткой кеша"""
        user_id = 123
        
        # Добавляем в кеш
        rate_limiter._user_type_cache[user_id] = (UserType.REGULAR, datetime.now())
        
        mock_rate_limit_cache._execute_redis_operation.return_value = None
        
        result = await rate_limiter.mark_user_as_premium(user_id)
        
        assert result is True
        assert user_id not in rate_limiter._user_type_cache

    @pytest.mark.asyncio
    async def test_mark_user_as_premium_with_exception(self, rate_limiter, mock_rate_limit_cache):
        """Тест обработки исключения при маркировании премиум"""
        user_id = 123
        
        mock_rate_limit_cache._execute_redis_operation.side_effect = Exception("Redis error")
        
        result = await rate_limiter.mark_user_as_premium(user_id)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_mark_user_as_suspicious_success(self, rate_limiter, mock_rate_limit_cache):
        """Тест успешного маркирования пользователя как подозрительного"""
        user_id = 123
        duration_hours = 12
        
        mock_rate_limit_cache._execute_redis_operation.return_value = None
        
        result = await rate_limiter.mark_user_as_suspicious(user_id, duration_hours)
        
        assert result is True
        mock_rate_limit_cache._execute_redis_operation.assert_called_with(
            'setex', f'user_suspicious:{user_id}', duration_hours * 3600, "1"
        )

    @pytest.mark.asyncio
    async def test_mark_user_as_suspicious_with_exception(self, rate_limiter, mock_rate_limit_cache):
        """Тест обработки исключения при маркировании подозрительного"""
        user_id = 123
        
        mock_rate_limit_cache._execute_redis_operation.side_effect = Exception("Redis error")
        
        result = await rate_limiter.mark_user_as_suspicious(user_id)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_get_user_rate_limit_status_success(self, rate_limiter, mock_rate_limit_cache):
        """Тест получения статуса rate limit пользователя"""
        user_id = 123
        
        # Настраиваем определение типа пользователя
        mock_rate_limit_cache._execute_redis_operation.side_effect = [
            str(int(time.time() - 25 * 3600)),  # get user_created
            None,  # get premium  
            None   # get suspicious
        ]
        
        # Настраиваем информацию о лимитах
        mock_rate_limit_cache.get_rate_limit_info.return_value = {
            "current": 5,
            "limit": 20,
            "remaining": 15
        }
        
        with patch('config.settings.settings') as mock_settings:
            mock_settings.rate_limit_user_messages = 20
            mock_settings.rate_limit_global_messages = 1000
            mock_settings.rate_limit_burst_messages = 5
            mock_settings.rate_limit_user_operations = 10
            mock_settings.rate_limit_global_operations = 500
            mock_settings.rate_limit_burst_operations = 3
            mock_settings.rate_limit_user_payments = 5
            mock_settings.rate_limit_global_payments = 100
            
            status = await rate_limiter.get_user_rate_limit_status(user_id)
        
        assert status["user_id"] == user_id
        assert status["user_type"] == UserType.REGULAR.value
        assert "limits" in status
        assert "current_usage" in status
        assert "message" in status["limits"]
        assert "operation" in status["limits"]
        assert "payment" in status["limits"]

    @pytest.mark.asyncio
    async def test_get_user_rate_limit_status_with_exception(self, rate_limiter, mock_rate_limit_cache):
        """Тест получения статуса пользователя с исключением"""
        user_id = 123
        
        # Настраиваем исключение
        mock_rate_limit_cache._execute_redis_operation.side_effect = Exception("Redis error")
        
        status = await rate_limiter.get_user_rate_limit_status(user_id)
        
        # Проверяем что вернулся статус (код resilient и продолжает работу)
        assert status["user_id"] == user_id
        assert "user_type" in status
        assert "limits" in status

    @pytest.mark.asyncio
    async def test_check_rate_limit_with_specified_user_type(self, rate_limiter, mock_rate_limit_cache):
        """Тест проверки rate limit с заданным типом пользователя"""
        user_id = 123
        action = "message"
        user_type = UserType.PREMIUM
        
        # Настраиваем успешные проверки
        mock_rate_limit_cache.check_user_rate_limit.return_value = True
        mock_rate_limit_cache.check_global_rate_limit.return_value = True
        mock_rate_limit_cache._execute_redis_operation.side_effect = [
            0,     # llen burst_key
            None,  # lpush burst_key
            None   # expire burst_key
        ]
        
        allowed, info = await rate_limiter.check_rate_limit(user_id, action, user_type)
        
        assert allowed is True
        assert info["user_type"] == UserType.PREMIUM.value

    def test_user_type_enum_values(self):
        """Тест значений enum UserType"""
        assert UserType.NEW.value == "new"
        assert UserType.REGULAR.value == "regular"
        assert UserType.PREMIUM.value == "premium"
        assert UserType.SUSPICIOUS.value == "suspicious"
