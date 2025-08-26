"""
WebSocket Service - сервис для real-time уведомлений через WebSocket
"""
import asyncio
import json
import logging
from typing import Dict, Any, Set, Optional, Union, cast
from datetime import datetime
import redis.asyncio as redis
from redis.cluster import RedisCluster
from services.cache.session_cache import SessionCache


class WebSocketService:
    """Сервис для управления WebSocket соединениями и real-time уведомлениями"""

    def __init__(self, redis_client: Union[redis.Redis, RedisCluster], session_cache: SessionCache):
        self.redis_client = redis_client
        self.session_cache = session_cache
        self.logger = logging.getLogger(__name__)
        self.connections: Dict[int, Set[str]] = {}  # user_id -> set of connection_ids
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}  # connection_id -> metadata
        self.is_cluster = isinstance(redis_client, RedisCluster)

        # Добавляем логи для диагностики типов
        self.logger.info(f"Redis client type: {type(redis_client)}")
        self.logger.info(f"Is cluster: {self.is_cluster}")

    async def register_connection(self, user_id: int, connection_id: str, metadata: Dict[str, Any]) -> None:
        """Регистрация нового WebSocket соединения"""
        try:
            if user_id not in self.connections:
                self.connections[user_id] = set()

            self.connections[user_id].add(connection_id)
            self.connection_metadata[connection_id] = {
                **metadata,
                "user_id": user_id,
                "connected_at": datetime.utcnow().isoformat()
            }

            # Сохраняем в Redis для распределенной системы
            if self.is_cluster:
                cluster_client = cast(RedisCluster, self.redis_client)
                cluster_client.sadd(f"ws_connections:{user_id}", connection_id)
                cluster_client.hset(
                    f"ws_metadata:{connection_id}",
                    mapping=self.connection_metadata[connection_id]
                )
            else:
                redis_client = cast(redis.Redis, self.redis_client)
                await redis_client.sadd(f"ws_connections:{user_id}", connection_id)
                await redis_client.hset(
                    f"ws_metadata:{connection_id}",
                    mapping=self.connection_metadata[connection_id]
                )

            self.logger.info(f"WebSocket connection registered for user {user_id}: {connection_id}")

        except Exception as e:
            self.logger.error(f"Error registering WebSocket connection: {e}")

    async def unregister_connection(self, user_id: int, connection_id: str) -> None:
        """Удаление WebSocket соединения"""
        try:
            if user_id in self.connections:
                self.connections[user_id].discard(connection_id)
                if not self.connections[user_id]:
                    del self.connections[user_id]

            self.connection_metadata.pop(connection_id, None)

            # Удаляем из Redis
            if self.is_cluster:
                cluster_client = cast(RedisCluster, self.redis_client)
                cluster_client.srem(f"ws_connections:{user_id}", connection_id)
                cluster_client.delete(f"ws_metadata:{connection_id}")
            else:
                redis_client = cast(redis.Redis, self.redis_client)
                await redis_client.srem(f"ws_connections:{user_id}", connection_id)
                await redis_client.delete(f"ws_metadata:{connection_id}")

            self.logger.info(f"WebSocket connection unregistered for user {user_id}: {connection_id}")

        except Exception as e:
            self.logger.error(f"Error unregistering WebSocket connection: {e}")

    async def get_user_connections(self, user_id: int) -> Set[str]:
        """Получение всех активных соединений пользователя"""
        try:
            # Проверяем локальный кеш и Redis
            local_connections = self.connections.get(user_id, set())
            if self.is_cluster:
                cluster_client = cast(RedisCluster, self.redis_client)
                redis_connections = cluster_client.smembers(f"ws_connections:{user_id}")
            else:
                redis_client = cast(redis.Redis, self.redis_client)
                redis_connections = await redis_client.smembers(f"ws_connections:{user_id}")
            redis_connections = {conn.decode() if isinstance(conn, bytes) else conn for conn in redis_connections}

            # Объединяем и синхронизируем
            all_connections = local_connections.union(redis_connections)
            return all_connections
        except Exception as e:
            self.logger.error(f"Error getting user connections: {e}")
            return set()

    async def send_notification(self, user_id: int, message_type: str, data: Dict[str, Any]) -> int:
        """Отправка уведомления пользователю через WebSocket"""
        try:
            connections = await self.get_user_connections(user_id)
            if not connections:
                return 0

            notification = {
                "type": message_type,
                "data": data,
                "timestamp": datetime.utcnow().isoformat()
            }

            sent_count = 0
            for connection_id in connections:
                try:
                    # Публикуем в Redis для распределенной доставки
                    await self.redis_client.publish(
                        f"ws_message:{connection_id}",
                        json.dumps(notification)
                    )
                    sent_count += 1
                except Exception as e:
                    self.logger.error(f"Error sending notification to {connection_id}: {e}")

            self.logger.info(f"Sent {sent_count} notifications to user {user_id}")
            return sent_count

        except Exception as e:
            self.logger.error(f"Error sending notification: {e}")
            return 0

    async def broadcast_message(self, message_type: str, data: Dict[str, Any], exclude_users: Optional[Set[int]] = None) -> int:
        """Рассылка сообщения всем подключенным пользователям"""
        try:
            exclude_users = exclude_users or set()

            notification = {
                "type": message_type,
                "data": data,
                "timestamp": datetime.utcnow().isoformat()
            }

            # Получаем всех активных пользователей
            pattern = "ws_connections:*"
            if self.is_cluster:
                cluster_client = cast(RedisCluster, self.redis_client)
                keys = cluster_client.keys(pattern)
            else:
                redis_client = cast(redis.Redis, self.redis_client)
                keys = await redis_client.keys(pattern)

            sent_count = 0
            for key in keys:
                user_id = int(key.decode().split(":")[1])
                if user_id in exclude_users:
                    continue

                connections = await self.get_user_connections(user_id)
                for connection_id in connections:
                    try:
                        await self.redis_client.publish(
                            f"ws_message:{connection_id}",
                            json.dumps(notification)
                        )
                        sent_count += 1
                    except Exception as e:
                        self.logger.error(f"Error broadcasting to {connection_id}: {e}")

            self.logger.info(f"Broadcasted message to {sent_count} connections")
            return sent_count

        except Exception as e:
            self.logger.error(f"Error broadcasting message: {e}")
            return 0

    async def send_payment_notification(self, user_id: int, payment_data: Dict[str, Any]) -> int:
        """Отправка уведомления об оплате"""
        return await self.send_notification(
            user_id,
            "payment_completed",
            {
                "amount": payment_data.get("amount"),
                "currency": payment_data.get("currency", "TON"),
                "status": payment_data.get("status", "completed"),
                "transaction_id": payment_data.get("transaction_id")
            }
        )

    async def send_balance_update(self, user_id: int, new_balance: float) -> int:
        """Отправка уведомления об обновлении баланса"""
        return await self.send_notification(
            user_id,
            "balance_updated",
            {
                "new_balance": new_balance,
                "updated_at": datetime.utcnow().isoformat()
            }
        )

    async def send_system_alert(self, user_id: int, alert_type: str, message: str) -> int:
        """Отправка системного уведомления"""
        return await self.send_notification(
            user_id,
            "system_alert",
            {
                "alert_type": alert_type,
                "message": message,
                "priority": "high"
            }
        )

    async def get_connection_stats(self) -> Dict[str, Any]:
        """Получение статистики WebSocket соединений"""
        try:
            total_connections = 0
            active_users = 0

            pattern = "ws_connections:*"
            keys = await self.redis_client.keys(pattern)

            for key in keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                user_id = int(key_str.split(":")[1])
                connections = await self.get_user_connections(user_id)
                total_connections += len(connections)
                if connections:
                    active_users += 1

            return {
                "total_connections": total_connections,
                "active_users": active_users,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            self.logger.error(f"Error getting connection stats: {e}")
            return {"error": str(e)}

    async def cleanup_inactive_connections(self, max_inactive_minutes: int = 30) -> int:
        """Очистка неактивных соединений"""
        try:
            cleaned_count = 0
            pattern = "ws_metadata:*"
            if self.is_cluster:
                cluster_client = cast(RedisCluster, self.redis_client)
                keys = cluster_client.keys(pattern)
            else:
                redis_client = cast(redis.Redis, self.redis_client)
                keys = await redis_client.keys(pattern)

            for key in keys:
                connection_id = key.decode().split(":")[1]
                if self.is_cluster:
                    cluster_client = cast(RedisCluster, self.redis_client)
                    metadata = cluster_client.hgetall(key)
                else:
                    redis_client = cast(redis.Redis, self.redis_client)
                    metadata = await redis_client.hgetall(key)

                if metadata:
                    # Handle both bytes and string keys from Redis
                    connected_at_key = b"connected_at" if isinstance(list(metadata.keys())[0], bytes) else "connected_at"
                    user_id_key = b"user_id" if isinstance(list(metadata.keys())[0], bytes) else "user_id"

                    connected_at_str = metadata[connected_at_key]
                    if isinstance(connected_at_str, bytes):
                        connected_at_str = connected_at_str.decode()

                    user_id_str = metadata[user_id_key]
                    if isinstance(user_id_str, bytes):
                        user_id_str = user_id_str.decode()

                    connected_at = datetime.fromisoformat(connected_at_str)
                    if (datetime.utcnow() - connected_at).total_seconds() > max_inactive_minutes * 60:
                        user_id = int(user_id_str)
                        await self.unregister_connection(user_id, connection_id)
                        cleaned_count += 1

            self.logger.info(f"Cleaned up {cleaned_count} inactive connections")
            return cleaned_count

        except Exception as e:
            self.logger.error(f"Error cleaning up connections: {e}")
            return 0

    async def subscribe_to_messages(self, connection_id: str):
        """Подписка на сообщения для конкретного соединения"""
        try:
            if self.is_cluster:
                # Для RedisCluster pubsub работает иначе
                cluster_client = cast(RedisCluster, self.redis_client)
                pubsub = cluster_client.pubsub()
                pubsub.subscribe(f"ws_message:{connection_id}")

                for message in pubsub.listen():
                    if message["type"] == "message":
                        yield json.loads(message["data"])
            else:
                # Для обычного Redis
                redis_client = cast(redis.Redis, self.redis_client)
                pubsub = redis_client.pubsub()
                await pubsub.subscribe(f"ws_message:{connection_id}")

                async for message in pubsub.listen():
                    if message["type"] == "message":
                        yield json.loads(message["data"])

        except Exception as e:
            self.logger.error(f"Error subscribing to messages: {e}")
