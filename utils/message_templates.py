"""
Централизованные шаблоны сообщений для Telegram bot

Предоставляет унифицированные шаблоны сообщений с использованием HTML форматирования
и стандартных эмодзи для всех типов взаимодействия с пользователем.
"""
from typing import Dict, Any, Optional
from datetime import datetime


class MessageTemplate:
    """
    Класс для централизованных шаблонов сообщений телеграм-бота.
    
    Предоставляет унифицированные шаблоны с HTML форматированием и стандартными эмодзи
    для всех типов сообщений, заменяя дублирующийся код во всех обработчиках.
    """

    # Константы эмодзи для унификации
    EMOJI_UNKNOWN = "❓"
    EMOJI_SUCCESS = "✅"
    EMOJI_ERROR = "❌"
    EMOJI_PENDING = "⏳"
    EMOJI_INFO = "ℹ️"
    EMOJI_WARNING = "⚠️"
    EMOJI_NETWORK = "🌐"
    EMOJI_PAYMENT = "💳"
    EMOJI_BALANCE = "💰"
    EMOJI_STAR = "⭐"
    EMOJI_HELP = "❓"
    EMOJI_BACK = "⬅️"
    EMOJI_REFRESH = "🔄"
    EMOJI_HOME = "🏠"

    @classmethod
    def get_unknown_command(cls) -> str:
        """
        Получить шаблон сообщения для неизвестных команд.
        
        Returns:
            str: Отформатированное сообщение с HTML тегами
        """
        return (
            f"{cls.EMOJI_UNKNOWN} <b>Неизвестная команда</b> {cls.EMOJI_UNKNOWN}\n\n"
            f"🔍 <i>Пожалуйста, используйте доступные команды</i>\n\n"
            f"💡 <i>Введите /help для списка команд</i>\n\n"
            f"🤖 <i>Или используйте кнопки в меню</i>"
        )

    @classmethod
    def get_unknown_callback(cls) -> str:
        """
        Получить шаблон сообщения для неизвестных callback запросов.
        
        Returns:
            str: Отформатированное сообщение с HTML тегами
        """
        return (
            f"{cls.EMOJI_UNKNOWN} <b>Неизвестное действие</b> {cls.EMOJI_UNKNOWN}\n\n"
            f"🔍 <i>Пожалуйста, используйте доступные кнопки</i>\n\n"
            f"💡 <i>Введите /start для возврата в меню</i>"
        )

    @classmethod
    def get_payment_status(cls, status: str, amount: float = 0, 
                          payment_id: Optional[str] = None, 
                          currency: str = "TON") -> str:
        """
        Получить шаблон сообщения для форматирования статусов оплаты.
        
        Args:
            status: Статус оплаты ('pending', 'paid', 'failed', 'expired', 'cancelled', 'processing')
            amount: Сумма оплаты
            payment_id: ID платежа
            currency: Валюта оплаты
            
        Returns:
            str: Отформатированное сообщение с HTML тегами
        """
        status_line = cls._format_status(status)
        amount_line = f"💰 <b>Сумма:</b> {amount} {currency}\n"
        
        message = f"{status_line}\n"
        if amount > 0:
            message += f"{amount_line}"
        if payment_id:
            message += f"🔢 <b>ID платежа:</b> {payment_id}\n"
            
        return message

    @classmethod
    def get_error_message(cls, error_type: str = "unknown", 
                         context: Optional[Dict[str, Any]] = None) -> str:
        """
        Получить шаблон сообщения для сообщений об ошибках.
        
        Args:
            error_type: Тип ошибки ('network', 'payment', 'validation', 'system', 'unknown')
            context: Контекст ошибки с дополнительной информацией
            
        Returns:
            str: Отформатированное сообщение с HTML тегами
        """
        context = context or {}
        user_id = context.get('user_id', 'неизвестный')
        amount = context.get('amount', 0)
        payment_id = context.get('payment_id', 'неизвестен')
        error_detail = context.get('error', 'Неизвестная ошибка')
        
        error_templates = {
            'network': (
                f"{cls.EMOJI_NETWORK} <b>Проблемы с сетевым подключением</b> {cls.EMOJI_NETWORK}\n\n"
                f"🔍 <i>Не удалось подключиться к серверу оплаты</i>\n"
                f"📝 <i>Ошибка: {error_detail}</i>\n\n"
                f"🔄 <i><b>Рекомендуемые действия:</b></i>\n"
                f"   📡 <i>Проверьте интернет-соединение</i>\n"
                f"   🔄 <i>Попробуйте снова через 30 секунд</i>\n"
                f"   📱 <i>Переключитесь на другую сеть</i>\n\n"
                f"📞 <i>Если проблема сохраняется, обратитесь в поддержку</i>"
            ),
            'payment': (
                f"{cls.EMOJI_PAYMENT} <b>Ошибка платежной системы</b> {cls.EMOJI_ERROR}\n\n"
                f"🔍 <i>Проблема с обработкой платежа</i>\n"
                f"📝 <i>Ошибка: {error_detail}</i>\n"
                f"{cls.get_payment_status(context.get('status', 'unknown'), amount, payment_id)}\n\n"
                f"🔄 <i><b>Рекомендуемые действия:</b></i>\n"
                f"   ⏰ <i>Попробуйте снова через 5 минут</i>\n"
                f"   💳 <i>Используйте другой способ оплаты</i>\n\n"
                f"📞 <i>Если проблема сохраняется, обратитесь в поддержку</i>"
            ),
            'validation': (
                f"{cls.EMOJI_WARNING} <b>Ошибка валидации данных</b> {cls.EMOJI_WARNING}\n\n"
                f"🔍 <i>Некорректные данные для операции</i>\n"
                f"📝 <i>Ошибка: {error_detail}</i>\n"
                f"🔢 <i>Введенное значение: {amount}</i>\n\n"
                f"🔄 <i><b>Рекомендуемые действия:</b></i>\n"
                f"   ✅ <i>Проверьте введенные данные</i>\n"
                f"   📏 <i>Убедитесь, что сумма находится в допустимом диапазоне</i>\n\n"
                f"💡 <i>Введите /start для возврата в меню</i>"
            ),
            'system': (
                f"{cls.EMOJI_ERROR} <b>Системная ошибка</b> {cls.EMOJI_ERROR}\n\n"
                f"🔍 <i>Произошла внутренняя ошибка системы</i>\n"
                f"📝 <i>Ошибка: {error_detail}</i>\n"
                f"👤 <i>Пользователь: {user_id}</i>\n\n"
                f"🔄 <i><b>Рекомендуемые действия:</b></i>\n"
                f"   ⏰ <i>Попробуйте снова позже</i>\n"
                f"   🔄 <i>Обновите приложение или страницу</i>\n\n"
                f"📞 <i>Если проблема сохраняется, обратитесь в поддержку</i>"
            ),
            'unknown': (
                f"{cls.EMOJI_UNKNOWN} <b>Неизвестная ошибка</b> {cls.EMOJI_UNKNOWN}\n\n"
                f"🔍 <i>Произошла непредвиденная ошибка</i>\n"
                f"📝 <i>Ошибка: {error_detail}</i>\n"
                f"👤 <i>Пользователь: {user_id}</i>\n"
                f"{cls.get_payment_status(context.get('status', 'unknown'), amount, payment_id)}\n\n"
                f"🔄 <i><b>Рекомендуемые действия:</b></i>\n"
                f"   🔄 <i>Попробуйте снова</i>\n"
                f"   📱 <i>Перезапустите приложение</i>\n\n"
                f"📞 <i>Если проблема сохраняется, обратитесь в поддержку</i>"
            )
        }
        
        return error_templates.get(error_type.lower(), error_templates['unknown'])

    @classmethod
    def get_success_message(cls, operation: str = "operation", 
                          details: Optional[Dict[str, Any]] = None) -> str:
        """
        Получить шаблон сообщения для успешных операций.
        
        Args:
            operation: Описание выполненной операции
            details: Дополнительные детали операции
            
        Returns:
            str: Отформатированное сообщение с HTML тегами
        """
        details = details or {}
        amount = details.get('amount', 0)
        currency = details.get('currency', 'TON')
        payment_id = details.get('payment_id', '')
        
        message = (
            f"{cls.EMOJI_SUCCESS} <b>Опция успешно выполнена</b> {cls.EMOJI_SUCCESS}\n\n"
            f"✅ <i>{operation}</i>\n"
        )
        
        if amount > 0:
            message += f"💰 <i>Сумма: {amount} {currency}</i>\n"
        if payment_id:
            message += f"🔢 <i>ID операции: {payment_id}</i>\n"
            
        message += f"\n💡 <i>Введите /start для возврата в меню</i>"
        
        return message

    @classmethod
    def get_info_message(cls, title: str = "Информация", 
                        content: Optional[str] = None,
                        details: Optional[Dict[str, Any]] = None) -> str:
        """
        Получить шаблон сообщения для информационных сообщений.
        
        Args:
            title: Заголовок сообщения
            content: Основной контент сообщения
            details: Дополнительные детали
            
        Returns:
            str: Отформатированное сообщение с HTML тегами
        """
        details = details or {}
        amount = details.get('amount', 0)
        currency = details.get('currency', 'TON')
        payment_id = details.get('payment_id', '')
        
        message = f"{cls.EMOJI_INFO} <b>{title}</b> {cls.EMOJI_INFO}\n\n"
        
        if content:
            message += f"{content}\n\n"
            
        if amount > 0:
            message += f"💰 <i>Сумма: {amount} {currency}</i>\n"
        if payment_id:
            message += f"🔢 <i>ID: {payment_id}</i>\n"
            
        return message

    @classmethod
    def _format_status(cls, status: str) -> str:
        """
        Унифицированное форматирование статусов с эмодзи и HTML тегами.
        
        Args:
            status: Статус для форматирования
            
        Returns:
            str: Отформатированный статус
        """
        status_formats = {
            'pending': f"{cls.EMOJI_PENDING} <b>статус: pending</b>",
            'paid': f"{cls.EMOJI_SUCCESS} <b>статус: paid</b>",
            'failed': f"{cls.EMOJI_ERROR} <b>статус: failed</b>",
            'expired': f"⚪ <b>статус: expired</b>",
            'cancelled': f"{cls.EMOJI_ERROR} <b>статус: cancelled</b>",
            'processing': f"{cls.EMOJI_PENDING} <b>статус: processing</b>",
            'unknown': f"{cls.EMOJI_UNKNOWN} <b>статус: unknown</b>"
        }
        
        return status_formats.get(status.lower(), status_formats['unknown'])

    # Статические методы для часто используемых шаблонов

    @staticmethod
    def get_welcome_message() -> str:
        """
        Получить шаблон приветственного сообщения.
        
        Returns:
            str: Отформатированное приветственное сообщение
        """
        return (
            "🤖 <b>Добро пожаловать в StarBot!</b> 🤖\n\n"
            "🌟 <i>Ваш личный помощник для управления звездами и балансом</i>\n\n"
            "💰 <i>Проверяйте баланс, пополняйте счет и покупайте звезды</i>\n\n"
            "✨ <i>Каждая звезда открывает новые возможности!</i>\n\n"
            "🎯 <i>Выберите действие из меню ниже</i>"
        )

    @staticmethod
    def get_help_message() -> str:
        """
        Получить шаблон сообщения справки.
        
        Returns:
            str: Отформатированное сообщение справки
        """
        return (
            "🤖 <b>Помощь StarBot</b> 🤖\n\n"
            "📋 <i>Доступные команды:</i>\n\n"
            f"• <code>/start</code> - Главное меню\n"
            f"• <code>/balance</code> - Проверить баланс\n"
            f"• <code>/payment</code> - Пополнить баланс\n"
            f"• <code>/purchase</code> - Купить звезды\n"
            f"• <code>/help</code> - Эта справка\n\n"
            "💡 <i>Вы также можете использовать кнопки в меню для навигации</i>\n\n"
            "🔧 <i>Для поддержки: contact@example.com</i>"
        )

    @staticmethod
    def get_balance_message(balance: float = 0, 
                          currency: str = "TON") -> str:
        """
        Получить шаблон сообщения о балансе.
        
        Args:
            balance: Текущий баланс
            currency: Валюта баланса
            
        Returns:
            str: Отформатированное сообщение о балансе
        """
        return (
            f"{MessageTemplate.EMOJI_BALANCE} <b>Ваш баланс</b> {MessageTemplate.EMOJI_BALANCE}\n\n"
            f"💰 <i>Текущий баланс:</i> <b>{balance:.2f} {currency}</b>\n\n"
            f"💡 <i>Введите /start для возврата в меню</i>"
        )

    @staticmethod
    def get_purchase_menu_title() -> str:
        """
        Получить шаблон заголовка меню покупки звезд.
        
        Returns:
            str: Отформатированный заголовок меню
        """
        return (
            f"{MessageTemplate.EMOJI_STAR} <b>Покупка звезд</b> {MessageTemplate.EMOJI_STAR}\n\n"
            "🎯 <i>Выберите способ оплаты:</i>\n\n"
            f"💳 <i>Картой/Кошельком - оплата через Heleket</i>\n"
            f"💰 <i>С баланса - списание со счета</i>\n\n"
            f"✨ <i>Каждая звезда имеет ценность!</i>"
        )

    @staticmethod
    def get_payment_menu_title() -> str:
        """
        Получить шаблон заголовка меню платежей.
        
        Returns:
            str: Отформатированный заголовок меню
        """
        return (
            f"{MessageTemplate.EMOJI_PAYMENT} <b>Выберите сумму для пополнения</b> {MessageTemplate.EMOJI_PAYMENT}\n\n"
            "🎯 <i>Доступные варианты:</i>\n\n"
            f"💰 <i>10 {MessageTemplate.EMOJI_BALANCE} - Минимальное пополнение</i>\n"
            f"💰 <i>50 {MessageTemplate.EMOJI_BALANCE} - Стандартное пополнение</i>\n"
            f"💰 <i>100 {MessageTemplate.EMOJI_BALANCE} - Комфортное пополнение</i>\n"
            f"💰 <i>500 {MessageTemplate.EMOJI_BALANCE} - Максимальное пополнение</i>\n\n"
            f"✨ <i>Выберите удобную для вас сумму</i>"
        )