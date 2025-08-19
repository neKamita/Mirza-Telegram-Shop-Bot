"""
Тесты для FragmentService
"""
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, Mock

from services.fragment_service import FragmentService


class TestFragmentService:
    """Тесты для FragmentService"""
    
    @pytest.fixture
    def fragment_service(self):
        """Фикстура для создания экземпляра FragmentService"""
        return FragmentService()
    
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


if __name__ == "__main__":
    pytest.main([__file__])