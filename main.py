"""
Основной файл приложения - рефакторинг по SOLID принципам
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.methods import DeleteWebhook

from config.settings import settings
from services.webhook_app import app as webhook_app
from repositories.user_repository import UserRepository
from repositories.balance_repository import BalanceRepository
from services.payment_service import PaymentService
from services.balance_service import BalanceService
from services.star_purchase_service import StarPurchaseService
from services.webhook_handler import WebhookHandler
from services.user_cache import UserCache
from services.payment_cache import PaymentCache
from services.session_cache import SessionCache
from services.rate_limit_cache import RateLimitCache
from handlers.message_handler import MessageHandler


async def init_database():
    """Инициализация базы данных"""
    user_repository = UserRepository(database_url=settings.database_url)
    await user_repository.create_tables()


async def init_cache_services():
    """Инициализация сервисов кэширования"""
    cache_services = {}

    # Инициализация Redis кэша
    if settings.redis_url:
        try:
            import redis.asyncio as redis
            from redis.cluster import RedisCluster
            from typing import Union
            from services.user_cache import UserCache
            from services.payment_cache import PaymentCache
            from services.session_cache import SessionCache
            from services.rate_limit_cache import RateLimitCache

            # Создаем Redis клиент с поддержкой кластера
            if settings.is_redis_cluster:
                startup_nodes = [
                    {"host": host.split(":")[0], "port": int(host.split(":")[1])}
                    for host in settings.redis_cluster_nodes.split(",")
                ]
                logging.info(f"Creating RedisCluster with {len(startup_nodes)} nodes")

                # Используем правильный формат для RedisCluster
                from redis.cluster import RedisCluster
                from redis.cluster import ClusterNode

                # Создаем корректные узлы кластера
                cluster_nodes = [ClusterNode(host=host.split(":")[0], port=int(host.split(":")[1]))
                               for host in settings.redis_cluster_nodes.split(",")]

                redis_client = RedisCluster(
                    startup_nodes=cluster_nodes,
                    password=settings.redis_password,
                    decode_responses=True,  # Изменено на True для согласованности
                    skip_full_coverage_check=True
                )
            else:
                logging.info(f"Creating Redis client from URL: {settings.redis_url}")
                redis_client = redis.from_url(settings.redis_url, decode_responses=True)  # Изменено на True для согласованности

            # Проверка подключения
            logging.info(f"Redis client type: {type(redis_client)}")

            if hasattr(redis_client, 'ping'):
                if asyncio.iscoroutinefunction(redis_client.ping):
                    logging.info("Using async ping method")
                    try:
                        await redis_client.ping()
                        logging.info("Redis ping successful")
                    except Exception as e:
                        logging.error(f"Redis ping failed: {e}")
                        raise
                else:
                    logging.info("Using sync ping method")
                    try:
                        result = redis_client.ping()
                        logging.info(f"Redis ping result: {result}")
                    except Exception as e:
                        logging.error(f"Redis ping failed: {e}")
                        raise
            else:
                logging.warning("Redis client does not have ping method")

            # Создаем кеш пользователей
            cache_services['user_cache'] = UserCache(redis_client)

            # Создаем кеш платежей
            cache_services['payment_cache'] = PaymentCache(redis_client)

            # Создаем кеш сессий
            cache_services['session_cache'] = SessionCache(redis_client)

            # Создаем кеш для rate limiting
            cache_services['rate_limit_cache'] = RateLimitCache(redis_client)

            logging.info("Cache services initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize cache services: {e}")
            # Продолжаем работу без кеша

    return cache_services


async def run_webhook_server():
    """Запуск FastAPI сервера для обработки webhook"""
    import uvicorn
    from services.webhook_app import app as webhook_app
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
    logging.info(f"Webhook host: {settings.webhook_host}:{settings.webhook_port}")
    logging.info(f"Environment: {settings.environment}")
    logging.info(f"Debug mode: {settings.debug}")

    # Предварительная проверка Fragment API настроек
    try:
        from services.fragment_service import FragmentService</search>
        
        # Проверяем формат seed phrase
        fragment_service = FragmentService()
        if not fragment_service._validate_seed_phrase():
            logging.error("Fragment API seed phrase validation failed. Application will continue but Fragment features may not work.")
        else:
            logging.info("Fragment API seed phrase validation passed")
            
        # Инициализация cookies если включена автоматическая настройка
        from services.fragment_cookie_manager import initialize_fragment_cookies
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
        logging.info(f"Webhook endpoint: https://{settings.production_domain}/webhook/heleket")
        logging.info(f"Health check endpoint: https://{settings.production_domain}/health")
        logging.info(f"Detailed health check: https://{settings.production_domain}/health/detailed")
        logging.info(f"Metrics endpoint: https://{settings.production_domain}/metrics")

        # Запуск webhook сервера и Telegram бота параллельно
        await asyncio.gather(
            run_webhook_server(),
            run_telegram_bot(bot, dp)
        )</search>
    else:
        # Запуск только Telegram бота
        await bot(DeleteWebhook(drop_pending_updates=True))
        logging.info("Starting Telegram bot polling...")
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
