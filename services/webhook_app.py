"""
FastAPI приложение для обработки webhook от платежной системы Heleket
"""
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from services.webhook_handler import WebhookHandler
from repositories.user_repository import UserRepository
from repositories.balance_repository import BalanceRepository
from services.payment_service import PaymentService
from services.star_purchase_service import StarPurchaseService
from services.user_cache import UserCache
from services.payment_cache import PaymentCache
from config.settings import settings

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создание FastAPI приложения
app = FastAPI(
    title="Telegram Bot Webhook Handler",
    description="Обработчик вебхуков для платежной системы Heleket",
    version="1.0.0"
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Глобальные переменные для сервисов
user_repository = None
balance_repository = None
payment_service = None
user_cache = None
payment_cache = None
webhook_handler = None

@app.on_event("startup")
async def startup_event():
    """Инициализация сервисов при запуске приложения"""
    global user_repository, balance_repository, payment_service, user_cache, payment_cache, webhook_handler

    logger.info("Initializing webhook handler services...")

    try:
        # Инициализация репозиториев
        user_repository = UserRepository(database_url=settings.database_url)
        await user_repository.create_tables()

        # Инициализация кеша Redis
        if settings.redis_url:
            try:
                import redis.asyncio as redis
                from redis.cluster import RedisCluster
                from typing import Any

                # Создаем Redis клиент с поддержкой кластера
                if settings.is_redis_cluster:
                    startup_nodes = [
                        {"host": host.split(":")[0], "port": int(host.split(":")[1])}
                        for host in settings.redis_cluster_nodes.split(",")
                    ]
                    redis_client = RedisCluster(
                        startup_nodes=startup_nodes,
                        password=settings.redis_password,
                        decode_responses=False,
                        skip_full_coverage_check=True
                    )
                else:
                    redis_client = redis.from_url(settings.redis_url, decode_responses=False)

                await redis_client.ping()

                user_cache = UserCache(redis_client)
                payment_cache = PaymentCache(redis_client)
                logger.info("Redis cache initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Redis cache: {e}")

        # Инициализация сервисов
        balance_repository = BalanceRepository(user_repository.async_session)
        payment_service = PaymentService(
            merchant_uuid=settings.merchant_uuid,
            api_key=settings.api_key
        )

        # Создание сервиса покупки звезд
        star_purchase_service = StarPurchaseService(
            user_repository=user_repository,
            balance_repository=balance_repository,
            payment_service=payment_service,
            user_cache=user_cache,
            payment_cache=payment_cache
        )

        # Создание обработчика вебхуков
        webhook_handler = WebhookHandler(
            star_purchase_service=star_purchase_service,
            user_cache=user_cache,
            payment_cache=payment_cache
        )

        logger.info("Webhook handler services initialized successfully")

    except Exception as e:
        logger.error(f"Error during webhook handler startup: {e}")
        raise

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "webhook-handler"}

@app.post("/webhook/heleket")
async def handle_heleket_webhook(request: Request):
    """Обработка вебхука от платежной системы Heleket"""
    try:
        if not webhook_handler:
            raise HTTPException(status_code=500, detail="Webhook handler not initialized")

        # Получаем тело запроса
        body = await request.body()

        # Получаем заголовки
        headers = dict(request.headers)

        logger.info(f"Received webhook request from {request.client.host}")

        # Обработка вебхука
        success = await webhook_handler.handle_payment_webhook(request)

        if success:
            return JSONResponse({"status": "ok"}, status_code=200)
        else:
            return JSONResponse(
                {"status": "error", "message": "Processing failed"},
                status_code=400
            )

    except HTTPException as e:
        logger.error(f"HTTP error in webhook: {e}")
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in webhook: {e}")
        return JSONResponse(
            {"status": "error", "message": "Internal server error"},
            status_code=500
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "services.webhook_app:app",
        host=settings.webhook_host,
        port=settings.webhook_port,
        reload=settings.debug
    )
