"""
Alert Service - сервис для отправки уведомлений о критических сбоях
Интеграция с Telegram для мгновенных оповещений
"""

import asyncio
import aiohttp
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
from config.settings import settings


class AlertLevel(Enum):
    """Уровни важности алертов"""
    INFO = "INFO"
    WARNING = "WARNING" 
    CRITICAL = "CRITICAL"
    EMERGENCY = "EMERGENCY"


@dataclass
class Alert:
    """Структура алерта"""
    level: AlertLevel
    message: str
    service: str
    timestamp: datetime
    details: Optional[Dict[str, Any]] = None
    resolved: bool = False


class AlertService:
    """Сервис для управления и отправки алертов"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: List[Alert] = []

    async def send_telegram_alert(self, alert: Alert) -> bool:
        """Отправка алерта в Telegram"""
        # Проверяем включен ли алертинг
        if not settings.telegram_alerts_enabled:
            self.logger.debug("Telegram alerts are disabled, skipping alert")
            return False
            
        if not settings.telegram_token or not settings.telegram_chat_id:
            self.logger.warning("Telegram credentials not configured")
            return False

        try:
            # Форматируем сообщение для Telegram
            emoji = self._get_alert_emoji(alert.level)
            message = f"{emoji} *{alert.level.value}* - {alert.service}\n"
            message += f"⏰ {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
            message += f"📝 {alert.message}\n"

            if alert.details:
                details_str = "\n".join([f"• {k}: {v}" for k, v in alert.details.items()])
                message += f"\n🔍 Детали:\n{details_str}"

            # Отправляем сообщение
            url = f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage"
            payload = {
                "chat_id": settings.telegram_chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_notification": alert.level == AlertLevel.INFO
            }

            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        self.logger.info(f"Alert sent to Telegram: {alert.message}")
                        return True
                    else:
                        self.logger.error(f"Failed to send alert: {response.status}")
                        return False

        except Exception as e:
            self.logger.error(f"Error sending Telegram alert: {e}")
            return False

    def _get_alert_emoji(self, level: AlertLevel) -> str:
        """Получение emoji для уровня алерта"""
        emojis = {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.CRITICAL: "🚨",
            AlertLevel.EMERGENCY: "🔴"
        }
        return emojis.get(level, "📢")

    async def create_alert(self, 
                          level: AlertLevel, 
                          message: str, 
                          service: str,
                          details: Optional[Dict[str, Any]] = None) -> str:
        """Создание нового алерта"""
        alert_id = f"{service}_{datetime.now(timezone.utc).timestamp()}"
        
        alert = Alert(
            level=level,
            message=message,
            service=service,
            timestamp=datetime.now(timezone.utc),
            details=details
        )

        # Добавляем в активные алерты
        self.active_alerts[alert_id] = alert
        self.alert_history.append(alert)

        # Отправляем уведомление
        if level in [AlertLevel.WARNING, AlertLevel.CRITICAL, AlertLevel.EMERGENCY]:
            await self.send_telegram_alert(alert)

        self.logger.info(f"Alert created: {alert_id} - {message}")
        return alert_id

    async def resolve_alert(self, alert_id: str, resolution_message: str = "") -> bool:
        """Разрешение алерта"""
        if alert_id not in self.active_alerts:
            return False

        alert = self.active_alerts[alert_id]
        alert.resolved = True
        
        # Отправляем уведомление о разрешении
        if alert.level in [AlertLevel.CRITICAL, AlertLevel.EMERGENCY]:
            resolution_alert = Alert(
                level=AlertLevel.INFO,
                message=f"Resolved: {alert.message}",
                service=alert.service,
                timestamp=datetime.now(timezone.utc),
                details={"resolution": resolution_message} if resolution_message else None
            )
            await self.send_telegram_alert(resolution_alert)

        # Удаляем из активных алертов
        del self.active_alerts[alert_id]
        self.logger.info(f"Alert resolved: {alert_id}")
        return True

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Получение активных алертов"""
        return [
            {
                "id": alert_id,
                "level": alert.level.value,
                "message": alert.message,
                "service": alert.service,
                "timestamp": alert.timestamp.isoformat(),
                "details": alert.details
            }
            for alert_id, alert in self.active_alerts.items()
        ]

    def get_alert_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Получение истории алертов"""
        recent_history = self.alert_history[-limit:] if self.alert_history else []
        return [
            {
                "level": alert.level.value,
                "message": alert.message,
                "service": alert.service,
                "timestamp": alert.timestamp.isoformat(),
                "resolved": alert.resolved,
                "details": alert.details
            }
            for alert in recent_history
        ]

    async def check_and_alert_redis_cluster(self, cluster_info: Dict[str, Any]) -> Optional[str]:
        """Проверка состояния Redis кластера и отправка алертов"""
        slots_covered = cluster_info.get("slots_covered", 0)
        total_slots = cluster_info.get("total_slots", 16384)
        
        if slots_covered < total_slots:
            message = f"Redis Cluster slots not fully covered: {slots_covered}/{total_slots}"
            details = {
                "slots_covered": slots_covered,
                "total_slots": total_slots,
                "missing_slots": total_slots - slots_covered
            }
            
            if slots_covered == 0:
                return await self.create_alert(
                    AlertLevel.EMERGENCY, 
                    "Redis Cluster: NO SLOTS COVERED!", 
                    "redis_cluster",
                    details
                )
            elif slots_covered < total_slots * 0.9:  # Менее 90% покрытия
                return await self.create_alert(
                    AlertLevel.CRITICAL,
                    message,
                    "redis_cluster",
                    details
                )
            else:
                return await self.create_alert(
                    AlertLevel.WARNING,
                    message,
                    "redis_cluster", 
                    details
                )
        return None

    async def check_and_alert_external_service(self, 
                                             service_name: str, 
                                             status: str, 
                                             response_time: float,
                                             error: Optional[str] = None) -> Optional[str]:
        """Проверка внешних сервисов и отправка алертов"""
        if status == "unhealthy":
            message = f"External service {service_name} is down"
            details = {
                "response_time_ms": response_time,
                "error": error
            }
            
            # Критичные сервисы
            critical_services = ["telegram_api", "payment_service", "database"]
            if service_name in critical_services:
                return await self.create_alert(
                    AlertLevel.CRITICAL,
                    message,
                    service_name,
                    details
                )
            else:
                return await self.create_alert(
                    AlertLevel.WARNING, 
                    message,
                    service_name,
                    details
                )
        return None

    async def check_and_alert_system_resources(self, resources: Dict[str, Any]) -> List[str]:
        """Проверка системных ресурсов и отправка алертов"""
        alert_ids = []
        
        # Проверка использования CPU
        cpu_usage = resources.get("cpu", {}).get("usage_percent", 0)
        if cpu_usage > 90:
            alert_ids.append(await self.create_alert(
                AlertLevel.CRITICAL,
                f"High CPU usage: {cpu_usage}%",
                "system_resources",
                {"cpu_usage": cpu_usage}
            ))
        elif cpu_usage > 80:
            alert_ids.append(await self.create_alert(
                AlertLevel.WARNING,
                f"High CPU usage: {cpu_usage}%", 
                "system_resources",
                {"cpu_usage": cpu_usage}
            ))

        # Проверка использования памяти
        memory_usage = resources.get("memory", {}).get("usage_percent", 0)
        if memory_usage > 90:
            alert_ids.append(await self.create_alert(
                AlertLevel.CRITICAL,
                f"High memory usage: {memory_usage}%",
                "system_resources",
                {"memory_usage": memory_usage}
            ))
        elif memory_usage > 80:
            alert_ids.append(await self.create_alert(
                AlertLevel.WARNING,
                f"High memory usage: {memory_usage}%",
                "system_resources", 
                {"memory_usage": memory_usage}
            ))

        return alert_ids


# Глобальный экземпляр сервиса алертинга
alert_service = AlertService()