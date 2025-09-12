#!/bin/bash

# Redis Cluster Slot Monitor - локальная версия для тестирования
# Автоматически отправляет алерты при проблемах с покрытием слотов

LOG_FILE="./redis-cluster-slots.log"
ALERT_THRESHOLD=16384  # Всего слотов в Redis Cluster
WARNING_THRESHOLD=16000  # Порог для предупреждения
REDIS_PASSWORD="root123"

# Функция для отправки алерта
send_alert() {
    local message="$1"
    local level="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
    
    # Здесь можно добавить интеграцию с системами мониторинга:
    # - Telegram бот
    # - Slack webhook
    # - Email уведомления
    # - PagerDuty/OpsGenie
    
    # Пример для Telegram (раскомментировать при настройке):
    # if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
    #     curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    #         -d chat_id="${TELEGRAM_CHAT_ID}" \
    #         -d text="[Redis Cluster Alert $level] $message" \
    #         >/dev/null 2>&1
    # fi
    
    echo "ALERT: $message"
}

# Функция проверки покрытия слотов
check_slot_coverage() {
    echo "=== Проверка покрытия слотов Redis Cluster - $(date) ==="
    
    # Получаем информацию о кластере
    cluster_info=$(redis-cli --cluster check localhost:7379 -a "${REDIS_PASSWORD}" 2>/dev/null)
    
    if [ $? -ne 0 ]; then
        send_alert "Не удалось получить информацию о кластере Redis" "CRITICAL"
        return 1
    fi
    
    # Извлекаем информацию о покрытии слотов
    slots_covered=$(echo "$cluster_info" | grep -oP '\[OK\] All \K[0-9]+ slots covered' | cut -d' ' -f1)
    cluster_state=$(echo "$cluster_info" | grep -oP 'cluster_state:\K[^ ]+')
    
    if [ -z "$slots_covered" ]; then
        # Альтернативный метод проверки покрытия слотов
        slots_covered=$(echo "$cluster_info" | grep -A5 "Slot coverage" | grep -oP '[0-9]+/[0-9]+' | cut -d'/' -f1)
    fi
    
    echo "Состояние кластера: $cluster_state"
    echo "Покрыто слотов: ${slots_covered:-0}/$ALERT_THRESHOLD"
    
    # Проверяем покрытие слотов
    if [ -n "$slots_covered" ] && [ "$slots_covered" -eq "$ALERT_THRESHOLD" ]; then
        echo "✓ Все слоты покрыты (16384/16384)"
    elif [ -n "$slots_covered" ] && [ "$slots_covered" -ge "$WARNING_THRESHOLD" ]; then
        send_alert "Частичное покрытие слотов: $slots_covered/$ALERT_THRESHOLD" "WARNING"
    elif [ -n "$slots_covered" ]; then
        send_alert "КРИТИЧЕСКОЕ состояние: покрыто только $slots_covered/$ALERT_THRESHOLD слотов" "CRITICAL"
    else
        send_alert "Не удалось определить покрытие слотов" "ERROR"
    fi
    
    # Проверяем состояние каждой ноды
    echo ""
    echo "=== Проверка состояния нод ==="
    
    nodes=("localhost:7379" "localhost:7380" "localhost:7381" "localhost:7382" "localhost:7383" "localhost:7384")
    
    for node in "${nodes[@]}"; do
        host="${node%:*}"
        port="${node#*:}"
        
        if redis-cli -h "$host" -p "$port" -a "${REDIS_PASSWORD}" ping >/dev/null 2>&1; then
            node_info=$(redis-cli -h "$host" -p "$port" -a "${REDIS_PASSWORD}" cluster info 2>/dev/null)
            node_state=$(echo "$node_info" | grep -oP 'cluster_state:\K[^ ]+' || echo "unknown")
            echo "✓ $node: доступна, состояние: $node_state"
        else
            send_alert "Нода $node недоступна" "CRITICAL"
            echo "✗ $node: недоступна"
        fi
    done
    
    # Дополнительная проверка репликации
    echo ""
    echo "=== Проверка репликации ==="
    replication_info=$(redis-cli -h localhost -p 7379 -a "${REDIS_PASSWORD}" info replication 2>/dev/null)
    if [ $? -eq 0 ]; then
        connected_slaves=$(echo "$replication_info" | grep -oP 'connected_slaves:\K[0-9]+')
        echo "Подключенные реплики: $connected_slaves"
        
        if [ "$connected_slaves" -lt 3 ]; then
            send_alert "Мало подключенных реплики: $connected_slaves/3" "WARNING"
        fi
    fi
}

# Основной цикл мониторинга
echo "Starting Redis Cluster Slot Monitor (Local)..."
echo "Log file: $LOG_FILE"

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running slot coverage check..."
    check_slot_coverage
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Check completed. Waiting for 2 minutes..."
    echo "=========================================="
    sleep 120
done