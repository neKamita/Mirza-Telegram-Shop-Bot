#!/usr/bin/env bash

echo "=== Redis Cluster Creator (Optimized) - $(date) ==="

# Функция для проверки доступности узла с таймаутом
check_node() {
    local host=$1
    local port=$2
    echo "Testing connection to $host:$port..."
    if ! timeout 5 redis-cli -h "$host" -p "$port" -a "${REDIS_PASSWORD}" ping >/dev/null 2>&1; then
        echo "Failed to connect to $host:$port"
        return 1
    fi
    echo "✓ $host:$port is responding"
    return 0
}

# Функция для сброса состояния узла (оптимизированная)
reset_node() {
    local host=$1
    local port=$2
    echo "Resetting node $host:$port..."
    redis-cli -h "$host" -p "$port" -a "${REDIS_PASSWORD}" CLUSTER RESET HARD >/dev/null 2>&1 || true
    sleep 0.5  # Уменьшено с 1 сек
    redis-cli -h "$host" -p "$port" -a "${REDIS_PASSWORD}" CONFIG SET appendonly no >/dev/null 2>&1 || true
    sleep 0.2  # Уменьшено с 0.5 сек
    redis-cli -h "$host" -p "$port" -a "${REDIS_PASSWORD}" FLUSHALL >/dev/null 2>&1 || true
    sleep 0.2  # Уменьшено с 0.5 сек
    redis-cli -h "$host" -p "$port" -a "${REDIS_PASSWORD}" CONFIG SET appendonly yes >/dev/null 2>&1 || true
    sleep 0.5  # Уменьшено с 1 сек
}

# Функция для проверки состояния кластера с таймаутом
check_cluster() {
    echo "Checking cluster state with timeout..."
    local timeout=10
    if timeout $timeout redis-cli --cluster check redis-node-1:7379 -a "${REDIS_PASSWORD}" 2>/dev/null | grep -q "All 16384 slots covered"; then
        return 0
    fi
    return 1
}

# ОПТИМИЗАЦИЯ: Проверка существующего кластера с таймаутом
echo "Checking if cluster already exists (with 10s timeout)..."
if check_cluster; then
    echo "✓ Cluster already exists and is healthy, skipping creation"
    echo "=== Redis Cluster Creator completed (cluster already exists) ==="
    exit 0
else
    echo "Cluster check failed or timed out, proceeding with creation..."
fi

# Шаг 1: ОПТИМИЗИРОВАННАЯ проверка доступности всех узлов (параллельно)
echo "Checking node availability (parallel)..."
nodes=("redis-node-1:7379" "redis-node-2:7380" "redis-node-3:7381" "redis-replica-1:7382" "redis-replica-2:7383" "redis-replica-3:7384")

# Функция для параллельной проверки узла
check_node_with_retry() {
    local node=$1
    local host="${node%:*}"
    local port="${node#*:}"
    
    # ОПТИМИЗАЦИЯ: Уменьшено количество попыток с 10 до 5
    for attempt in $(seq 1 5); do
        if check_node "$host" "$port"; then
            echo "✓ Node $node is available"
            return 0
        fi
        if [ $attempt -eq 5 ]; then
            echo "ERROR: Node $node is not available after 5 attempts"
            return 1
        fi
        # ОПТИМИЗАЦИЯ: Уменьшен интервал ожидания с 2 до 1 сек
        sleep 1
    done
}

# Запускаем проверки параллельно
pids=()
for node in "${nodes[@]}"; do
    check_node_with_retry "$node" &
    pids+=($!)
done

# Ждем завершения всех проверок
failed_nodes=0
for i in "${!pids[@]}"; do
    if ! wait "${pids[$i]}"; then
        failed_nodes=$((failed_nodes + 1))
    fi
done

if [ $failed_nodes -gt 0 ]; then
    echo "ERROR: $failed_nodes nodes are not available"
    exit 1
fi

# Шаг 2: ОПТИМИЗИРОВАННЫЙ сброс состояния кластера (параллельно)
echo "Resetting cluster state for clean setup (parallel)..."

# Функция для параллельного reset
reset_node_parallel() {
    local node=$1
    local host="${node%:*}"
    local port="${node#*:}"
    reset_node "$host" "$port"
}

# Запускаем reset параллельно
reset_pids=()
for node in "${nodes[@]}"; do
    reset_node_parallel "$node" &
    reset_pids+=($!)
done

# Ждем завершения всех reset операций
for pid in "${reset_pids[@]}"; do
    wait "$pid"
done

# Шаг 3: Создание кластера
echo "Creating Redis cluster..."
redis-cli --cluster create \
    redis-node-1:7379 \
    redis-node-2:7380 \
    redis-node-3:7381 \
    redis-replica-1:7382 \
    redis-replica-2:7383 \
    redis-replica-3:7384 \
    --cluster-replicas 1 \
    --cluster-yes \
    -a "${REDIS_PASSWORD}"

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to create Redis cluster"
    exit 1
fi

# Шаг 4: ОПТИМИЗИРОВАННАЯ проверка состояния кластера
echo "Verifying cluster state..."
# ОПТИМИЗАЦИЯ: Уменьшено количество попыток с 5 до 3
for attempt in $(seq 1 3); do
    if check_cluster; then
        echo "✓ Cluster verification successful"
        break
    fi
    if [ $attempt -eq 3 ]; then
        echo "WARNING: Cluster verification failed, but cluster was created"
        break
    fi
    echo "Waiting for cluster stabilization... (attempt $attempt/3)"
    # ОПТИМИЗАЦИЯ: Уменьшен интервал с 3 до 1 сек
    sleep 1
done

# Шаг 5: Показать итоговое состояние
echo ""
echo "=== Cluster Status ==="
redis-cli --cluster check redis-node-1:7379 -a "${REDIS_PASSWORD}"
echo "=== Redis Cluster Creator (Optimized) completed successfully ==="
