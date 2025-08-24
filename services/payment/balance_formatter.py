"""
BalanceFormatter - специализированный сервис для форматирования сообщений о балансе

🎯 Основные возможности:
- Централизованное форматирование балансовых сообщений
- Единые шаблоны и константы
- Опциональная интеграция с MessageFormatter
- Fallback сообщения при ошибках

📊 Архитектура:
- Чистое разделение ответственности (SRP)
- Dependency Injection для MessageFormatter
- Консистентность интерфейса
- Graceful degradation при отсутствии зависимостей
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from utils.message_formatter import MessageFormatter


class BalanceFormatter:
    """
    Сервис форматирования сообщений о балансе

    🚀 Принципы:
    - Единая ответственность: только форматирование
    - Опциональная зависимость от MessageFormatter
    - Чистые методы без бизнес-логики
    """

    def __init__(self, message_formatter: Optional[MessageFormatter] = None):
        """
        Args:
            message_formatter: Опциональный MessageFormatter для продвинутого форматирования
        """
        self.message_formatter = message_formatter
        self.logger = logging.getLogger(f"{__name__}.BalanceFormatter")

    async def get_balance_message(self, user_id: int, balance_data: Optional[Dict[str, Any]] = None) -> str:
        """
        Получение отформатированного сообщения о балансе пользователя

        Args:
            user_id: ID пользователя
            balance_data: Данные баланса (опционально)

        Returns:
            Отформатированное сообщение
        """
        try:
            if not self.message_formatter:
                # Fallback к простому сообщению
                balance = balance_data.get("balance", 0) if balance_data else 0
                return f"💰 <b>Ваш баланс:</b> {balance} TON"

            # Используем MessageFormatter для форматирования
            if balance_data:
                # Получаем последние транзакции для отображения
                transactions = balance_data.get("transactions", [])
                if transactions:
                    # Берем самую последнюю транзакцию
                    last_transaction = transactions[0]
                    balance_data["transactions_count"] = len(transactions)
                    balance_data["last_transaction"] = {
                        "type": last_transaction.get("transaction_type", "unknown"),
                        "amount": last_transaction.get("amount", 0),
                        "status": last_transaction.get("status", "unknown"),
                        "created_at": last_transaction.get("created_at", "")
                    }

                return self.message_formatter.format_balance(balance_data)
            else:
                return "❌ Ошибка получения данных баланса"

        except Exception as e:
            self.logger.error(f"Error getting balance message for user {user_id}: {e}")
            # Fallback сообщение
            try:
                balance = balance_data.get("balance", 0) if balance_data else 0
                return f"💰 <b>Ваш баланс:</b> {balance} TON"
            except:
                return "❌ Ошибка получения баланса"

    async def get_transaction_history_message(self,
                                            user_id: int,
                                            balance_history: Optional[Dict[str, Any]] = None,
                                            days: int = 30) -> str:
        """
        Получение отформатированного сообщения об истории транзакций

        Args:
            user_id: ID пользователя
            balance_history: История баланса с транзакциями
            days: Период в днях

        Returns:
            Отформатированное сообщение
        """
        try:
            if not self.message_formatter:
                # Fallback к простому сообщению
                if not balance_history or not balance_history.get("transactions"):
                    return "📊 <b>История транзакций:</b> Нет транзакций"

                transactions = balance_history["transactions"][:5]
                message = "📊 <b>История транзакций:</b>\n\n"

                for i, transaction in enumerate(transactions, 1):
                    amount = transaction.get("amount", 0)
                    trans_type = transaction.get("transaction_type", "unknown")
                    status = transaction.get("status", "unknown")

                    type_emoji = {"purchase": "🛒", "recharge": "📥", "refund": "↩️", "bonus": "🎁"}.get(trans_type, "❓")
                    message += f"{i}. {type_emoji} {amount} TON - {status}\n"

                return message

            # Используем MessageFormatter
            if balance_history:
                # Получаем текущий баланс для финального баланса
                current_balance = balance_history.get("final_balance", 0)

                # Формируем данные для MessageFormatter
                history_data = {
                    "initial_balance": balance_history.get("initial_balance", 0),
                    "final_balance": current_balance,
                    "transactions_count": balance_history.get("transactions_count", 0),
                    "period": f"{days} дней",
                    "transactions": balance_history.get("transactions", [])
                }

                return self.message_formatter.format_transaction_history(history_data)
            else:
                return "📊 <b>История транзакций:</b> Нет данных"

        except Exception as e:
            self.logger.error(f"Error getting transaction history message for user {user_id}: {e}")
            # Fallback сообщение
            try:
                if balance_history and balance_history.get("transactions"):
                    transactions = balance_history["transactions"][:5]
                    if transactions:
                        message = "📊 <b>История транзакций:</b>\n\n"
                        for i, transaction in enumerate(transactions, 1):
                            amount = transaction.get("amount", 0)
                            trans_type = transaction.get("transaction_type", "unknown")
                            message += f"{i}. {trans_type}: {amount} TON\n"
                        return message

                return "📊 <b>История транзакций:</b> Нет транзакций"
            except:
                return "❌ Ошибка получения истории транзакций"

    async def get_recharge_history_message(self, user_id: int, recharge_history: List[Dict[str, Any]]) -> str:
        """
        Получение отформатированного сообщения об истории пополнений

        Args:
            user_id: ID пользователя
            recharge_history: История пополнений

        Returns:
            Отформатированное сообщение
        """
        try:
            if not recharge_history:
                return "📥 <b>История пополнений:</b> Нет пополнений"

            message = "📥 <b>История пополнений баланса:</b>\n\n"
            for i, recharge in enumerate(recharge_history, 1):
                amount = recharge.get("amount", 0)
                currency = recharge.get("currency", "TON")
                status = recharge.get("status", "unknown")
                created_at = recharge.get("created_at", "")

                # Форматируем дату
                if created_at:
                    try:
                        dt = datetime.fromisoformat(created_at)
                        date_str = dt.strftime("%d.%m.%Y %H:%M")
                    except:
                        date_str = created_at[:10] if created_at else "Неизвестно"
                else:
                    date_str = "Неизвестно"

                status_emoji = {"completed": "✅", "pending": "⏳", "failed": "❌"}.get(status, "❓")
                message += f"{i}. {status_emoji} {amount} {currency} - {date_str}\n"

            return message

        except Exception as e:
            self.logger.error(f"Error getting recharge history message for user {user_id}: {e}")
            return "❌ Ошибка получения истории пополнений"

    async def get_purchase_history_message(self, user_id: int, purchase_history: Dict[str, Any]) -> str:
        """
        Получение отформатированного сообщения об истории покупок

        Args:
            user_id: ID пользователя
            purchase_history: История покупок с балансом

        Returns:
            Отформатированное сообщение
        """
        try:
            current_balance = purchase_history.get("current_balance", 0)
            purchases = purchase_history.get("purchase_history", [])
            total_purchases = purchase_history.get("total_purchases", 0)

            if not purchases:
                return f"🛒 <b>История покупок:</b> Нет покупок\n💰 <b>Текущий баланс:</b> {current_balance} TON"

            message = f"🛒 <b>История покупок:</b> {total_purchases} покупок\n💰 <b>Текущий баланс:</b> {current_balance} TON\n\n"

            for i, purchase in enumerate(purchases[:5], 1):  # Показываем только 5 последних
                amount = purchase.get("amount", 0)
                currency = purchase.get("currency", "TON")
                created_at = purchase.get("created_at", "")

                # Форматируем дату
                if created_at:
                    try:
                        dt = datetime.fromisoformat(created_at)
                        date_str = dt.strftime("%d.%m.%Y %H:%M")
                    except:
                        date_str = created_at[:10] if created_at else "Неизвестно"
                else:
                    date_str = "Неизвестно"

                message += f"{i}. 🛒 {amount} {currency} - {date_str}\n"

            if len(purchases) > 5:
                message += f"\n... и ещё {len(purchases) - 5} покупок"

            return message

        except Exception as e:
            self.logger.error(f"Error getting purchase history message for user {user_id}: {e}")
            return f"❌ Ошибка получения истории покупок\n💰 <b>Текущий баланс:</b> {purchase_history.get('current_balance', 0)} TON"

    def format_balance_change(self, old_balance: float, new_balance: float, operation: str) -> str:
        """
        Форматирование изменения баланса

        Args:
            old_balance: Старый баланс
            new_balance: Новый баланс
            operation: Тип операции

        Returns:
            Отформатированное сообщение об изменении
        """
        try:
            change = new_balance - old_balance
            if change > 0:
                return f"📈 Баланс увеличен на {change} TON (+{operation})"
            elif change < 0:
                return f"📉 Баланс уменьшен на {abs(change)} TON (-{operation})"
            else:
                return f"📊 Баланс не изменился ({operation})"
        except Exception as e:
            self.logger.error(f"Error formatting balance change: {e}")
            return "📊 Изменение баланса"