"""
Репозиторий для работы с пользователями через PostgreSQL (Neon)
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, insert, update
from typing import Dict, Any, Optional
from core.interfaces import DatabaseInterface
from sqlalchemy import Column, Integer, Boolean, DateTime, String
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from services.user_cache import UserCache

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    def __init__(self, database_url: str, user_cache: Optional[UserCache] = None):
        self.database_url = database_url
        self.user_cache = user_cache

class UserRepository(DatabaseInterface):
    """Репозиторий для управления пользователями через PostgreSQL"""

    def __init__(self, database_url: str, user_cache: Optional[UserCache] = None):
        self.database_url = database_url
        self.user_cache = user_cache
        self.engine = create_async_engine(
            database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True
        )
        self.async_session = sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

    async def create_tables(self) -> None:
        """Создание таблиц в базе данных"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def add_user(self, user_id: int) -> bool:
        """Добавление пользователя в базу данных"""
        async with self.async_session() as session:
            try:
                stmt = insert(User).values(user_id=user_id)
                await session.execute(stmt)
                # Инвалидируем кеш пользователя
                if self.user_cache:
                    await self.user_cache.invalidate_user_cache(user_id)
                await session.commit()
                return True
            except Exception:
                await session.rollback()
                return False

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение пользователя по ID с использованием Cache-Aside паттерна"""
        # Сначала пытаемся получить из кеша
        if self.user_cache:
            cached_user = await self.user_cache.get_user_profile(user_id)
            if cached_user:
                return cached_user

        # Если в кеше нет, получаем из базы данных
        async with self.async_session() as session:
            stmt = select(User).where(User.user_id == user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if user:
                user_data = {
                    "id": user.id,
                    "user_id": user.user_id,
                    "created_at": user.created_at
                }

                # Кешируем результат
                if self.user_cache:
                    await self.user_cache.cache_user_profile(user_id, user_data)

                return user_data
            return None



    async def user_exists(self, user_id: int) -> bool:
        """Проверка существования пользователя"""
        async with self.async_session() as session:
            stmt = select(User).where(User.user_id == user_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    async def get_all_users(self) -> list:
        """Получение всех пользователей"""
        async with self.async_session() as session:
            stmt = select(User.user_id)
            result = await session.execute(stmt)
            return [row[0] for row in result.fetchall()]
