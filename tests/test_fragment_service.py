"""
Тесты для FragmentService
"""
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, Mock

from services.fragment.fragment_service import FragmentService


class TestFragmentService:
    """Тесты для FragmentService"""
    
    @pytest.fixture
    def fragment_service(self):
        """Фикстура для создания экземпляра FragmentService"""
        return FragmentService()

    def setup_method(self):
        """Сброс circuit breaker перед каждым тестом"""
        from services.system.circuit_breaker import circuit_manager
        circuit_manager.reset_circuit("fragment_service")
    
    @pytest.mark.asyncio
    async def test_ping_success(self, fragment_service):
        """Тест успешного ping"""
        # Мock client.ping для возврата успешного результата
        with patch.object(fragment_service.client, 'ping', return_value={"status": "ok"}):
            result = await fragment_service.ping()
            assert result["status"] == "success"
            assert result["result"] == {"status": "ok"}
    
    @pytest.mark.asyncio
    async def test_ping_failure(self, fragment_service):
        """Тест неудачного ping"""
        # Мock client.ping для выброса исключения
        with patch.object(fragment_service.client, 'ping', side_effect=Exception("Connection failed")):
            result = await fragment_service.ping()
            assert result["status"] == "failed"
            assert "Connection failed" in result["error"]
    
    @pytest.mark.asyncio
    async def test_get_balance_no_seed(self, fragment_service):
        """Тест get_balance без seed phrase"""
        # Устанавливаем пустую seed phrase
        fragment_service.seed_phrase = ""
        result = await fragment_service.get_balance()
        assert result["status"] == "failed"
        assert "Seed phrase is not configured" in result["error"]
    
    @pytest.mark.asyncio
    async def test_get_balance_success(self, fragment_service):
        """Тест успешного get_balance"""
        # Устанавливаем тестовую seed phrase
        fragment_service.seed_phrase = "word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11 word12 word13 word14 word15 word16 word17 word18 word19 word20 word21 word22 word23 word24"
        
        # Мock client.get_balance для возврата успешного результата
        with patch.object(fragment_service.client, 'get_balance', return_value={"balance": "100.00", "currency": "TON"}):
            result = await fragment_service.get_balance()
            assert result["status"] == "success"
            assert result["result"] == {"balance": "100.00", "currency": "TON"}
    
    @pytest.mark.asyncio
    async def test_get_balance_failure(self, fragment_service):
        """Тест неудачного get_balance"""
        # Устанавливаем тестовую seed phrase
        fragment_service.seed_phrase = "word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11 word12 word13 word14 word15 word16 word17 word18 word19 word20 word21 word22 word23 word24"
        
        # Мock client.get_balance для выброса исключения
        with patch.object(fragment_service.client, 'get_balance', side_effect=Exception("Invalid seed")):
            result = await fragment_service.get_balance()
            assert result["status"] == "failed"
            assert "Invalid seed" in result["error"]
    
    @pytest.mark.asyncio
    async def test_get_user_info_no_cookies(self, fragment_service):
        """Тест get_user_info без cookies"""
        # Устанавливаем пустые cookies
        fragment_service.fragment_cookies = ""
        result = await fragment_service.get_user_info("@testuser")
        assert result["status"] == "failed"
        assert "Fragment cookies are not configured" in result["error"]
    
    @pytest.mark.asyncio
    async def test_get_user_info_success(self, fragment_service):
        """Тест успешного get_user_info"""
        # Устанавливаем тестовые cookies
        fragment_service.fragment_cookies = "cookie1=value1; cookie2=value2"
        
        # Мock client.get_user_info для возврата успешного результата
        with patch.object(fragment_service.client, 'get_user_info', return_value={"username": "@testuser", "stars": 100}):
            result = await fragment_service.get_user_info("@testuser")
            assert result["status"] == "success"
            assert result["result"] == {"username": "@testuser", "stars": 100}
    
    @pytest.mark.asyncio
    async def test_get_user_info_failure(self, fragment_service):
        """Тест неудачного get_user_info"""
        # Устанавливаем тестовые cookies
        fragment_service.fragment_cookies = "cookie1=value1; cookie2=value2"
        
        # Мock client.get_user_info для выброса исключения
        with patch.object(fragment_service.client, 'get_user_info', side_effect=Exception("Invalid cookies")):
            result = await fragment_service.get_user_info("@testuser")
            assert result["status"] == "failed"
            assert "Invalid cookies" in result["error"]

    @pytest.mark.asyncio
    async def test_make_api_call_with_retry_on_auth_error(self, fragment_service):
        """Тест retry механизма при ошибках авторизации"""
        fragment_service.fragment_cookies = "expired_cookies"
        
        # Mock API метода, который сначала падает с auth ошибкой, потом успешен после обновления cookies
        mock_api_method = Mock()
        mock_api_method.side_effect = [
            Exception("Cookie validation failed"),
            {"status": "success", "data": "test_data"}
        ]
        
        # Mock успешного обновления cookies
        with patch.object(fragment_service, 'refresh_cookies_if_needed', AsyncMock(return_value=True)):
            result = await fragment_service._make_api_call(mock_api_method)
            
            assert result["status"] == "success"
            assert result["result"] == {"status": "success", "data": "test_data"}
            assert mock_api_method.call_count == 2

    @pytest.mark.asyncio
    async def test_make_api_call_circuit_breaker_trip(self, fragment_service):
        """Тест срабатывания circuit breaker при многократных ошибках"""
        fragment_service.fragment_cookies = "test_cookies"
        
        # Mock API метода, который всегда падает с исключением (не возвращает {"status": "failed"})
        mock_api_method = Mock(side_effect=Exception("Service unavailable"))
        
        # Создаем функцию, которая будет выбрасывать исключение для circuit breaker
        async def failing_func():
            raise Exception("Service unavailable")
        
        # Вызываем несколько раз чтобы tripнуть circuit breaker
        for i in range(3):  # failure_threshold=3 в fragment_service конфиге
            try:
                result = await fragment_service.circuit_breaker.call(failing_func)
                # Не должно дойти сюда
                assert False, f"Expected exception on call {i+1}"
            except Exception as e:
                assert "Service unavailable" in str(e)
        
        # После trip circuit breaker должен выбрасывать исключение сразу
        try:
            await fragment_service.circuit_breaker.call(failing_func)
            assert False, "Expected circuit breaker exception"
        except Exception as e:
            assert "Circuit fragment_service is OPEN" in str(e)

    @pytest.mark.asyncio
    async def test_make_api_call_non_auth_error_no_retry(self, fragment_service):
        """Тест что не-auth ошибки не вызывают retry"""
        fragment_service.fragment_cookies = "test_cookies"
        
        # Mock API метода с не-auth ошибкой
        mock_api_method = Mock(side_effect=Exception("Validation error"))
        
        result = await fragment_service._make_api_call(mock_api_method)
        
        assert result["status"] == "failed"
        assert "Validation error" in result["error"]
        mock_api_method.assert_called_once()  # Должен вызваться только один раз

    @pytest.mark.asyncio
    async def test_make_api_call_cookie_refresh_failure(self, fragment_service):
        """Тест когда обновление cookies не удалось"""
        fragment_service.fragment_cookies = "expired_cookies"
        
        # Mock API метода с auth ошибкой
        mock_api_method = Mock(side_effect=Exception("Cookie validation failed"))
        
        # Mock неудачного обновления cookies
        with patch.object(fragment_service, 'refresh_cookies_if_needed', AsyncMock(return_value=False)):
            result = await fragment_service._make_api_call(mock_api_method)
            
            assert result["status"] == "failed"
            assert "Failed to refresh cookies" in result["error"]
            mock_api_method.assert_called_once()  # Должен вызваться только один раз

    @pytest.mark.asyncio
    async def test_refresh_cookies_if_needed_disabled(self, fragment_service):
        """Тест когда автоматическое обновление cookies отключено"""
        with patch('os.getenv', return_value="false"):
            result = await fragment_service.refresh_cookies_if_needed()
            assert result is True  # Должен вернуть True когда отключено

    @pytest.mark.asyncio
    async def test_refresh_cookies_if_needed_valid_cookies(self, fragment_service):
        """Тест когда cookies действительны и не требуют обновления"""
        fragment_service.fragment_cookies = "valid_cookies"
        
        with patch.object(fragment_service.cookie_manager, '_are_cookies_expired', AsyncMock(return_value=False)):
            result = await fragment_service.refresh_cookies_if_needed()
            assert result is True

    @pytest.mark.asyncio
    async def test_refresh_cookies_if_needed_success(self, fragment_service):
        """Тест успешного обновления cookies"""
        fragment_service.fragment_cookies = "expired_cookies"
        
        with patch('os.getenv', side_effect=lambda key, default=None: "true" if key == "FRAGMENT_AUTO_COOKIE_REFRESH" else default), \
             patch.object(fragment_service.cookie_manager, '_are_cookies_expired', AsyncMock(return_value=True)), \
             patch.object(fragment_service.cookie_manager, '_refresh_cookies', AsyncMock(return_value="new_cookies")), \
             patch.object(fragment_service.cookie_manager, '_save_cookies_to_file', AsyncMock()):
            
            result = await fragment_service.refresh_cookies_if_needed()
            assert result is True
            assert fragment_service.fragment_cookies == "new_cookies"

    @pytest.mark.asyncio
    async def test_refresh_cookies_if_needed_failure(self, fragment_service):
        """Тест неудачного обновления cookies"""
        fragment_service.fragment_cookies = "expired_cookies"
        
        with patch('os.getenv', side_effect=lambda key, default=None: "true" if key == "FRAGMENT_AUTO_COOKIE_REFRESH" else default), \
             patch.object(fragment_service.cookie_manager, '_are_cookies_expired', AsyncMock(return_value=True)), \
             patch.object(fragment_service.cookie_manager, '_refresh_cookies', AsyncMock(return_value=None)):
            
            result = await fragment_service.refresh_cookies_if_needed()
            assert result is False

    @pytest.mark.asyncio
    async def test_buy_stars_without_kyc_success(self, fragment_service):
        """Тест успешной покупки звезд без KYC"""
        fragment_service.seed_phrase = "word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11 word12 word13 word14 word15 word16 word17 word18 word19 word20 word21 word22 word23 word24"
        
        with patch.object(fragment_service.client, 'buy_stars_without_kyc', return_value={"status": "success", "stars": 10}):
            result = await fragment_service.buy_stars_without_kyc("@testuser", 10)
            assert result["status"] == "success"
            assert result["result"] == {"status": "success", "stars": 10}

    @pytest.mark.asyncio
    async def test_buy_stars_success(self, fragment_service):
        """Тест успешной покупки звезд с KYC"""
        fragment_service.seed_phrase = "word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11 word12 word13 word14 word15 word16 word17 word18 word19 word20 word21 word22 word23 word24"
        fragment_service.fragment_cookies = "valid_cookies"
        
        with patch.object(fragment_service.client, 'buy_stars', return_value={"status": "success", "stars": 10}):
            result = await fragment_service.buy_stars("@testuser", 10)
            assert result["status"] == "success"
            assert result["result"] == {"status": "success", "stars": 10}


if __name__ == "__main__":
    pytest.main([__file__])