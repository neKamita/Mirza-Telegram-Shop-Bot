"""
Комплексные unit-тесты для FragmentCookieManager
Используются современные практики тестирования с чистыми моками и изоляцией зависимостей
"""
import pytest
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from pathlib import Path

from services.fragment.fragment_cookie_manager import FragmentCookieManager, initialize_fragment_cookies
from services.fragment.fragment_service import FragmentService


class TestFragmentCookieManager:
    """Тесты для FragmentCookieManager с использованием Dependency Injection и чистых моков"""
    
    @pytest.fixture
    def mock_fragment_service(self):
        """Мок FragmentService с настраиваемым поведением"""
        service = Mock(spec=FragmentService)
        service.fragment_cookies = "original_cookies"
        service.get_user_info = AsyncMock(return_value={"status": "success"})
        return service
    
    @pytest.fixture
    def cookie_manager(self, mock_fragment_service):
        """Экземпляр FragmentCookieManager с моком сервиса"""
        manager = FragmentCookieManager(mock_fragment_service)
        # Мокируем logger чтобы избежать реального логирования в тестах
        manager.logger = Mock()
        return manager
    
    @pytest.fixture
    def valid_cookies_data(self):
        """Валидные данные cookies для тестирования"""
        return {
            'cookies': 'test_cookie=value; session=abc123',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        }
    
    @pytest.fixture
    def expired_cookies_data(self):
        """Истекшие данные cookies для тестирования"""
        return {
            'cookies': 'test_cookie=expired; session=expired123',
            'timestamp': (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
            'expires_at': (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        }

    def test_initialization(self, mock_fragment_service):
        """Тест инициализации FragmentCookieManager"""
        # Act
        manager = FragmentCookieManager(mock_fragment_service)
        
        # Assert
        assert manager.fragment_service == mock_fragment_service
        assert manager.cookies_file == Path("fragment_cookies.json")
        assert manager.cookie_refresh_interval == 3600  # default value
        assert manager.logger is not None

    @pytest.mark.asyncio
    async def test_get_fragment_cookies_with_valid_cached_cookies(self, cookie_manager, valid_cookies_data):
        """Тест получения cookies когда есть валидные кэшированные cookies"""
        # Arrange
        mock_load = AsyncMock(return_value=valid_cookies_data['cookies'])
        mock_expired = AsyncMock(return_value=False)
        mock_refresh = AsyncMock()
        mock_save = AsyncMock()
        
        with patch.object(cookie_manager, '_load_cookies_from_file', mock_load):
            with patch.object(cookie_manager, '_are_cookies_expired', mock_expired):
                with patch.object(cookie_manager, '_refresh_cookies', mock_refresh):
                    with patch.object(cookie_manager, '_save_cookies_to_file', mock_save):
                        
                        # Act
                        result = await cookie_manager.get_fragment_cookies()
                        
                        # Assert
                        assert result == valid_cookies_data['cookies']
                        # Методы не должны были вызываться
                        mock_refresh.assert_not_called()
                        mock_save.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_fragment_cookies_with_expired_cookies_successful_refresh(self, cookie_manager, expired_cookies_data):
        """Тест получения cookies с истекшими cookies и успешным обновлением"""
        # Arrange
        new_cookies = "new_cookie=value; fresh_session=xyz789"
        
        mock_load = AsyncMock(return_value=expired_cookies_data['cookies'])
        mock_expired = AsyncMock(return_value=True)
        mock_refresh = AsyncMock(return_value=new_cookies)
        mock_save = AsyncMock()
        
        with patch.object(cookie_manager, '_load_cookies_from_file', mock_load):
            with patch.object(cookie_manager, '_are_cookies_expired', mock_expired):
                with patch.object(cookie_manager, '_refresh_cookies', mock_refresh):
                    with patch.object(cookie_manager, '_save_cookies_to_file', mock_save):
                        
                        # Act
                        result = await cookie_manager.get_fragment_cookies()
                        
                        # Assert
                        assert result == new_cookies
                        mock_refresh.assert_called_once()
                        mock_save.assert_called_once_with(new_cookies)

    @pytest.mark.asyncio
    async def test_get_fragment_cookies_with_expired_cookies_failed_refresh(self, cookie_manager, expired_cookies_data):
        """Тест получения cookies с истекшими cookies и неудачным обновление"""
        # Arrange
        mock_load = AsyncMock(return_value=expired_cookies_data['cookies'])
        mock_expired = AsyncMock(return_value=True)
        mock_refresh = AsyncMock(return_value=None)
        mock_save = AsyncMock()
        
        with patch.object(cookie_manager, '_load_cookies_from_file', mock_load):
            with patch.object(cookie_manager, '_are_cookies_expired', mock_expired):
                with patch.object(cookie_manager, '_refresh_cookies', mock_refresh):
                    with patch.object(cookie_manager, '_save_cookies_to_file', mock_save):
                        
                        # Act
                        result = await cookie_manager.get_fragment_cookies()
                        
                        # Assert
                        assert result == expired_cookies_data['cookies']  # возвращаем старые cookies
                        mock_refresh.assert_called_once()
                        mock_save.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_fragment_cookies_no_cached_cookies_successful_refresh(self, cookie_manager):
        """Тест получения cookies когда нет кэшированных cookies и обновление успешно"""
        # Arrange
        new_cookies = "new_cookie=value; fresh_session=xyz789"
        
        mock_load = AsyncMock(return_value=None)
        mock_expired = AsyncMock(return_value=True)
        mock_refresh = AsyncMock(return_value=new_cookies)
        mock_save = AsyncMock()
        
        with patch.object(cookie_manager, '_load_cookies_from_file', mock_load):
            with patch.object(cookie_manager, '_are_cookies_expired', mock_expired):
                with patch.object(cookie_manager, '_refresh_cookies', mock_refresh):
                    with patch.object(cookie_manager, '_save_cookies_to_file', mock_save):
                        
                        # Act
                        result = await cookie_manager.get_fragment_cookies()
                        
                        # Assert
                        assert result == new_cookies
                        mock_refresh.assert_called_once()
                        mock_save.assert_called_once_with(new_cookies)

    @pytest.mark.asyncio
    async def test_get_fragment_cookies_exception_handling(self, cookie_manager):
        """Тест обработки исключений в get_fragment_cookies"""
        # Arrange
        # Используем side_effect для последовательных вызовов
        mock_load = AsyncMock(side_effect=[Exception("Test error"), "fallback_cookies"])
        mock_expired = AsyncMock(return_value=True)
        
        with patch.object(cookie_manager, '_load_cookies_from_file', mock_load):
            with patch.object(cookie_manager, '_are_cookies_expired', mock_expired):
                
                # Act
                result = await cookie_manager.get_fragment_cookies()
                
                # Assert
                assert result == "fallback_cookies"
                cookie_manager.logger.error.assert_called_once()
                # Проверяем что метод вызывался два раза (первый раз с ошибкой, второй раз в блоке except)
                assert mock_load.call_count == 2

    @pytest.mark.asyncio
    async def test_load_cookies_from_file_exists(self, cookie_manager, valid_cookies_data, tmp_path):
        """Тест загрузки cookies из существующего файла"""
        # Arrange
        cookie_manager.cookies_file = tmp_path / "test_cookies.json"
        with open(cookie_manager.cookies_file, 'w') as f:
            json.dump(valid_cookies_data, f)
        
        # Act
        result = await cookie_manager._load_cookies_from_file()
        
        # Assert
        assert result == valid_cookies_data['cookies']

    @pytest.mark.asyncio
    async def test_load_cookies_from_file_not_exists(self, cookie_manager, tmp_path):
        """Тест загрузки cookies когда файл не существует"""
        # Arrange
        cookie_manager.cookies_file = tmp_path / "nonexistent.json"
        
        # Act
        result = await cookie_manager._load_cookies_from_file()
        
        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_load_cookies_from_file_invalid_json(self, cookie_manager, tmp_path):
        """Тест загрузки cookies из файла с невалидным JSON"""
        # Arrange
        cookie_manager.cookies_file = tmp_path / "invalid.json"
        with open(cookie_manager.cookies_file, 'w') as f:
            f.write("invalid json content")
        
        # Act
        result = await cookie_manager._load_cookies_from_file()
        
        # Assert
        assert result is None
        cookie_manager.logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_save_cookies_to_file_success(self, cookie_manager, tmp_path):
        """Тест успешного сохранения cookies в файл"""
        # Arrange
        cookie_manager.cookies_file = tmp_path / "test_save.json"
        test_cookies = "test_cookie=value; session=abc123"
        
        # Act
        await cookie_manager._save_cookies_to_file(test_cookies)
        
        # Assert
        assert cookie_manager.cookies_file.exists()
        with open(cookie_manager.cookies_file, 'r') as f:
            saved_data = json.load(f)
            assert saved_data['cookies'] == test_cookies
            assert 'timestamp' in saved_data
            assert 'expires_at' in saved_data

    @pytest.mark.asyncio
    async def test_save_cookies_to_file_permission_error(self, cookie_manager, tmp_path):
        """Тест обработки ошибок при сохранении cookies в файл"""
        # Arrange
        cookie_manager.cookies_file = tmp_path / "test_permission.json"
        test_cookies = "test_cookie=value"
        
        # Создаем файл без прав на запись
        cookie_manager.cookies_file.touch()
        cookie_manager.cookies_file.chmod(0o444)  # read-only
        
        # Act
        await cookie_manager._save_cookies_to_file(test_cookies)
        
        # Assert
        cookie_manager.logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_are_cookies_expired_valid(self, cookie_manager, valid_cookies_data, tmp_path):
        """Тест проверки срока действия валидных cookies"""
        # Arrange
        cookie_manager.cookies_file = tmp_path / "valid_cookies.json"
        with open(cookie_manager.cookies_file, 'w') as f:
            json.dump(valid_cookies_data, f)
        
        # Act
        result = await cookie_manager._are_cookies_expired(valid_cookies_data['cookies'])
        
        # Assert
        assert result is False

    @pytest.mark.asyncio
    async def test_are_cookies_expired_expired(self, cookie_manager, expired_cookies_data, tmp_path):
        """Тест проверки срока действия истекших cookies"""
        # Arrange
        cookie_manager.cookies_file = tmp_path / "expired_cookies.json"
        with open(cookie_manager.cookies_file, 'w') as f:
            json.dump(expired_cookies_data, f)
        
        # Act
        result = await cookie_manager._are_cookies_expired(expired_cookies_data['cookies'])
        
        # Assert
        assert result is True

    @pytest.mark.asyncio
    async def test_are_cookies_expired_no_file(self, cookie_manager):
        """Тест проверки срока действия когда файл не существует"""
        # Arrange
        cookie_manager.cookies_file = Path("nonexistent.json")
        
        # Act
        result = await cookie_manager._are_cookies_expired("test_cookies")
        
        # Assert
        assert result is True

    @pytest.mark.asyncio
    async def test_are_cookies_expired_invalid_file(self, cookie_manager, tmp_path):
        """Тест проверки срока действия при невалидном файле"""
        # Arrange
        cookie_manager.cookies_file = tmp_path / "invalid.json"
        with open(cookie_manager.cookies_file, 'w') as f:
            f.write("invalid json")
        
        # Act
        result = await cookie_manager._are_cookies_expired("test_cookies")
        
        # Assert
        assert result is True
        cookie_manager.logger.error.assert_called()

    @pytest.mark.asyncio
    @patch('services.fragment.fragment_cookie_manager.SELENIUM_AVAILABLE', False)
    async def test_refresh_cookies_selenium_not_available(self, cookie_manager):
        """Тест обновления cookies когда Selenium недоступен"""
        # Act
        result = await cookie_manager._refresh_cookies()
        
        # Assert
        assert result is None
        cookie_manager.logger.warning.assert_called_once()

    @pytest.mark.asyncio
    @patch('services.fragment.fragment_cookie_manager.SELENIUM_AVAILABLE', True)
    @patch('services.fragment.fragment_cookie_manager.webdriver')
    @patch('services.fragment.fragment_cookie_manager.WebDriverWait')
    async def test_refresh_cookies_success(self, mock_wait, mock_webdriver, cookie_manager):
        """Тест успешного обновления cookies через Selenium"""
        # Arrange
        mock_driver = Mock()
        mock_driver.get_cookies.return_value = [
            {'name': 'test_cookie', 'value': 'test_value'},
            {'name': 'session', 'value': 'session_id'}
        ]
        
        # Мокаем Remote driver для успешного подключения
        mock_webdriver.Remote.return_value = mock_driver
        mock_webdriver.Chrome.return_value = mock_driver
        
        # Мокаем WebDriverWait
        mock_wait_instance = Mock()
        mock_wait.return_value = mock_wait_instance
        
        # Act
        result = await cookie_manager._refresh_cookies()
        
        # Assert
        assert result == "test_cookie=test_value; session=session_id"
        mock_driver.get.assert_called_once_with("https://fragment.com")
        mock_driver.quit.assert_called_once()

    @pytest.mark.asyncio
    @patch('services.fragment.fragment_cookie_manager.SELENIUM_AVAILABLE', True)
    @patch('services.fragment.fragment_cookie_manager.webdriver')
    async def test_refresh_cookies_driver_creation_failed(self, mock_webdriver, cookie_manager):
        """Тест обновления cookies когда не удалось создать драйвер"""
        # Arrange
        # Оба драйвера (Remote и Chrome) должны падать
        mock_webdriver.Remote.side_effect = Exception("Remote driver failed")
        mock_webdriver.Chrome.side_effect = Exception("Driver creation failed")
        
        # Act
        result = await cookie_manager._refresh_cookies()
        
        # Assert
        assert result is None
        # Ожидаем два вызова error: Remote driver и Chrome fallback
        assert cookie_manager.logger.error.call_count == 2

    @pytest.mark.asyncio
    @patch('services.fragment.fragment_cookie_manager.SELENIUM_AVAILABLE', True)
    @patch('services.fragment.fragment_cookie_manager.webdriver')
    async def test_refresh_cookies_timeout_exception(self, mock_webdriver, cookie_manager):
        """Тест обновления cookies при таймауте загрузки страницы"""
        # Arrange
        mock_driver = Mock()
        mock_driver.get.side_effect = Exception("Timeout")
        
        # Remote должен упасть, и нет fallback к Chrome (CHROMEDRIVER_PY_AVAILABLE = False по умолчанию)
        mock_webdriver.Remote.side_effect = Exception("Remote failed")
        
        # Act
        result = await cookie_manager._refresh_cookies()
        
        # Assert
        assert result is None
        # Проверяем что Remote был вызван и упал
        mock_webdriver.Remote.assert_called_once()
        # Проверяем логирование ошибки
        assert cookie_manager.logger.error.call_count >= 1
        # В данном сценарии driver не создается, поэтому quit не вызывается

    @pytest.mark.asyncio
    async def test_validate_cookies_success(self, cookie_manager, mock_fragment_service):
        """Тест успешной валидации cookies"""
        # Arrange
        test_cookies = "valid_cookies_string"
        
        # Act
        result = await cookie_manager.validate_cookies(test_cookies)
        
        # Assert
        assert result is True
        # Проверяем что оригинальные cookies были восстановлены
        assert mock_fragment_service.fragment_cookies == "original_cookies"
        mock_fragment_service.get_user_info.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_cookies_failure(self, cookie_manager, mock_fragment_service):
        """Тест неудачной валидации cookies"""
        # Arrange
        test_cookies = "invalid_cookies_string"
        original_cookies = mock_fragment_service.fragment_cookies
        mock_fragment_service.get_user_info = AsyncMock(side_effect=Exception("API error"))
        
        # Act
        result = await cookie_manager.validate_cookies(test_cookies)
        
        # Assert
        assert result is False
        # Проверяем что оригинальные cookies были восстановлены
        assert mock_fragment_service.fragment_cookies == original_cookies
        mock_fragment_service.get_user_info.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_cookies_exception_handling(self, cookie_manager, mock_fragment_service):
        """Тест обработки исключений при валидации cookies"""
        # Arrange
        test_cookies = "test_cookies"
        # Создаем ситуацию где восстановление оригинальных cookies тоже падает
        original_cookies = mock_fragment_service.fragment_cookies
        def side_effect(*args, **kwargs):
            mock_fragment_service.fragment_cookies = "corrupted"
            raise Exception("Validation error")
        mock_fragment_service.get_user_info = AsyncMock(side_effect=side_effect)
        
        # Act
        result = await cookie_manager.validate_cookies(test_cookies)
        
        # Assert
        assert result is False
        cookie_manager.logger.error.assert_called_once()
        mock_fragment_service.get_user_info.assert_called_once()


class TestInitializeFragmentCookies:
    """Тесты для функции инициализации Fragment cookies"""
    
    @pytest.fixture
    def mock_fragment_service(self):
        """Мок FragmentService для тестов инициализации"""
        service = Mock(spec=FragmentService)
        service.fragment_cookies = None
        return service
    
    @pytest.mark.asyncio
    @patch('services.fragment.fragment_cookie_manager.os.getenv')
    async def test_initialize_fragment_cookies_disabled(self, mock_getenv, mock_fragment_service):
        """Тест инициализации когда автоматическое обновление отключено"""
        # Arrange
        mock_getenv.return_value = "false"
        
        # Act
        await initialize_fragment_cookies(mock_fragment_service)
        
        # Assert
        assert mock_fragment_service.fragment_cookies is None

    @pytest.mark.asyncio
    @patch('services.fragment.fragment_cookie_manager.os.getenv')
    @patch('services.fragment.fragment_cookie_manager.FragmentCookieManager')
    async def test_initialize_fragment_cookies_success(self, mock_manager_class, mock_getenv, mock_fragment_service):
        """Тест успешной инициализации cookies"""
        # Arrange
        mock_getenv.side_effect = lambda key, default=None: "true" if key == "FRAGMENT_AUTO_COOKIE_REFRESH" else default
        
        mock_manager = Mock()
        mock_manager.get_fragment_cookies = AsyncMock(return_value="fresh_cookies")
        mock_manager_class.return_value = mock_manager
        
        # Act
        await initialize_fragment_cookies(mock_fragment_service)
        
        # Assert
        assert mock_fragment_service.fragment_cookies == "fresh_cookies"
        mock_manager.get_fragment_cookies.assert_called_once()

    @pytest.mark.asyncio
    @patch('services.fragment.fragment_cookie_manager.os.getenv')
    @patch('services.fragment.fragment_cookie_manager.FragmentCookieManager')
    async def test_initialize_fragment_cookies_failed(self, mock_manager_class, mock_getenv, mock_fragment_service):
        """Тест инициализации когда не удалось получить cookies"""
        # Arrange
        mock_getenv.side_effect = lambda key, default=None: "true" if key == "FRAGMENT_AUTO_COOKIE_REFRESH" else default
        
        mock_manager = Mock()
        mock_manager.get_fragment_cookies = AsyncMock(return_value=None)
        mock_manager_class.return_value = mock_manager
        
        # Act
        await initialize_fragment_cookies(mock_fragment_service)
        
        # Assert
        assert mock_fragment_service.fragment_cookies is None

    @pytest.mark.asyncio
    @patch('services.fragment.fragment_cookie_manager.os.getenv')
    @patch('services.fragment.fragment_cookie_manager.FragmentCookieManager')
    async def test_initialize_fragment_cookies_exception(self, mock_manager_class, mock_getenv, mock_fragment_service):
        """Тест обработки исключений при инициализации"""
        # Arrange
        mock_getenv.side_effect = lambda key, default=None: "true" if key == "FRAGMENT_AUTO_COOKIE_REFRESH" else default
        
        mock_manager = Mock()
        mock_manager.get_fragment_cookies = AsyncMock(side_effect=Exception("Initialization error"))
        mock_manager_class.return_value = mock_manager
        
        # Act
        await initialize_fragment_cookies(mock_fragment_service)
        
        # Assert
        assert mock_fragment_service.fragment_cookies is None


# Дополнительные интеграционные тесты
class TestFragmentCookieManagerIntegration:
    """Интеграционные тесты для проверки взаимодействия компонентов"""
    
    @pytest.mark.asyncio
    async def test_full_flow_with_mocked_dependencies(self, tmp_path):
        """Тест полного цикла работы с моками всех зависимостей"""
        # Arrange
        mock_service = Mock(spec=FragmentService)
        mock_service.get_user_info = AsyncMock(return_value={"status": "success"})
        
        manager = FragmentCookieManager(mock_service)
        manager.cookies_file = tmp_path / "integration_test.json"
        manager.logger = Mock()
        
        # Создаем моки для приватных методов
        mock_load = AsyncMock(return_value=None)
        mock_refresh = AsyncMock(return_value="integration_cookies") 
        mock_save = AsyncMock()
        
        # Заменяем методы моками
        manager._load_cookies_from_file = mock_load
        manager._refresh_cookies = mock_refresh
        manager._save_cookies_to_file = mock_save
        
        # Act
        result = await manager.get_fragment_cookies()
        
        # Assert
        assert result == "integration_cookies"
        mock_load.assert_called_once()
        mock_refresh.assert_called_once()
        mock_save.assert_called_once_with("integration_cookies")
