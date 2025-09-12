"""
External Health Service - сервис для мониторинга доступности внешних API
Интегрируется с основным Health Service и предоставляет детальные проверки
"""

import asyncio
import aiohttp
import logging
from typing import Dict, Any, List
from datetime import datetime, timezone
from dataclasses import dataclass
from config.settings import settings


@dataclass
class ExternalServiceConfig:
    """Конфигурация внешнего сервиса для мониторинга"""
    name: str
    url: str
    timeout: int = 5
    expected_status: int = 200
    check_interval: int = 30
    is_critical: bool = False


class ExternalHealthService:
    """Сервис для мониторинга доступности внешних API"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.services = self._get_services_config()
        self.last_check_results: Dict[str, Dict[str, Any]] = {}

    def _get_services_config(self) -> List[ExternalServiceConfig]:
        """Получение конфигурации мониторинга внешних сервисов"""
        return [
            ExternalServiceConfig(
                name="telegram_api",
                url=f"https://api.telegram.org/bot{settings.telegram_token}/getMe" if settings.telegram_token else "https://api.telegram.org",
                timeout=3,
                expected_status=200,
                is_critical=True
            ),
            ExternalServiceConfig(
                name="payment_service",
                url="https://api.heleket.com/v1/health",
                timeout=5,
                expected_status=200,
                is_critical=True
            ),
            ExternalServiceConfig(
                name="fragment_api",
                url="https://fragment.com/api/health",  # Примерный endpoint
                timeout=10,
                expected_status=200,
                is_critical=False
            ),
            ExternalServiceConfig(
                name="cloudflare_dns",
                url="https://1.1.1.1/dns-query",
                timeout=3,
                expected_status=200,
                is_critical=False
            )
        ]

    async def check_service(self, service: ExternalServiceConfig) -> Dict[str, Any]:
        """Проверка доступности конкретного сервиса"""
        start_time = datetime.now(timezone.utc)
        
        try:
            timeout = aiohttp.ClientTimeout(total=service.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                
                # Для Telegram API используем HEAD запрос для экономии трафика
                if "telegram" in service.name.lower():
                    async with session.head(service.url) as response:
                        response_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                        status_ok = response.status == service.expected_status
                else:
                    async with session.get(service.url) as response:
                        response_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                        status_ok = response.status == service.expected_status
                
                return {
                    "status": "healthy" if status_ok else "unhealthy",
                    "response_time_ms": response_time,
                    "status_code": response.status,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
        except asyncio.TimeoutError:
            return {
                "status": "unhealthy",
                "error": "Timeout",
                "response_time_ms": service.timeout * 1000,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "response_time_ms": (datetime.now(timezone.utc) - start_time).total_seconds() * 1000,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    async def check_all_services(self) -> Dict[str, Any]:
        """Проверка всех внешних сервисов параллельно"""
        start_time = datetime.now(timezone.utc)
        
        # Запускаем все проверки параллельно
        tasks = []
        for service in self.services:
            tasks.append(self.check_service(service))
        
        results = await asyncio.gather(*tasks)
        
        # Собираем результаты по имени сервиса
        service_results = {}
        for i, service in enumerate(self.services):
            service_results[service.name] = results[i]
        
        # Определяем общий статус
        overall_status = "healthy"
        unhealthy_critical = False
        
        for service_name, result in service_results.items():
            if result["status"] == "unhealthy":
                service_config = next(s for s in self.services if s.name == service_name)
                if service_config.is_critical:
                    unhealthy_critical = True
                    overall_status = "unhealthy"
                elif overall_status == "healthy":
                    overall_status = "degraded"
        
        response_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        
        self.last_check_results = service_results
        
        return {
            "status": overall_status,
            "response_time_ms": response_time,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "services": service_results,
            "has_critical_issues": unhealthy_critical
        }

    async def get_service_metrics(self) -> Dict[str, Any]:
        """Получение метрик по всем сервисам"""
        if not self.last_check_results:
            await self.check_all_services()
        
        metrics = {}
        for service_name, result in self.last_check_results.items():
            metrics[service_name] = {
                "response_time": result.get("response_time_ms", 0),
                "status": result.get("status", "unknown"),
                "last_check": result.get("timestamp")
            }
        
        return metrics

    async def get_detailed_report(self) -> Dict[str, Any]:
        """Получение детального отчета о состоянии внешних сервисов"""
        health_status = await self.check_all_services()
        
        # Добавляем дополнительную информацию
        report = {
            **health_status,
            "summary": {
                "total_services": len(self.services),
                "healthy_services": sum(1 for r in health_status["services"].values() if r["status"] == "healthy"),
                "unhealthy_services": sum(1 for r in health_status["services"].values() if r["status"] == "unhealthy"),
                "critical_services": [s.name for s in self.services if s.is_critical],
                "degraded_services": [name for name, result in health_status["services"].items() 
                                    if result["status"] == "unhealthy" and not next(s for s in self.services if s.name == name).is_critical]
            }
        }
        
        return report

    def get_service_configuration(self) -> List[Dict[str, Any]]:
        """Получение конфигурации мониторинга сервисов"""
        return [
            {
                "name": service.name,
                "url": service.url,
                "timeout": service.timeout,
                "expected_status": service.expected_status,
                "is_critical": service.is_critical,
                "check_interval": service.check_interval
            }
            for service in self.services
        ]


# Глобальный экземпляр сервиса
external_health_service = ExternalHealthService()


# Интеграция с основным Health Service
async def get_external_services_health() -> Dict[str, Any]:
    """Функция для интеграции с основным Health Service"""
    return await external_health_service.check_all_services()