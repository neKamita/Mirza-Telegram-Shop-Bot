"""
Session Cache Service - специализированный сервис для управления сессиями пользователей
"""
import json
import logging
import uuid
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import redis.asyncio as redis
from config.settings import settings


class SessionCache:
    """Специализированный сервис для управления сессиями пользователей"""

    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client
        self.logger = logging.getLogger(__name__)
        self.SESSION_PREFIX = "session:"
        self.SESSION_TTL = settings.cache_ttl_session
        self.SESSION_DATA_PREFIX = "session_data:"
        self.SESSION_STATE_PREFIX = "session_state:"

    async def create_session(self, user_id: int, initial_data: Optional[Dict[str, Any]] = None) -> str:
        """Создание новой сессии пользователя"""
        try:
            session_id = str(uuid.uuid4())
            session_key = f"{self.SESSION_PREFIX}{session_id}"

            # Данные сессии
            session_data = {
                'user_id': user_id,
                'created_at': datetime.utcnow().isoformat(),
                'last_activity': datetime.utcnow().isoformat(),
                'is_active': True
            }

            if initial_data:
                session_data.update(initial_data)

            # Сохраняем сессию
            serialized = json.dumps(session_data, default=str)
            await self.redis_client.setex(session_key, self.SESSION_TTL, serialized)

            # Индексируем сессии по пользователю для быстрого поиска
            user_sessions_key = f"user_sessions:{user_id}"
            await self.redis_client.lpush(user_sessions_key, session_id)
            await self.redis_client.expire(user_sessions_key, self.SESSION_TTL)

            self.logger.info(f"Created session {session_id} for user {user_id}")
            return session_id

        except Exception as e:
            self.logger.error(f"Error creating session for user {user_id}: {e}")
            raise

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Получение сессии по ID"""
        try:
            session_key = f"{self.SESSION_PREFIX}{session_id}"
            cached_data = await self.redis_client.get(session_key)

            if cached_data:
                session_data = json.loads(cached_data)

                # Проверяем активность и свежесть
                if session_data.get('is_active') and self._is_session_valid(session_data):
                    # Обновляем время последней активности
                    session_data['last_activity'] = datetime.utcnow().isoformat()
                    await self.update_session(session_id, session_data)
                    return session_data
                else:
                    # Сессия неактивна или устарела
                    await self.delete_session(session_id)

            return None

        except Exception as e:
            self.logger.error(f"Error getting session {session_id}: {e}")
            return None

    async def update_session(self, session_id: str, session_data: Dict[str, Any]) -> bool:
        """Обновление данных сессии"""
        try:
            session_key = f"{self.SESSION_PREFIX}{session_id}"
            session_data['last_activity'] = datetime.utcnow().isoformat()
            serialized = json.dumps(session_data, default=str)
            await self.redis_client.setex(session_key, self.SESSION_TTL, serialized)
            return True
        except Exception as e:
            self.logger.error(f"Error updating session {session_id}: {e}")
            return False

    async def delete_session(self, session_id: str) -> bool:
        """Удаление сессии"""
        try:
            session_key = f"{self.SESSION_PREFIX}{session_id}"
            session_data = await self.get_session(session_id)

            # Удаляем сессию
            await self.redis_client.delete(session_key)

            # Удаляем связанные данные
            await self.redis_client.delete(f"{self.SESSION_DATA_PREFIX}{session_id}")
            await self.redis_client.delete(f"{self.SESSION_STATE_PREFIX}{session_id}")

            # Удаляем из индекса пользователя
            if session_data and 'user_id' in session_data:
                user_sessions_key = f"user_sessions:{session_data['user_id']}"
                await self.redis_client.lrem(user_sessions_key, 0, session_id)

            self.logger.info(f"Deleted session {session_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error deleting session {session_id}: {e}")
            return False

    async def get_user_sessions(self, user_id: int) -> list:
        """Получение всех активных сессий пользователя"""
        try:
            user_sessions_key = f"user_sessions:{user_id}"
            session_ids = await self.redis_client.lrange(user_sessions_key, 0, -1)

            active_sessions = []
            for session_id_bytes in session_ids:
                session_id = session_id_bytes.decode('utf-8')
                session = await self.get_session(session_id)
                if session:
                    active_sessions.append(session)

            return active_sessions

        except Exception as e:
            self.logger.error(f"Error getting sessions for user {user_id}: {e}")
            return []

    async def invalidate_user_sessions(self, user_id: int, keep_active: bool = False) -> int:
        """Инвалидация всех сессий пользователя"""
        try:
            sessions = await self.get_user_sessions(user_id)
            invalidated_count = 0

            for session in sessions:
                if keep_active and session.get('is_active'):
                    continue
                await self.delete_session(session['id'])
                invalidated_count += 1

            self.logger.info(f"Invalidated {invalidated_count} sessions for user {user_id}")
            return invalidated_count

        except Exception as e:
            self.logger.error(f"Error invalidating sessions for user {user_id}: {e}")
            return 0

    async def cache_session_data(self, session_id: str, data: Dict[str, Any]) -> bool:
        """Кеширование данных сессии"""
        try:
            data_key = f"{self.SESSION_DATA_PREFIX}{session_id}"
            data['cached_at'] = datetime.utcnow().isoformat()
            serialized = json.dumps(data, default=str)
            await self.redis_client.setex(data_key, self.SESSION_TTL, serialized)
            return True
        except Exception as e:
            self.logger.error(f"Error caching session data for {session_id}: {e}")
            return False

    async def get_session_data(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Получение данных сессии"""
        try:
            data_key = f"{self.SESSION_DATA_PREFIX}{session_id}"
            cached_data = await self.redis_client.get(data_key)

            if cached_data:
                data = json.loads(cached_data)
                # Проверяем свежесть
                cached_at = datetime.fromisoformat(data.get('cached_at', ''))
                if datetime.utcnow() - cached_at < timedelta(seconds=self.SESSION_TTL):
                    data.pop('cached_at', None)
                    return data
                else:
                    await self.redis_client.delete(data_key)

            return None

        except Exception as e:
            self.logger.error(f"Error getting session data for {session_id}: {e}")
            return None

    async def cache_session_state(self, session_id: str, state: Dict[str, Any]) -> bool:
        """Кеширование состояния сессии (например, состояние бота)"""
        try:
            state_key = f"{self.SESSION_STATE_PREFIX}{session_id}"
            state['updated_at'] = datetime.utcnow().isoformat()
            serialized = json.dumps(state, default=str)
            await self.redis_client.setex(state_key, self.SESSION_TTL, serialized)
            return True
        except Exception as e:
            self.logger.error(f"Error caching session state for {session_id}: {e}")
            return False

    async def get_session_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Получение состояния сессии"""
        try:
            state_key = f"{self.SESSION_STATE_PREFIX}{session_id}"
            cached_data = await self.redis_client.get(state_key)

            if cached_data:
                state = json.loads(cached_data)
                # Проверяем свежесть
                updated_at = datetime.fromisoformat(state.get('updated_at', ''))
                if datetime.utcnow() - updated_at < timedelta(seconds=self.SESSION_TTL):
                    state.pop('updated_at', None)
                    return state
                else:
                    await self.redis_client.delete(state_key)

            return None

        except Exception as e:
            self.logger.error(f"Error getting session state for {session_id}: {e}")
            return None

    async def extend_session(self, session_id: str, additional_ttl: Optional[int] = None) -> bool:
        """Продление срока действия сессии"""
        try:
            session_key = f"{self.SESSION_PREFIX}{session_id}"
            session = await self.get_session(session_id)

            if session:
                new_ttl = additional_ttl or self.SESSION_TTL
                await self.redis_client.expire(session_key, new_ttl)

                # Также продляем связанные данные
                await self.redis_client.expire(f"{self.SESSION_DATA_PREFIX}{session_id}", new_ttl)
                await self.redis_client.expire(f"{self.SESSION_STATE_PREFIX}{session_id}", new_ttl)

                self.logger.info(f"Extended session {session_id} for {new_ttl} seconds")
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error extending session {session_id}: {e}")
            return False

    def _is_session_valid(self, session_data: Dict[str, Any]) -> bool:
        """Проверка валидности сессии"""
        try:
            last_activity = datetime.fromisoformat(session_data.get('last_activity', ''))
            max_inactive = timedelta(minutes=30)  # 30 минут бездействия

            return datetime.utcnow() - last_activity < max_inactive

        except Exception:
            return False

    async def get_session_stats(self) -> Dict[str, Any]:
        """Получение статистики сессий"""
        try:
            stats = {
                'total_sessions': 0,
                'active_sessions': 0,
                'inactive_sessions': 0
            }

            # Получаем все ключи сессий
            session_keys = await self.redis_client.keys(f"{self.SESSION_PREFIX}*")
            stats['total_sessions'] = len(session_keys)

            # Проверяем активность каждой сессии
            for key in session_keys:
                session_id = key.decode('utf-8').replace(self.SESSION_PREFIX, '')
                session = await self.get_session(session_id)
                if session and session.get('is_active'):
                    stats['active_sessions'] += 1
                else:
                    stats['inactive_sessions'] += 1

            return stats

        except Exception as e:
            self.logger.error(f"Error getting session stats: {e}")
            return {}
