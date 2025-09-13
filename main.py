"""
Основной файл приложения - рефакторинг по SOLID принципам
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.methods import DeleteWebhook

from config.settings import settings
from services.webhook.webhook_app import app as webhook_app
from repositories.user_repository import UserRepository
from repositories.balance_repository import BalanceRepository
from services.payment.payment_service import PaymentService
from services.balance.balance_service import BalanceService
from services.payment.star_purchase_service import StarPurchaseService
from services.webhook.webhook_handler import WebhookHandler
from services.cache.user_cache import UserCache
from services.cache.payment_cache import PaymentCache
from services.cache.session_cache import SessionCache
from services.cache.rate_limit_cache import RateLimitCache
from handlers.message_handler import MessageHandler


async def init_database():
    """Инициализация базы данных"""
    try:
        user_repository = UserRepository(database_url=settings.database_url)
        await user_repository.create_tables()
        logging.info("Database initialized successfully")
    except Exception as e:
        logging.error(f"Failed to initialize database: {e}")
        # Graceful degradation - продолжаем работу без базы


async def init_cache_services():
    """Инициализация сервисов кэширования"""
    cache_services = {}

    # Инициализация Redis кэша
    if settings.redis_url:
        import redis.asyncio as redis
        from redis.cluster import RedisCluster, ClusterNode
        from typing import Union
        from services.cache.user_cache import UserCache
        from services.cache.payment_cache import PaymentCache
        from services.cache.session_cache import SessionCache
        from services.cache.rate_limit_cache import RateLimitCache
        import time

        async def connect_redis_with_retry(max_retries=10, base_delay=2):
            """Подключение к Redis с retry логикой и экспоненциальной задержкой"""
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    logging.info(f"Redis connection attempt {attempt + 1}/{max_retries}")
                    
                    # Создаем Redis клиент с поддержкой кластера
                    if settings.is_redis_cluster:
                        logging.info(f"Creating RedisCluster with nodes: {settings.redis_cluster_nodes}")

                        # Создаем корректные узлы кластера
                        cluster_nodes = [
                            ClusterNode(host=host.split(":")[0], port=int(host.split(":")[1]))
                            for host in settings.redis_cluster_nodes.split(",")
                        ]

                        redis_client = RedisCluster(
                            startup_nodes=cluster_nodes,
                            password=settings.redis_password,
                            decode_responses=True,
                            skip_full_coverage_check=True,
                            health_check_interval=30,
                            socket_connect_timeout=5,
                            socket_timeout=5
                        )
                    else:
                        logging.info(f"Creating Redis client from URL: {settings.redis_url}")
                        redis_client = redis.from_url(settings.redis_url, decode_responses=True)

                    # Проверка подключения
                    logging.info(f"Redis client type: {type(redis_client)}")

                    if hasattr(redis_client, 'ping'):
                        if asyncio.iscoroutinefunction(redis_client.ping):
                            logging.info("Using async ping method")
                            await redis_client.ping()
                            logging.info("Redis async ping successful")
                        else:
                            logging.info("Using sync ping method")
                            result = redis_client.ping()
                            logging.info(f"Redis sync ping result: {result}")
                    else:
                        logging.warning("Redis client does not have ping method")

                    # Если дошли до этой точки, подключение успешно
                    logging.info(f"Redis connection successful on attempt {attempt + 1}")
                    return redis_client

                except Exception as e:
                    last_exception = e
                    delay = base_delay * (2 ** attempt)  # Экспоненциальная задержка
                    logging.warning(f"Redis connection attempt {attempt + 1} failed: {e}")
                    
                    if attempt < max_retries - 1:
                        logging.info(f"Retrying in {delay} seconds...")
                        await asyncio.sleep(delay)
                    else:
                        logging.error(f"All Redis connection attempts failed. Last error: {e}")
                        
            raise last_exception

        try:
            # Попытка подключения с retry логикой
            redis_client = await connect_redis_with_retry()

            # Создаем кеш сервисы
            cache_services['user_cache'] = UserCache(redis_client)
            cache_services['payment_cache'] = PaymentCache(redis_client)
            cache_services['session_cache'] = SessionCache(redis_client)
            cache_services['rate_limit_cache'] = RateLimitCache(redis_client)

            logging.info("Cache services initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize cache services after all retries: {e}")
            logging.info("Continuing without Redis cache services")
            # Продолжаем работу без кеша

    return cache_services


async def run_webhook_server():
    """Запуск FastAPI сервера для обработки webhook"""
    import uvicorn
    from services.webhook.webhook_app import app as webhook_app
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
        from services.fragment.fragment_service import FragmentService
        
        # Проверяем формат seed phrase
        fragment_service = FragmentService()
        if not fragment_service._validate_seed_phrase():
            logging.error("Fragment API seed phrase validation failed. Application will continue but Fragment features may not work.")
        else:
            logging.info("Fragment API seed phrase validation passed")
            
        # Инициализация cookies если включена автоматическая настройка
        from services.fragment.fragment_cookie_manager import initialize_fragment_cookies
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
        )
    else:
        # Запуск только Telegram бота
        await bot(DeleteWebhook(drop_pending_updates=True))
        logging.info("Starting Telegram bot polling...")
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
