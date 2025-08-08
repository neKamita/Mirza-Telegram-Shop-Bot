"""
Основной файл приложения - рефакторинг по SOLID принципам
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.methods import DeleteWebhook

from config.settings import settings
from repositories.user_repository import UserRepository
from services.payment_service import PaymentService
from handlers.message_handler import MessageHandler


async def init_database():
    """Инициализация базы данных"""
    user_repository = UserRepository(database_url=settings.database_url)
    await user_repository.create_tables()


async def main():
    """Основная функция приложения"""
    # Настройка логирования
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Инициализация компонентов
    user_repository = UserRepository(database_url=settings.database_url)
    payment_service = PaymentService(
        merchant_uuid=settings.merchant_uuid,
        api_key=settings.api_key
    )

    # Инициализация обработчиков
    message_handler = MessageHandler(
        user_repository=user_repository,
        payment_service=payment_service
    )

    # Инициализация бота и диспетчера
    bot = Bot(token=settings.telegram_token)
    dp = Dispatcher()

    # Регистрация обработчиков
    message_handler.register_handlers(dp)

    # Инициализация базы данных
    await init_database()
    logging.info("Database initialized successfully")

    # Запуск бота
    await bot(DeleteWebhook(drop_pending_updates=True))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
