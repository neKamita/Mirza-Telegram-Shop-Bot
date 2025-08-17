"""
MessageFormatter класс для единообразного форматирования данных в телеграм-боте

Предоставляет централизованные методы для форматирования различных типов данных
с использованием HTML форматирования и унифицированной структуры сообщений.
"""
import re
import html
from typing import Dict, Any, Optional, Union, List
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from utils.message_templates import MessageTemplate


class MessageFormatter:
    """
    Класс для единообразного форматирования данных в телеграм-боте.
    
    Предоставляет методы для форматирования баланса, платежей, покупок,
    истории транзакций, а также утилиты для валидации и очистки данных.
    Следует принципам SOLID, DRY, KISS и обеспечивает безопасность.
    """

    # Константы валидации
    MAX_AMOUNT = 1000000.0
    MIN_AMOUNT = 0.01
    MAX_TEXT_LENGTH = 4096
    CURRENCY_SYMBOLS = {'TON', 'USD', 'EUR', 'RUB', 'KZT'}
    
    # Шаблоны для валидации
    AMOUNT_PATTERN = r'^\d+(\.\d{1,2})?$'
    TIMESTAMP_PATTERN = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$'
    
    def __init__(self):
        """Инициализация MessageFormatter"""
        self.logger = None  # Будет установлен при интеграции с логгером

    def format_balance(self, balance_data: Dict[str, Any]) -> str:
        """
        Форматирование баланса и истории транзакций.
        
        Args:
            balance_data: Словарь с данными о балансе
                - balance: Текущий баланс
                - currency: Валюта
                - source: Источник баланса
                - transactions_count: Количество транзакций (опционально)
                - last_transaction: Последняя транзакция (опционально)
                
        Returns:
            str: Отформатированное сообщение с HTML
        """
        try:
            # Валидация входных данных
            if not self.validate_amount(balance_data.get('balance', 0)):
                raise ValueError("Некорректный баланс")
                
            balance = float(balance_data.get('balance', 0))
            currency = balance_data.get('currency', 'TON')
            source = balance_data.get('source', 'unknown')
            transactions_count = balance_data.get('transactions_count', 0)
            last_transaction = balance_data.get('last_transaction', {})
            
            # Форматирование основного сообщения
            message = (
                f"{MessageTemplate.EMOJI_BALANCE} <b>Ваш баланс</b> {MessageTemplate.EMOJI_BALANCE}\n\n"
                f"💰 <b>Текущий баланс:</b> {self.format_amount(balance, currency)}\n"
                f"📊 <i>Источник: {self.sanitize_text(source)}</i>\n"
            )
            
            # Добавление информации о транзакциях
            if transactions_count > 0:
                message += f"📈 <i>Транзакций: {transactions_count}</i>\n"
                
                if last_transaction:
                    last_amount = last_transaction.get('amount', 0)
                    last_type = last_transaction.get('type', 'unknown')
                    last_status = last_transaction.get('status', 'unknown')
                    last_date = last_transaction.get('created_at', '')
                    
                    if last_date:
                        formatted_date = self.format_timestamp(last_date)
                        message += f"🔄 <i>Последняя: {self._format_transaction_type(last_type)} "
                        message += f"{self.format_amount(abs(last_amount), currency)} - "
                        message += f"{self._format_transaction_status(last_status)} {formatted_date}</i>\n"
            
            message += f"\n💡 <i>Используйте звезды для различных функций внутри бота!</i>\n"
            message += f"💎 <i>Каждая звезда имеет ценность!</i>"
            
            return self._validate_message_length(message)
            
        except Exception as e:
            self._log_error(f"Ошибка форматирования баланса: {e}")
            return self._format_error_message("Не удалось отформатировать баланс")

    def format_payment(self, payment_data: Dict[str, Any]) -> str:
        """
        Форматирование информации о платежах.
        
        Args:
            payment_data: Словарь с данными о платеже
                - amount: Сумма платежа
                - currency: Валюта
                - status: Статус платежа
                - payment_id: ID платежа
                - created_at: Дата создания
                - description: Описание платежа (опционально)
                
        Returns:
            str: Отформатированное сообщение с HTML
        """
        try:
            # Валидация входных данных
            if not self.validate_amount(payment_data.get('amount', 0)):
                raise ValueError("Некорректная сумма платежа")
                
            amount = float(payment_data.get('amount', 0))
            currency = payment_data.get('currency', 'TON')
            status = payment_data.get('status', 'unknown')
            payment_id = payment_data.get('payment_id', '')
            created_at = payment_data.get('created_at', '')
            description = payment_data.get('description', '')
            
            # Форматирование статуса
            status_line = self._format_payment_status(status)
            
            # Формирование сообщения
            message = f"{status_line}\n"
            message += f"💰 <b>Сумма:</b> {self.format_amount(amount, currency)}\n"
            
            if payment_id:
                message += f"🔢 <b>ID платежа:</b> {self.sanitize_text(payment_id)}\n"
                
            if created_at:
                formatted_date = self.format_timestamp(created_at)
                message += f"📅 <b>Дата:</b> {formatted_date}\n"
                
            if description:
                message += f"📝 <b>Описание:</b> {self.sanitize_text(description)}\n"
            
            return self._validate_message_length(message)
            
        except Exception as e:
            self._log_error(f"Ошибка форматирования платежа: {e}")
            return self._format_error_message("Не удалось отформатировать информацию о платеже")

    def format_purchase(self, purchase_data: Dict[str, Any]) -> str:
        """
        Форматирование информации о покупках.
        
        Args:
            purchase_data: Словарь с данными о покупке
                - stars_count: Количество звезд
                - amount: Сумма покупки
                - currency: Валюта
                - status: Статус покупки
                - purchase_id: ID покупки
                - created_at: Дата создания
                - payment_method: Способ оплаты (опционально)
                
        Returns:
            str: Отформатированное сообщение с HTML
        """
        try:
            # Валидация входных данных
            stars_count = int(purchase_data.get('stars_count', 0))
            if stars_count <= 0:
                raise ValueError("Некорректное количество звезд")
                
            amount = float(purchase_data.get('amount', 0))
            if not self.validate_amount(amount):
                raise ValueError("Некорректная сумма покупки")
                
            currency = purchase_data.get('currency', 'TON')
            status = purchase_data.get('status', 'unknown')
            purchase_id = purchase_data.get('purchase_id', '')
            created_at = purchase_data.get('created_at', '')
            payment_method = purchase_data.get('payment_method', '')
            
            # Форматирование статуса
            status_line = self._format_payment_status(status)
            
            # Формирование сообщения
            message = (
                f"{MessageTemplate.EMOJI_STAR} <b>Покупка звезд</b> {MessageTemplate.EMOJI_STAR}\n\n"
                f"{status_line}\n"
                f"⭐ <b>Куплено звезд:</b> {stars_count}\n"
                f"💰 <b>Сумма:</b> {self.format_amount(amount, currency)}\n"
            )
            
            if purchase_id:
                message += f"🔢 <b>ID покупки:</b> {self.sanitize_text(purchase_id)}\n"
                
            if created_at:
                formatted_date = self.format_timestamp(created_at)
                message += f"📅 <b>Дата:</b> {formatted_date}\n"
                
            if payment_method:
                message += f"💳 <b>Способ оплаты:</b> {self.sanitize_text(payment_method)}\n"
            
            message += f"\n🌟 <i>Спасибо за покупку!</i> 🌟\n"
            message += f"✨ Ваши звезды уже доступны для использования!"
            
            return self._validate_message_length(message)
            
        except Exception as e:
            self._log_error(f"Ошибка форматирования покупки: {e}")
            return self._format_error_message("Не удалось отформатировать информацию о покупке")

    def format_transaction_history(self, history_data: Dict[str, Any]) -> str:
        """
        Форматирование истории транзакций.
        
        Args:
            history_data: Словарь с данными истории
                - initial_balance: Начальный баланс
                - final_balance: Конечный баланс
                - transactions_count: Количество транзакций
                - period: Период (опционально)
                - transactions: Список транзакций
                
        Returns:
            str: Отформатированное сообщение с HTML
        """
        try:
            # Валидация входных данных
            initial_balance = float(history_data.get('initial_balance', 0))
            final_balance = float(history_data.get('final_balance', 0))
            transactions_count = int(history_data.get('transactions_count', 0))
            period = history_data.get('period', '')
            transactions = history_data.get('transactions', [])
            
            # Формирование заголовка
            message = (
                f"📊 <b>История транзакций</b> 📊\n\n"
                f"💰 <b>Начальный баланс:</b> {self.format_amount(initial_balance, 'TON')}\n"
                f"💰 <b>Текущий баланс:</b> {self.format_amount(final_balance, 'TON')}\n"
                f"📈 <b>Транзакций:</b> {transactions_count}\n"
            )
            
            if period:
                message += f"📅 <b>Период:</b> {self.sanitize_text(period)}\n"
            
            message += f"\n🔄 <b>Последние транзакции:</b>\n"
            
            # Форматирование транзакций
            for i, transaction in enumerate(transactions[:10], 1):  # Максимум 10 транзакций
                try:
                    transaction_type = transaction.get('type', 'unknown')
                    amount = float(transaction.get('amount', 0))
                    status = transaction.get('status', 'unknown')
                    created_at = transaction.get('created_at', '')
                    description = transaction.get('description', '')
                    
                    if created_at:
                        formatted_date = self.format_timestamp(created_at)
                    else:
                        formatted_date = "N/A"
                    
