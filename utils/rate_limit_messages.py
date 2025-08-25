"""
Сообщения для уведомления пользователей о rate limiting
"""
from typing import Dict, Any, Optional


class RateLimitMessages:
    """Класс для генерации сообщений о превышении лимитов запросов"""
    
    @staticmethod
    def get_rate_limit_message(limit_type: str, remaining_time: Optional[int] = None, for_callback: bool = False) -> str:
        """
        Получение сообщения о превышении rate limit
        
        Args:
            limit_type: Тип лимита (message, operation, payment)
            remaining_time: Оставшееся время до сброса лимита в секундах
            
        Returns:
            Отформатированное сообщение
        """
        base_messages = {
            "message": {
                "title": "🚫 Слишком быстро!",
                "description": "Пожалуйста, нажимайте кнопки медленнее",
                "icon": "⏱️"
            },
            "operation": {
                "title": "⏳ Подождите немного",
                "description": "Слишком много операций за короткое время",
                "icon": "🔄"
            },
            "payment": {
                "title": "💳 Ограничение платежей",
                "description": "Превышен лимит платежных операций",
                "icon": "💰"
            }
        }
        
        message_config = base_messages.get(limit_type, base_messages["message"])
        
        time_text = ""
        if remaining_time:
            if remaining_time < 60:
                time_text = f"⏰ Попробуйте через {remaining_time} сек."
            else:
                minutes = remaining_time // 60
                time_text = f"⏰ Попробуйте через {minutes} мин."
        else:
            time_text = "⏰ Попробуйте через минуту"
        
        if for_callback:
            # Версия без HTML тегов для callback.answer()
            return (
                f"{message_config['icon']} {message_config['title']}\n\n"
                f"📝 {message_config['description']}\n\n"
                f"{time_text}\n\n"
                f"💡 Это защищает сервис от перегрузки"
            )
        else:
            # Версия с HTML тегами для обычных сообщений
            return (
                f"{message_config['icon']} <b>{message_config['title']}</b>\n\n"
                f"📝 <i>{message_config['description']}</i>\n\n"
                f"{time_text}\n\n"
                f"💡 <i>Это защищает сервис от перегрузки</i>"
            )
    
    @staticmethod
    def get_rate_limit_info_message(current_limits: Dict[str, Any]) -> str:
        """
        Получение информационного сообщения о текущих лимитах
        
        Args:
            current_limits: Словарь с информацией о лимитах
            
        Returns:
            Информационное сообщение
        """
        return (
            f"📊 <b>Информация о лимитах</b>\n\n"
            f"💬 <b>Сообщения:</b> {current_limits.get('message_limit', 10)} в минуту\n"
            f"🔄 <b>Операции:</b> {current_limits.get('operation_limit', 5)} в минуту\n"
            f"💳 <b>Платежи:</b> {current_limits.get('payment_limit', 2)} в минуту\n\n"
            f"⚡ <i>Лимиты сбрасываются каждую минуту</i>\n"
            f"🛡️ <i>Это обеспечивает стабильную работу бота</i>"
        )