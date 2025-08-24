"""
Полнофункциональное FastAPI приложение для обработки webhook от платежной системы Heleket
с полной поддержкой домена nekamita.work

Архитектура:
- FastAPI приложение с полным middleware стеком
- CORS, безопасность, rate limiting, метрики
- Интеграция с WebhookHandler и HMAC валидацией
- Расширенное логирование домена
- Prometheus метрики и health checks
- Совместимость с существующей архитектурой проекта
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, Depends, status
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware

from services.webhooks import WebhookHandler
from repositories.user_repository import UserRepository
from repositories.balance_repository import BalanceRepository
from services.payment import PaymentService
from services.payment import StarPurchaseService
from services.cache import UserCache
from services.cache import PaymentCache

from services.infrastructure import HealthService
from services.cache import RateLimitCache
from config.settings import settings

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DomainLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware для расширенного логирования домена nekamita.work"""

    async def dispatch(self, request: Request, call_next):
        start_time = datetime.utcnow()

        # Извлечение информации о домене
        client_host = getattr(request.client, 'host', 'unknown') if request.client else 'unknown'
        headers = dict(request.headers)
        host_header = headers.get('host', 'unknown')
        user_agent = headers.get('user-agent', 'unknown')
        cf_ray = headers.get('cf-ray', 'unknown')  # Cloudflare Ray ID
        cf_connecting_ip = headers.get('cf-connecting-ip', client_host)  # Real IP from Cloudflare

        # Логирование домена с расширенной информацией
        if settings.domain_debug_logging or settings.webhook_domain_logging:
            logger.info(
                "domain_request_received",
                extra={
                    "client_ip": client_host,
                    "cf_real_ip": cf_connecting_ip,
                    "host_header": host_header,
                    "expected_domain": settings.webhook_domain,
                    "user_agent": user_agent,
                    "cf_ray": cf_ray,
                    "method": request.method,
                    "url": str(request.url),
                    "path": request.url.path,
                    "query_params": dict(request.query_params),
                    "timestamp": start_time.isoformat()
                }
            )

        # Проверка домена для webhook endpoint
        if request.url.path.startswith("/webhook/"):
            if host_header != settings.webhook_domain:
                logger.warning(
                    "domain_mismatch_detected",
                    extra={
                        "expected_domain": settings.webhook_domain,
                        "received_host": host_header,
                        "client_ip": client_host,
                        "cf_real_ip": cf_connecting_ip,
                        "path": request.url.path
                    }
                )

        try:
            response = await call_next(request)
            duration = (datetime.utcnow() - start_time).total_seconds()

            # Логирование успешных запросов
            if settings.domain_debug_logging:
                logger.info(
                    "domain_request_completed",
                    extra={
                        "client_ip": client_host,
                        "cf_real_ip": cf_connecting_ip,
                        "host_header": host_header,
                        "status_code": response.status_code,
                        "duration_seconds": round(duration, 4),
                        "path": request.url.path
                    }
                )

            return response

        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()

            logger.error(
                "domain_request_error",
                extra={
                    "client_ip": client_host,
                    "cf_real_ip": cf_connecting_ip,
                    "host_header": host_header,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_seconds": round(duration, 4),
                    "path": request.url.path
                },
                exc_info=True
            )
            raise


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware для добавления security headers"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"

        # Webhook specific headers
        if request.url.path.startswith("/webhook/"):
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'

        return response


class SimpleRateLimitMiddleware(BaseHTTPMiddleware):
    """Простое rate limiting middleware для webhook endpoints"""

    def __init__(self, app):
        super().__init__(app)
        self._requests = {}

    async def dispatch(self, request: Request, call_next):
        # Rate limiting только для webhook endpoints
        if request.url.path.startswith("/webhook/"):
            client_ip = (
                request.headers.get('cf-connecting-ip') or
                getattr(request.client, 'host', 'unknown') if request.client else 'unknown'
            )

            current_time = datetime.utcnow()
            window_start = current_time - timedelta(minutes=1)

            # Очистка старых записей
            if client_ip in self._requests:
                self._requests[client_ip] = [
                    req_time for req_time in self._requests[client_ip]
                    if req_time > window_start
                ]

            # Проверка лимита (10 запросов в минуту)
            if client_ip not in self._requests:
                self._requests[client_ip] = []

            if len(self._requests[client_ip]) >= 10:
                logger.warning(
                    "rate_limit_exceeded",
                    extra={
                        "client_ip": client_ip,
                        "endpoint": request.url.path
                    }
                )

                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Rate limit exceeded",
                        "retry_after": 60,
                        "message": "Слишком много запросов. Попробуйте через минуту.",
                        "domain": settings.webhook_domain
                    }
                )

            # Добавление записи о запросе
            self._requests[client_ip].append(current_time)

        return await call_next(request)


# Глобальные переменные для сервисов
services = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Startup
    logger.info("Starting webhook application", extra={"domain": settings.webhook_domain})

    try:
        # Инициализация сервисов
        await initialize_services()
        logger.info("Webhook services initialized successfully")

    except Exception as e:
        logger.error("Failed to initialize webhook services", extra={"error": str(e)}, exc_info=True)
        raise

    yield

    # Shutdown
    logger.info("Shutting down webhook application")
    await cleanup_services()


async def initialize_services():
    """Инициализация всех сервисов"""
    global services

    try:
        # Инициализация репозиториев
        user_repository = UserRepository(database_url=settings.database_url)
        await user_repository.create_tables()

        # Инициализация Redis кеша с использованием унифицированного менеджера
        redis_client = None
        user_cache = None
        payment_cache = None

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

                redis_client = cache_services['redis_client']
                user_cache = cache_services['user_cache']
                payment_cache = cache_services['payment_cache']

                logger.info("Redis cache initialized successfully using unified manager")

            except Exception as e:
                logger.error("Failed to initialize Redis cache", extra={"error": str(e)})
                logger.warning("Webhook services will continue without cache functionality")

        # Инициализация сервисов
        balance_repository = BalanceRepository(user_repository.async_session)
        payment_service = PaymentService(
            merchant_uuid=settings.merchant_uuid,
            api_key=settings.api_key
        )

        # Инициализация сервиса покупки звезд
        star_purchase_service = StarPurchaseService(
            user_repository=user_repository,
            balance_repository=balance_repository,
            payment_service=payment_service,
            user_cache=user_cache,
            payment_cache=payment_cache
        )

        # Инициализация обработчика вебхуков
        webhook_handler = WebhookHandler(
            star_purchase_service=star_purchase_service,
            user_cache=user_cache,
            payment_cache=payment_cache
        )

        # Rate limiter больше не используется - удален как избыточный
        rate_limiter = None

        # Инициализация health service
        health_service = None
        if redis_client:
            try:
                health_service = HealthService(redis_client)
                logger.info("Health service initialized")
            except Exception as e:
                logger.error("Failed to initialize health service", extra={"error": str(e)})

        # Сохранение сервисов
        services.update({
            'user_repository': user_repository,
            'balance_repository': balance_repository,
            'payment_service': payment_service,
            'star_purchase_service': star_purchase_service,
            'user_cache': user_cache,
            'payment_cache': payment_cache,
            'webhook_handler': webhook_handler,
            'rate_limiter': rate_limiter,
            'health_service': health_service,
            'redis_client': redis_client
        })

        logger.info("All webhook services initialized successfully")

    except Exception as e:
        logger.error("Error during webhook services initialization", extra={"error": str(e)}, exc_info=True)
        raise


async def cleanup_services():
    """Очистка ресурсов при завершении"""
    global services

    try:
        # Закрытие соединений
        if 'user_repository' in services:
            await services['user_repository'].close()

        if 'user_cache' in services and services['user_cache']:
            await services['user_cache'].close()

        logger.info("Webhook services cleaned up successfully")

    except Exception as e:
        logger.error("Error during services cleanup", extra={"error": str(e)}, exc_info=True)


# Создание FastAPI приложения
app = FastAPI(
    title="Mirza Telegram Shop Bot - Webhook Handler",
    description="Полнофункциональный обработчик вебхуков для платежной системы Heleket с поддержкой домена nekamita.work",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://nekamita.work",
        "https://www.nekamita.work",
        "https://api.nekamita.work"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    max_age=86400,  # 24 hours
)

# Настройка доверенных хостов
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "nekamita.work",
        "www.nekamita.work",
        "api.nekamita.work",
        "localhost",
        "127.0.0.1",
        "0.0.0.0"
    ]
)

# Добавление middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(DomainLoggingMiddleware)
app.add_middleware(SimpleRateLimitMiddleware)


# Health endpoints
@app.get("/health")
async def health_check():
    """Основной health check endpoint"""
    try:
        health_data: Dict[str, Any] = {
            "status": "healthy",
            "service": "webhook-handler",
            "domain": settings.webhook_domain,
            "timestamp": datetime.utcnow().isoformat(),
            "version": "2.0.0",
            "environment": settings.environment
        }

        # Проверка сервисов
        services_status = {}
        if 'health_service' in services and services['health_service']:
            services_status = await services['health_service'].get_health_status()

        health_data.update({"services": services_status})

        # Определение общего статуса
        if services_status and services_status.get("status") == "unhealthy":
            health_data["status"] = "unhealthy"
            return JSONResponse(content=health_data, status_code=503)

        return JSONResponse(content=health_data, status_code=200)

    except Exception as e:
        logger.error("Health check failed", extra={"error": str(e)}, exc_info=True)

        return JSONResponse(
            content={
                "status": "unhealthy",
                "error": "Внутренняя ошибка сервера",
                "domain": settings.webhook_domain,
                "timestamp": datetime.utcnow().isoformat()
            },
            status_code=503
        )


@app.get("/health/detailed")
async def detailed_health_check():
    """Детальный health check со всей информацией о системе"""
    try:
        if 'health_service' not in services or not services['health_service']:
            return JSONResponse(
                content={"error": "Health service not initialized"},
                status_code=503
            )

        detailed_health = await services['health_service'].get_detailed_metrics()

        # Добавление информации о домене
        detailed_health.update({
            "domain": settings.webhook_domain,
            "cloudflare_tunnel_url": settings.cloudflare_tunnel_url,
            "webhook_domain_logging": settings.webhook_domain_logging,
            "domain_debug_logging": settings.domain_debug_logging
        })

        return JSONResponse(content=detailed_health, status_code=200)

    except Exception as e:
        logger.error("Detailed health check failed", extra={"error": str(e)}, exc_info=True)
        return JSONResponse(
            content={
                "status": "unhealthy",
                "error": "Внутренняя ошибка сервера",
                "domain": settings.webhook_domain,
                "timestamp": datetime.utcnow().isoformat()
            },
            status_code=503
        )


@app.get("/metrics")
async def metrics():
    """Metrics endpoint (placeholder for Prometheus metrics)"""
    try:
        return JSONResponse(
            content={
                "service": "webhook-handler",
                "metrics": {
                    "uptime": "running",
                    "version": "2.0.0",
                    "domain": settings.webhook_domain
                },
                "note": "Prometheus metrics require prometheus_client dependency"
            }
        )
    except Exception as e:
        logger.error("Metrics endpoint failed", extra={"error": str(e)}, exc_info=True)
        return JSONResponse(
            content={
                "error": "Внутренняя ошибка сервера",
                "message": "Не удалось сгенерировать метрики"
            },
            status_code=500
        )


# Webhook endpoint
@app.post("/webhook/heleket")
async def handle_heleket_webhook(request: Request):
    """Обработка вебхука от платежной системы Heleket с полной поддержкой домена"""
    try:
        if 'webhook_handler' not in services:
            raise HTTPException(status_code=500, detail="Webhook handler not initialized")

        client_host = getattr(request.client, 'host', 'unknown') if request.client else 'unknown'
        cf_real_ip = request.headers.get('cf-connecting-ip', client_host)

        logger.info(
            "webhook_received",
            extra={
                "domain": settings.webhook_domain,
                "client_ip": client_host,
                "cf_real_ip": cf_real_ip,
                "host_header": request.headers.get('host', 'unknown'),
                "user_agent": request.headers.get('user-agent', 'unknown'),
                "cf_ray": request.headers.get('cf-ray', 'unknown')
            }
        )

        # Обработка вебхука
        result = await services['webhook_handler'].handle_payment_webhook(request)

        if isinstance(result, JSONResponse):
            # Логирование в зависимости от статуса ответа
            if result.status_code == 200:
                logger.info(
                    "webhook_processed_successfully",
                    extra={
                        "domain": settings.webhook_domain,
                        "client_ip": client_host,
                        "cf_real_ip": cf_real_ip
                    }
                )
            else:
                logger.warning(
                    "webhook_processing_failed",
                    extra={
                        "domain": settings.webhook_domain,
                        "client_ip": client_host,
                        "cf_real_ip": cf_real_ip,
                        "status_code": result.status_code
                    }
                )

        return result

    except HTTPException as e:
        logger.error(
            "webhook_http_error",
            extra={
                "domain": settings.webhook_domain,
                "error": str(e),
                "status_code": e.status_code
            },
            exc_info=True
        )
        raise e

    except Exception as e:
        logger.error(
            "webhook_unexpected_error",
            extra={
                "domain": settings.webhook_domain,
                "error": str(e)
            },
            exc_info=True
        )
        return JSONResponse(
            content={
                "status": "error",
                "message": "Internal server error",
                "domain": settings.webhook_domain
            },
            status_code=500
        )


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint с информацией о приложении"""
    return JSONResponse(
        content={
            "service": "Mirza Telegram Shop Bot - Webhook Handler",
            "version": "2.0.0",
            "domain": settings.webhook_domain,
            "status": "running",
            "endpoints": {
                "health": "/health",
                "detailed_health": "/health/detailed",
                "metrics": "/metrics",
                "webhook": "/webhook/heleket",
                "docs": "/docs"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    )


# Custom exception handlers
@app.exception_handler(429)
async def rate_limit_handler(request: Request, exc):
    """Обработчик rate limit ошибок"""
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "retry_after": 60,
            "message": "Слишком много запросов. Попробуйте через минуту.",
            "domain": settings.webhook_domain
        }
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    """Обработчик внутренних ошибок"""
    logger.error("Internal server error", extra={"error": str(exc), "path": request.url.path}, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "Произошла внутренняя ошибка сервера",
            "domain": settings.webhook_domain
        }
    )


if __name__ == "__main__":
    import uvicorn

    # Настройка логирования для uvicorn
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO"},
            "uvicorn.error": {"handlers": ["default"], "level": "INFO"},
            "uvicorn.access": {"handlers": ["default"], "level": "INFO"},
        },
    }

    uvicorn.run(
        "services.webhook_app:app",
        host=settings.webhook_host,
        port=settings.webhook_port,
        reload=settings.debug,
        log_config=log_config,
        access_log=True,
        server_header=False,  # Скрываем информацию о сервере
        date_header=False     # Скрываем информацию о дате
    )
