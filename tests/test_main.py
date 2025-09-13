"""
Unit-тесты для основного файла приложения main.py
Тестируем инициализацию сервисов и основные функции
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from aiogram import Bot, Dispatcher
from aiogram.methods import DeleteWebhook

from main import init_database, init_cache_services, main
from config.settings import settings
from repositories.user_repository import UserRepository
from repositories.balance_repository import BalanceRepository
from services.payment.payment_service import PaymentService
from services.balance.balance_service import BalanceService
from services.payment.star_purchase_service import StarPurchaseService
from services.cache.user_cache import UserCache
from services.cache.payment_cache import PaymentCache
from services.cache.session_cache import SessionCache
from services.cache.rate_limit_cache import RateLimitCache


class TestMainApp:
    """Тесты для основного приложения"""
    
    @pytest.fixture
    def mock_settings(self):
        """Фикстура для мока настроек"""
        with patch('main.settings') as mock_settings:
            mock_settings.database_url = "sqlite+aiosqlite:///:memory:"
            mock_settings.redis_url = "redis://localhost:6379"
            mock_settings.is_redis_cluster = False
            mock_settings.redis_cluster_nodes = "localhost:6379"
            mock_settings.redis_password = None
            mock_settings.cache_ttl_user = 1800
            mock_settings.redis_local_cache_enabled = True
            mock_settings.redis_local_cache_ttl = 300
            mock_settings.telegram_token = "test_token"
            mock_settings.balance_service_enabled = False
            mock_settings.webhook_enabled = False
            mock_settings.webhook_host = "localhost"
            mock_settings.webhook_port = 8000
            mock_settings.debug = True
            mock_settings.log_level = "INFO"
            mock_settings.production_domain = "test.example.com"
            mock_settings.environment = "test"
            mock_settings.merchant_uuid = "test_merchant"
            mock_settings.api_key = "test_api_key"
            yield mock_settings

    @pytest.mark.asyncio
    async def test_init_database_success(self):
        """Тест успешной инициализации базы данных"""
        with patch('main.UserRepository') as mock_repo:
            mock_instance = Mock()
            mock_instance.create_tables = AsyncMock()
            mock_repo.return_value = mock_instance
            
            await init_database()
            
            mock_repo.assert_called_once_with(database_url=settings.database_url)
            mock_instance.create_tables.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_database_error(self):
        """Тест ошибки инициализации базы данных"""
        with patch('main.UserRepository') as mock_repo, \
             patch('main.logging') as mock_logging:
            mock_instance = Mock()
            mock_instance.create_tables = AsyncMock(side_effect=Exception("DB error"))
            mock_repo.return_value = mock_instance
            
            # Должен завершиться без исключения (graceful degradation)
            await init_database()
            
            # Проверяем, что ошибка была залогирована
            mock_logging.error.assert_called()

    @pytest.mark.asyncio
    async def test_init_cache_services_with_redis(self, mock_settings):
        """Тест инициализации кэш-сервисов с Redis"""
        with patch('redis.asyncio') as mock_redis, \
             patch('redis.cluster.RedisCluster') as mock_redis_cluster:
            
            # Мок обычного Redis клиента
            mock_client = AsyncMock()
            mock_redis.from_url.return_value = mock_client
            mock_client.ping = AsyncMock(return_value=True)
            
            cache_services = await init_cache_services()
            
            assert 'user_cache' in cache_services
            assert 'payment_cache' in cache_services
            assert 'session_cache' in cache_services
            assert 'rate_limit_cache' in cache_services
            assert isinstance(cache_services['user_cache'], UserCache)

    @pytest.mark.asyncio
    async def test_init_cache_services_redis_cluster(self, mock_settings):
        """Тест инициализации кэш-сервисов с Redis кластером"""
        mock_settings.is_redis_cluster = True
        
        with patch('redis.cluster.RedisCluster') as mock_redis_cluster, \
             patch('redis.cluster.ClusterNode') as mock_cluster_node:
            
            # Мок Redis кластера
            mock_client = AsyncMock()
            mock_redis_cluster.return_value = mock_client
            mock_client.ping = AsyncMock(return_value=True)
            
            cache_services = await init_cache_services()
            
            assert 'user_cache' in cache_services
            mock_redis_cluster.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_cache_services_redis_error(self, mock_settings):
        """Тест инициализации кэш-сервисов с ошибкой Redis"""
        with patch('redis.asyncio.from_url') as mock_from_url, \
             patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            mock_client = AsyncMock()
            mock_from_url.return_value = mock_client
            mock_client.ping = AsyncMock(side_effect=Exception("Redis error"))
            
            # Должен вернуть пустой словарь при ошибке
            cache_services = await init_cache_services()
            
            assert cache_services == {}

    @pytest.mark.asyncio
    async def test_init_cache_services_no_redis(self, mock_settings):
        """Тест инициализации кэш-сервисов без Redis"""
        mock_settings.redis_url = None
        
        cache_services = await init_cache_services()
        
        # Должен вернуть пустой словарь при отсутствии Redis
        assert cache_services == {}

    @pytest.mark.asyncio
    @patch('main.logging')
    @patch('main.asyncio')
    @patch('main.UserRepository')
    @patch('main.Bot')
    @patch('main.Dispatcher')
    async def test_main_function_basic(self, mock_dp, mock_bot, mock_user_repo, mock_asyncio, mock_logging, mock_settings):
        """Тест основной функции приложения (базовый сценарий)"""
        mock_settings.balance_service_enabled = False
        
        # Моки для зависимостей
        mock_user_instance = Mock()
        mock_user_repo.return_value = mock_user_instance
        
        mock_bot_instance = AsyncMock()
        mock_bot.return_value = mock_bot_instance
        
        # Создаем правильный async mock для dp.start_polling
        mock_dp_instance = Mock()
        mock_dp_instance.start_polling = AsyncMock()
        mock_dp.return_value = mock_dp_instance
        
        # Мок для asyncio.run
        mock_asyncio.run = AsyncMock()
        
        # Вызываем main функцию
        await main()
        
        # Проверяем, что логирование было настроено
        mock_logging.basicConfig.assert_called_once()
        # UserRepository вызывается дважды: в init_database и в main
        assert mock_user_repo.call_count == 2
        mock_bot.assert_called_once_with(token=mock_settings.telegram_token)
        mock_dp_instance.start_polling.assert_called_once()

    @pytest.mark.asyncio
    @patch('main.Bot')
    @patch('main.Dispatcher')
    @patch('main.init_database')
    @patch('main.init_cache_services')
    @patch('main.UserRepository')
    async def test_main_function_components_initialization(self, mock_user_repo, mock_init_cache, mock_init_db,
                                                         mock_dp, mock_bot, mock_settings):
        """Тест инициализации компонентов в main функции"""
        mock_settings.balance_service_enabled = False
        
        # Настраиваем моки
        mock_user_instance = Mock()
        mock_user_repo.return_value = mock_user_instance
        mock_init_db.return_value = None
        mock_init_cache.return_value = {}
        mock_bot_instance = AsyncMock()
        mock_bot.return_value = mock_bot_instance
        mock_dp_instance = Mock()
        mock_dp_instance.start_polling = AsyncMock()
        mock_dp.return_value = mock_dp_instance
        
        # Мок для asyncio.run
        with patch('main.asyncio.run', AsyncMock()):
            await main()
            
            # Проверяем инициализацию компонентов
            mock_user_repo.assert_called_once_with(
                database_url=mock_settings.database_url,
                user_cache=None
            )
            mock_init_db.assert_called_once()
            mock_init_cache.assert_called_once()
            mock_bot.assert_called_once_with(token=mock_settings.telegram_token)
            mock_dp.assert_called_once()

    @pytest.mark.asyncio
    @patch('main.UserRepository')
    @patch('main.BalanceRepository')
    @patch('main.PaymentService')
    @patch('main.BalanceService')
    @patch('main.StarPurchaseService')
    async def test_service_initialization_logic(self, mock_star_service, mock_balance_service,
                                               mock_payment_service, mock_balance_repo,
                                               mock_user_repo, mock_settings):
        """Тест логики инициализации сервисов"""
        # Создаем mock экземпляры
        mock_user_instance = Mock()
        mock_user_repo.return_value = mock_user_instance
        mock_balance_repo_instance = Mock()
        mock_balance_repo.return_value = mock_balance_repo_instance
        mock_payment_instance = Mock()
        mock_payment_service.return_value = mock_payment_instance
        mock_balance_instance = Mock()
        mock_balance_service.return_value = mock_balance_instance
        mock_star_instance = Mock()
        mock_star_service.return_value = mock_star_instance
        
        # Проверяем конструкторы
        user_repo = UserRepository(database_url=settings.database_url)
        balance_repo = BalanceRepository(user_repo.async_session)
        payment_service = PaymentService(
            merchant_uuid=settings.merchant_uuid,
            api_key=settings.api_key,
            payment_cache=None
        )
        balance_service = BalanceService(
            user_repository=user_repo,
            balance_repository=balance_repo,
            user_cache=None
        )
        star_service = StarPurchaseService(
            user_repository=user_repo,
            balance_repository=balance_repo,
            payment_service=payment_service,
            user_cache=None,
            payment_cache=None
        )
        
        # Проверяем, что объекты созданы
        assert user_repo is not None
        assert balance_repo is not None
        assert payment_service is not None
        assert balance_service is not None
        assert star_service is not None

    @pytest.mark.asyncio
    async def test_settings_validation(self, mock_settings):
        """Тест валидации настроек приложения"""
        # Проверяем обязательные настройки
        assert hasattr(settings, 'telegram_token')
        assert hasattr(settings, 'database_url')
        assert hasattr(settings, 'merchant_uuid')
        assert hasattr(settings, 'api_key')
        
        # Проверяем типы настроек
        assert isinstance(settings.telegram_token, str)
        assert isinstance(settings.database_url, str)
        assert isinstance(settings.merchant_uuid, str)
        assert isinstance(settings.api_key, str)

    @pytest.mark.asyncio
    async def test_webhook_server_initialization(self, mock_settings):
        """Тест инициализации webhook сервера"""
        # Мокаем импорт uvicorn внутри функции run_webhook_server
        
        from main import run_webhook_server
        
        # Создаем мок для uvicorn
        mock_uvicorn = Mock()
        mock_config = Mock()
        mock_uvicorn.Config.return_value = mock_config
        mock_server = AsyncMock()
        mock_uvicorn.Server.return_value = mock_server
        
        # Мокаем builtins.__import__ для перехвата импорта uvicorn
        original_import = __import__
        
        def mock_import(name, *args, **kwargs):
            if name == 'uvicorn':
                return mock_uvicorn
            return original_import(name, *args, **kwargs)
        
        with patch('builtins.__import__', side_effect=mock_import):
            await run_webhook_server()
            
        mock_uvicorn.Config.assert_called_once()
        mock_uvicorn.Server.assert_called_once_with(mock_config)
        mock_server.serve.assert_called_once()

    @pytest.mark.asyncio
    @patch('main.Bot')
    @patch('main.Dispatcher')
    async def test_telegram_bot_initialization(self, mock_dp, mock_bot, mock_settings):
        """Тест инициализации Telegram бота"""
        from main import run_telegram_bot
        
        mock_bot_instance = AsyncMock()
        mock_bot.return_value = mock_bot_instance
        mock_dp_instance = Mock()
        mock_dp_instance.start_polling = AsyncMock()
        mock_dp.return_value = mock_dp_instance
        
        await run_telegram_bot(mock_bot_instance, mock_dp_instance)
        
        mock_bot_instance.assert_called_once_with(DeleteWebhook(drop_pending_updates=True))
        mock_dp_instance.start_polling.assert_called_once_with(mock_bot_instance)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])