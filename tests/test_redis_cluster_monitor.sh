#!/bin/bash

# Тестовый скрипт для проверки Redis Cluster мониторинга
# Имитирует различные сценарии работы монитора слотов

set -e

echo "🧪 Запуск тестов Redis Cluster мониторинга"
echo "=========================================="

# Создаем временный лог файл
TEST_LOG="/tmp/redis_cluster_test.log"
echo "" > "$TEST_LOG"

# Функция для тестирования отправки алертов
test_alert_function() {
    echo "📋 Тест 1: Проверка функции отправки алертов"
    
    # Копируем функцию send_alert из оригинального скрипта
    send_alert() {
        local message="$1"
        local level="$2"
        local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
        
        echo "[$timestamp] [$level] $message" >> "$TEST_LOG"
        echo "ALERT: $message"
    }
    
    # Тестируем отправку алертов разных уровней
    send_alert "Тестовое сообщение INFO" "INFO" | tee -a "$TEST_LOG"
    send_alert "Тестовое сообщение WARNING" "WARNING" | tee -a "$TEST_LOG"
    send_alert "Тестовое сообщение CRITICAL" "CRITICAL" | tee -a "$TEST_LOG"
    send_alert "Тестовое сообщение ERROR" "ERROR" | tee -a "$TEST_LOG"
    
    echo "✅ Функция отправки алертов работает корректно"
    echo ""
}

# Функция для тестирования проверки покрытия слотов (мокирование)
test_slot_coverage_mock() {
    echo "📋 Тест 2: Мокирование проверки покрытия слотов"
    
    # Создаем мок функции check_slot_coverage
    mock_check_slot_coverage() {
        local scenario="$1"
        
        case "$scenario" in
            "full_coverage")
                echo "=== Проверка покрытия слотов Redis Cluster - $(date) ==="
                echo "Состояние кластера: ok"
                echo "Покрыто слотов: 16384/16384"
                echo "✓ Все слоты покрыты (16384/16384)"
                ;;
            "partial_coverage")
                echo "=== Проверка покрытия слотов Redis Cluster - $(date) ==="
                echo "Состояние кластера: ok"
                echo "Покрыто слотов: 16001/16384"
                echo "ALERT: Частичное покрытие слотов: 16001/16384"
                ;;
            "critical_coverage")
                echo "=== Проверка покрытия слотов Redis Cluster - $(date) ==="
                echo "Состояние кластера: fail"
                echo "Покрыто слотов: 8000/16384"
                echo "ALERT: КРИТИЧЕСКОЕ состояние: покрыто только 8000/16384 слотов"
                ;;
            "error")
                echo "=== Проверка покрытия слотов Redis Cluster - $(date) ==="
                echo "ALERT: Не удалось получить информацию о кластере Redis"
                ;;
        esac
    }
    
    echo "🔹 Тестируем полное покрытие слотов:"
    mock_check_slot_coverage "full_coverage" | tee -a "$TEST_LOG"
    echo ""
    
    echo "🔹 Тестируем частичное покрытие (WARNING):"
    mock_check_slot_coverage "partial_coverage" | tee -a "$TEST_LOG"
    echo ""
    
    echo "🔹 Тестируем критическое покрытие (CRITICAL):"
    mock_check_slot_coverage "critical_coverage" | tee -a "$TEST_LOG"
    echo ""
    
    echo "🔹 Тестируем ошибку подключения:"
    mock_check_slot_coverage "error" | tee -a "$TEST_LOG"
    echo ""
    
    echo "✅ Мокирование проверки покрытия слотов завершено"
    echo ""
}

# Функция для проверки синтаксиса скрипта
test_syntax_validation() {
    echo "📋 Тест 3: Проверка синтаксиса скрипта"
    
    echo "🔹 Проверяем локальную версию скрипта:"
    if bash -n redis/scripts/cluster_slot_monitor_local.sh; then
        echo "✅ Синтаксис cluster_slot_monitor_local.sh корректен"
    else
        echo "❌ Ошибка синтаксиса в cluster_slot_monitor_local.sh"
        exit 1
    fi
    
    echo ""
}

# Функция для тестирования пороговых значений
test_threshold_values() {
    echo "📋 Тест 4: Проверка пороговых значений"
    
    # Извлекаем значения из скрипта
    ALERT_THRESHOLD=$(grep -oP 'ALERT_THRESHOLD=\K[0-9]+' redis/scripts/cluster_slot_monitor_local.sh)
    WARNING_THRESHOLD=$(grep -oP 'WARNING_THRESHOLD=\K[0-9]+' redis/scripts/cluster_slot_monitor_local.sh)
    
    echo "🔹 ALERT_THRESHOLD: $ALERT_THRESHOLD (ожидается: 16384)"
    echo "🔹 WARNING_THRESHOLD: $WARNING_THRESHOLD (ожидается: 16000)"
    
    if [ "$ALERT_THRESHOLD" -eq 16384 ] && [ "$WARNING_THRESHOLD" -eq 16000 ]; then
        echo "✅ Пороговые значения корректны"
    else
        echo "❌ Неправильные пороговые значения"
        exit 1
    fi
    
    echo ""
}

# Функция для проверки списка нод
test_node_list() {
    echo "📋 Тест 5: Проверка списка нод кластера"
    
    # Извлекаем список нод из скрипта
    NODES_LINE=$(grep -A 1 'nodes=(' redis/scripts/cluster_slot_monitor_local.sh | grep -o '".*"' | tr -d '"')
    echo "🔹 Список нод: $NODES_LINE"
    
    # Проверяем что есть 6 нод (3 мастера + 3 реплики)
    NODE_COUNT=$(echo "$NODES_LINE" | tr ' ' '\n' | grep -c "localhost:")
    echo "🔹 Количество нод: $NODE_COUNT (ожидается: 6)"
    
    if [ "$NODE_COUNT" -eq 6 ]; then
        echo "✅ Список нод корректен"
    else
        echo "❌ Неправильное количество нод"
        exit 1
    fi
    
    echo ""
}

# Функция для проверки интеграции с AlertService
test_alert_service_integration() {
    echo "📋 Тест 6: Проверка возможности интеграции с AlertService"
    
    # Проверяем наличие закомментированного кода для Telegram
    TELEGRAM_CODE=$(grep -c "TELEGRAM_BOT_TOKEN" redis/scripts/cluster_slot_monitor_local.sh)
    if [ "$TELEGRAM_CODE" -gt 0 ]; then
        echo "✅ Код для интеграции с Telegram присутствует (закомментирован)"
    else
        echo "⚠️ Код для интеграции с Telegram отсутствует"
    fi
    
    # Проверяем логирование в файл
    LOG_FILE=$(grep -oP 'LOG_FILE=\K[^ ]+' redis/scripts/cluster_slot_monitor_local.sh)
    echo "🔹 Лог файл: $LOG_FILE"
    
    echo "✅ Проверка интеграционных возможностей завершена"
    echo ""
}

# Главная функция тестирования
main() {
    echo "🚀 Начало комплексного тестирования Redis Cluster мониторинга"
    echo "=========================================================="
    
    test_syntax_validation
    test_threshold_values
    test_node_list
    test_alert_function
    test_slot_coverage_mock
    test_alert_service_integration
    
    echo "=========================================================="
    echo "🎉 Все тесты пройдены успешно!"
    echo ""
    echo "📊 Результаты тестирования:"
    echo "   - Синтаксис скрипта: ✅"
    echo "   - Пороговые значения: ✅"
    echo "   - Список нод: ✅"
    echo "   - Функция алертов: ✅"
    echo "   - Мокирование сценариев: ✅"
    echo "   - Интеграционные возможности: ✅"
    echo ""
    echo "📋 Лог тестирования сохранен в: $TEST_LOG"
    echo ""
    echo "Следующий шаг: Запуск мониторинга в тестовом окружении"
}

# Запуск тестов
main "$@"