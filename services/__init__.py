"""
Сервисный слой - бизнес логика

Организация по модулям:
- cache/ - сервисы кеширования
- payment/ - платежные сервисы
- webhooks/ - вебхук сервисы
- infrastructure/ - инфраструктурные сервисы
- fragment/ - Fragment API сервисы
"""

# Импорты для обратной совместимости - все сервисы доступны на верхнем уровне
from .cache import UserCache, PaymentCache, RateLimitCache, SessionCache
from .payment import PaymentService, StarPurchaseService, BalanceService
from .webhooks import WebhookHandler
from .infrastructure import HealthService, CircuitBreaker, WebSocketService, FragmentCookieManager
from .fragment import FragmentService

# Экспорт всех сервисов для удобства импорта
__all__ = [
    # Cache services
    'UserCache',
    'PaymentCache',
    'RateLimitCache',
    'SessionCache',

    # Payment services
    'PaymentService',
    'StarPurchaseService',
    'BalanceService',

    # Webhook services
    'WebhookHandler',

    # Infrastructure services
    'HealthService',
    'CircuitBreaker',
    'WebSocketService',
    'FragmentCookieManager',

    # Fragment services
    'FragmentService'
]
