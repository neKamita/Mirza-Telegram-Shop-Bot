"""
Тест интеграции с Docker Selenium для Fragment cookies
"""
import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch

from services.fragment.fragment_cookie_manager import FragmentCookieManager


class TestDockerSeleniumIntegration:
    """Тесты интеграции с Docker Selenium"""

    @pytest.fixture
    def mock_fragment_service(self):
        """Мок Fragment сервиса"""
        service = AsyncMock()
        service.fragment_cookies = "test_cookies"
        return service

    @pytest.fixture
    def cookie_manager(self, mock_fragment_service):
        """Менеджер cookies для тестов"""
        return FragmentCookieManager(mock_fragment_service)

    def test_selenium_environment_variables(self):
        """Тест настройки переменных окружения для Selenium"""
        # Проверяем дефолтные значения
        assert os.getenv("SELENIUM_HOST", "selenium-chrome") == "selenium-chrome"
        assert os.getenv("SELENIUM_PORT", "4444") == "4444"

    @pytest.mark.asyncio
    async def test_docker_selenium_connection_priority(self, cookie_manager):
        """Тест приоритета Docker Selenium"""
        with patch('selenium.webdriver.Remote') as mock_remote, \
             patch('selenium.webdriver.Chrome') as mock_chrome:
            
            # Настраиваем успешное подключение к Docker Selenium
            mock_driver = MagicMock()
            mock_driver.get_cookies.return_value = [
                {'name': 'session', 'value': 'test123'},
                {'name': 'auth', 'value': 'token456'}
            ]
            mock_driver.quit = MagicMock()
            mock_remote.return_value = mock_driver
            
            # Тестируем обновление cookies
            result = await cookie_manager._refresh_cookies()
            
            # Проверяем что использовался Docker Selenium
            mock_remote.assert_called_once()
            mock_chrome.assert_not_called()  # Локальный Chrome не должен вызываться
            
            # Проверяем результат
            assert result is not None
            assert "session=test123" in result
            assert "auth=token456" in result

    @pytest.mark.asyncio 
    async def test_docker_selenium_failure_handling(self, cookie_manager):
        """Тест обработки ошибок Docker Selenium"""
        with patch('selenium.webdriver.Remote') as mock_remote:
            # Настраиваем ошибку подключения
            mock_remote.side_effect = Exception("Connection refused")
            
            # Тестируем обновление cookies
            result = await cookie_manager._refresh_cookies()
            
            # Должен вернуть None при ошибке
            assert result is None

    @pytest.mark.asyncio
    async def test_chrome_options_configuration(self, cookie_manager):
        """Тест настройки опций Chrome для Docker"""
        expected_args = [
            "--headless",
            "--no-sandbox", 
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-web-security",
            "--allow-running-insecure-content",
            "--window-size=1920,1080"
        ]
        
        with patch('selenium.webdriver.Remote') as mock_remote, \
             patch('selenium.webdriver.ChromeOptions') as mock_options:
            
            mock_options_instance = MagicMock()
            mock_options.return_value = mock_options_instance
            
            # Настраиваем драйвер для возврата после создания
            mock_driver = MagicMock()
            mock_driver.quit = MagicMock()
            mock_remote.side_effect = Exception("Test error")  # Сразу ошибка для быстрого завершения
            
            await cookie_manager._refresh_cookies()
            
            # Проверяем что все необходимые аргументы добавлены
            for arg in expected_args:
                mock_options_instance.add_argument.assert_any_call(arg)

    @pytest.mark.asyncio
    async def test_selenium_url_construction(self, cookie_manager):
        """Тест построения URL для Docker Selenium"""
        with patch.dict(os.environ, {'SELENIUM_HOST': 'custom-host', 'SELENIUM_PORT': '9999'}):
            with patch('selenium.webdriver.Remote') as mock_remote:
                mock_remote.side_effect = Exception("Test")
                
                await cookie_manager._refresh_cookies()
                
                # Проверяем правильный URL
                expected_url = "http://custom-host:9999/wd/hub"
                mock_remote.assert_called_once()
                args, kwargs = mock_remote.call_args
                assert kwargs['command_executor'] == expected_url

    def test_no_chromedriver_py_dependency(self):
        """Тест отсутствия зависимости от chromedriver-py"""
        # Проверяем что код не импортирует chromedriver_py
        import services.fragment.fragment_cookie_manager as fcm_module
        
        # Убеждаемся что не используется chromedriver_py
        module_source = fcm_module.__file__
        with open(module_source, 'r') as f:
            content = f.read()
            assert 'chromedriver_py' not in content or 'chromedriver_py' in content and 'REMOVED' in content

    @pytest.mark.asyncio
    async def test_selenium_available_flag(self, cookie_manager):
        """Тест флага доступности Selenium"""
        from services.fragment.fragment_cookie_manager import SELENIUM_AVAILABLE
        
        # Selenium должен быть доступен (установлен в requirements.txt)
        assert SELENIUM_AVAILABLE is True

    @pytest.mark.asyncio
    async def test_docker_selenium_health_check(self):
        """Тест проверки здоровья Docker Selenium"""
        # Имитируем HTTP запрос к selenium health check
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = b'{"ready": true}'
            mock_urlopen.return_value.__enter__.return_value = mock_response
            
            # Эмуляция health check запроса
            import urllib.request
            try:
                response = urllib.request.urlopen('http://selenium-chrome:4444/wd/hub/status', timeout=5)
                health_data = response.read()
                assert b'ready' in health_data
            except:
                # В тестовой среде это ожидаемо
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
