"""
Утилиты для безопасного редактирования сообщений Telegram
"""
import logging
from typing import Union, Optional, Any

from aiogram.types import Message, CallbackQuery, InaccessibleMessage
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

logger = logging.getLogger(__name__)


async def safe_edit_message(
    message: Union[Message, CallbackQuery, InaccessibleMessage, Any],
    text: str,
    reply_markup=None,
    parse_mode: str = "HTML",
    disable_web_page_preview: Optional[bool] = None,
    **kwargs
) -> bool:
    """
    Безопасное редактирование сообщения с расширенной обработкой ошибок

    Args:
        message: Сообщение для редактирования (Message, CallbackQuery, InaccessibleMessage или другой объект)
        text: Новый текст сообщения
        reply_markup: Клавиатура (InlineKeyboardMarkup)
        parse_mode: Режим парсинга ("HTML", "Markdown", None)
        disable_web_page_preview: Отключить превью ссылок
        **kwargs: Дополнительные параметры для методов aiogram

    Returns:
        bool: True если редактирование удалось, False в противном случае
    """
    try:
        # Проверка на недоступное сообщение
        if isinstance(message, InaccessibleMessage):
            logger.warning("Attempted to edit InaccessibleMessage")
            return False

        # Обработка CallbackQuery
        if isinstance(message, CallbackQuery):
            logger.debug(f"Processing CallbackQuery edit for user {message.from_user.id if message.from_user else 'unknown'}")

            # Проверяем наличие связанного сообщения
            if not message.message:
                logger.warning("CallbackQuery has no associated message")
                await message.answer(text, show_alert=True)
                return True

            # Проверяем, что сообщение доступно для редактирования
            if isinstance(message.message, InaccessibleMessage):
                logger.warning("CallbackQuery message is InaccessibleMessage")
                await message.answer(text, show_alert=True)
                return True

            # Проверяем наличие метода edit_text
            if not hasattr(message.message, 'edit_text'):
                logger.warning("CallbackQuery message has no edit_text method")
                await message.answer(text, show_alert=True)
                return True

            # Попытка редактирования через CallbackQuery
            try:
                await message.message.edit_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview,
                    **kwargs
                )
                logger.debug("Successfully edited message via CallbackQuery")
                return True
            except TelegramBadRequest as e:
                logger.error(f"BadRequest editing via CallbackQuery: {e}")
                # Попытка ответить через alert
                await message.answer(text, show_alert=True)
                return True
            except TelegramForbiddenError as e:
                logger.error(f"Forbidden error editing via CallbackQuery: {e}")
                return False
            except Exception as e:
                logger.error(f"Unexpected error editing via CallbackQuery: {e}")
                await message.answer(text, show_alert=True)
                return True

        # Обработка Message
        elif isinstance(message, Message):
            logger.debug(f"Processing Message edit for user {message.from_user.id if message.from_user else 'unknown'}")

            # Проверяем наличие метода edit_text
            if not hasattr(message, 'edit_text'):
                logger.warning("Message has no edit_text method, using answer")
                await message.answer(
                    text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview,
                    **kwargs
                )
                return True

            # Попытка редактирования через Message
            try:
                await message.edit_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview,
                    **kwargs
                )
                logger.debug("Successfully edited message via Message.edit_text")
                return True
            except TelegramBadRequest as e:
                logger.error(f"BadRequest editing message: {e}")
                # Попытка ответить новым сообщением
                await message.answer(
                    text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview,
                    **kwargs
                )
                return True
            except TelegramForbiddenError as e:
                logger.error(f"Forbidden error editing message: {e}")
                return False
            except Exception as e:
                logger.error(f"Unexpected error editing message: {e}")
                await message.answer(
                    text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview,
                    **kwargs
                )
                return True

        # Обработка объектов с методом answer (fallback)
        elif hasattr(message, 'answer'):
            logger.debug("Using fallback answer method")
            await message.answer(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
                **kwargs
            )
            return True

        # Неизвестный тип объекта
        else:
            logger.error(f"Unsupported message type: {type(message)}")
            return False

    except Exception as e:
        logger.error(f"Critical error in safe_edit_message: {e}", exc_info=True)
        return False