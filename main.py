"""
Основной файл приложения - рефакторинг по SOLID принципам
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.methods import DeleteWebhook

from config.settings import settings
from services.webhooks import app as webhook_app
from repositories.user_repository import UserRepository
from repositories.balance_repository import BalanceRepository
from services.payment import PaymentService
from services.payment import BalanceService
from services.payment import StarPurchaseService
from services.webhooks import WebhookHandler
from services.cache import UserCache
from services.cache import PaymentCache
from services.cache import SessionCache
from services.cache import RateLimitCache
from services.fragment import FragmentService
from services.infrastructure import FragmentCookieManager
from handlers.message_handler import MessageHandler


async def init_database():
    """Инициализация базы данных"""
    user_repository = UserRepository(database_url=settings.database_url)
    await user_repository.create_tables()


async def init_cache_services():
    """Инициализация сервисов кэширования с использованием унифицированного менеджера"""
    cache_services = {}

    # Инициализация Redis кэша с использованием унифицированной функции
    if settings.redis_url or (settings.is_redis_cluster and settings.redis_cluster_nodes):
        try:
            from core.cache.cache_manager import initialize_cache_services

            # Используем унифицированную функцию для инициализации Redis
            cache_services = await initialize_cache_services(
                redis_url=settings.redis_url,
                redis_cluster_nodes=settings.redis_cluster_nodes,
                redis_password=settings.redis_password,
                is_redis_cluster=settings.is_redis_cluster,
                decode_responses=True,  # Устанавливаем decode_responses=True для согласованности
                socket_timeout=settings.redis_socket_timeout,
                socket_connect_timeout=settings.redis_socket_connect_timeout,
                retry_on_timeout=settings.redis_retry_on_timeout,
                max_connections=settings.redis_max_connections,
                health_check_interval=settings.redis_health_check_interval
            )

            logging.info("Cache services initialized successfully using unified manager")

        except Exception as e:
            logging.error(f"Failed to initialize cache services: {e}")
            # Продолжаем работу без кеша
            logging.warning("Application will continue without cache functionality")

    return cache_services


async def run_webhook_server():
    """Запуск FastAPI сервера для обработки webhook"""
    import uvicorn
    from services.webhooks import app as webhook_app
    from config.settings import settings

    config = uvicorn.Config(
        app=webhook_app,
        host=settings.webhook_host,
        port=settings.webhook_port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
    server = uvicorn.Server(config)
    await server.serve()


async def run_telegram_bot(bot, dp):
    """Запуск Telegram бота"""
    await bot(DeleteWebhook(drop_pending_updates=True))
    logging.info("Starting Telegram bot polling...")
    await dp.start_polling(bot)


async def main():
    """Основная функция приложения"""
    # Настройка логирования
    logging.basicConfig(
        level=logging.DEBUG,  # Изменено на DEBUG для получения всех сообщений
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logging.info("Starting application initialization...")
    logging.info(f"Production domain configured: {settings.production_domain}")
    logging.info(f"Webhook domain configured: {settings.webhook_domain}")
    logging.info(f"Webhook host: {settings.webhook_host}:{settings.webhook_port}")
    logging.info(f"Environment: {settings.environment}")
    logging.info(f"Debug mode: {settings.debug}")

    # Предварительная проверка Fragment API настроек
    try:
        from services.fragment import FragmentService

        # Проверяем формат seed phrase
        fragment_service = FragmentService()
        if not fragment_service._validate_seed_phrase():
            logging.error("Fragment API seed phrase validation failed. Application will continue but Fragment features may not work.")
        else:
            logging.info("Fragment API seed phrase validation passed")

        # Инициализация cookies если включена автоматическая настройка
        from services.infrastructure import initialize_fragment_cookies
        await initialize_fragment_cookies(fragment_service)
        
        ping_result = await fragment_service.ping()
        if ping_result["status"] == "success":
            logging.info("Fragment API is available")
        else:
            logging.warning(f"Fragment API is not available: {ping_result.get('error', 'Unknown error')}")
    except Exception as e:
        logging.error(f"Error initializing Fragment API: {e}")
        logging.warning("Fragment API features may not be available")

    # Инициализация сервисов кэширования
    cache_services = await init_cache_services()

    # Извлечение кеш сервисов
    user_cache = cache_services.get('user_cache')
    payment_cache = cache_services.get('payment_cache')
    session_cache = cache_services.get('session_cache')
    rate_limit_cache = cache_services.get('rate_limit_cache')

    # Инициализация компонентов
    user_repository = UserRepository(
        database_url=settings.database_url,
        user_cache=user_cache
    )

    balance_repository = BalanceRepository(user_repository.async_session)

    payment_service = PaymentService(
        merchant_uuid=settings.merchant_uuid,
        api_key=settings.api_key,
        payment_cache=payment_cache
    )

    # Инициализация сервисов
    balance_service = BalanceService(
        user_repository=user_repository,
        balance_repository=balance_repository,
        user_cache=user_cache
    )

    star_purchase_service = StarPurchaseService(
        user_repository=user_repository,
        balance_repository=balance_repository,
        payment_service=payment_service,
        user_cache=user_cache,
        payment_cache=payment_cache
    )

    # Инициализация обработчиков
    message_handler = MessageHandler(
        user_repository=user_repository,
        payment_service=payment_service,
        balance_service=balance_service,
        star_purchase_service=star_purchase_service,
        session_cache=session_cache,
        rate_limit_cache=rate_limit_cache,
        payment_cache=payment_cache
    )

    # Инициализация вебхук обработчика
    webhook_handler = WebhookHandler(
        star_purchase_service=star_purchase_service,
        user_cache=user_cache,
        payment_cache=payment_cache
    )

    # Инициализация бота и диспетчера
    bot = Bot(token=settings.telegram_token)
    dp = Dispatcher()

    # Регистрация обработчиков
    message_handler.register_handlers(dp)

    # Инициализация базы данных
    await init_database()
    logging.info("Database initialized successfully")

    # Запуск сервисов параллельно
    if settings.balance_service_enabled and settings.webhook_enabled:
        logging.info(f"Starting webhook server on {settings.webhook_host}:{settings.webhook_port}")
        logging.info(f"Webhook endpoint: https://{settings.webhook_domain}/webhook/heleket")
        logging.info(f"Health check endpoint: https://{settings.webhook_domain}/health")
        logging.info(f"Detailed health check: https://{settings.webhook_domain}/health/detailed")
        logging.info(f"Metrics endpoint: https://{settings.webhook_domain}/metrics")

        # Запуск webhook сервера и Telegram бота параллельно
        await asyncio.gather(
            run_webhook_server(),
            run_telegram_bot(bot, dp)
        )
    else:
        # Запуск только Telegram бота
        await bot(DeleteWebhook(drop_pending_updates=True))
        logging.info("Starting Telegram bot polling...")
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
