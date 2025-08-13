#!/usr/bin/env bash

echo "=== Redis Cluster Creator - $(date) ==="

# Функция для проверки доступности узла
check_node() {
    local host=$1
    local port=$2
    if ! redis-cli -h "$host" -p "$port" -a "${REDIS_PASSWORD}" ping >/dev/null 2>&1; then
        echo "ERROR: Node $host:$port is not available"
        return 1
    fi
    return 0
}

# Функция для сброса состояния узла
reset_node() {
    local host=$1
    local port=$2
    echo "Resetting node $host:$port..."
    redis-cli -h "$host" -p "$port" -a "${REDIS_PASSWORD}" CLUSTER RESET HARD >/dev/null 2>&1 || true
    sleep 1
    redis-cli -h "$host" -p "$port" -a "${REDIS_PASSWORD}" CONFIG SET appendonly no >/dev/null 2>&1 || true
    sleep 0.5
    redis-cli -h "$host" -p "$port" -a "${REDIS_PASSWORD}" FLUSHALL >/dev/null 2>&1 || true
    sleep 0.5
    redis-cli -h "$host" -p "$port" -a "${REDIS_PASSWORD}" CONFIG SET appendonly yes >/dev/null 2>&1 || true
    sleep 1
}

# Функция для проверки состояния кластера
check_cluster() {
    if redis-cli --cluster check redis-node-1:7379 -a "${REDIS_PASSWORD}" 2>/dev/null | grep -q "All 16384 slots covered"; then
        return 0
    fi
    return 1
}

# Шаг 1: Проверка доступности всех узлов
echo "Checking node availability..."
nodes=("redis-node-1:7379" "redis-node-2:7380" "redis-node-3:7381" "redis-replica-1:7382" "redis-replica-2:7383" "redis-replica-3:7384")

for node in "${nodes[@]}"; do
    host="${node%:*}"
    port="${node#*:}"

    # Ждем доступности узла с таймаутом
    for attempt in $(seq 1 10); do
        if check_node "$host" "$port"; then
            echo "✓ Node $node is available"
            break
        fi
        if [ $attempt -eq 10 ]; then
            echo "ERROR: Node $node is not available after 10 attempts"
            exit 1
        fi
        echo "Waiting for node $node... (attempt $attempt/10)"
        sleep 2
    done
done

# Шаг 2: Сброс состояния кластера (полная очистка)
echo "Resetting cluster state for clean setup..."
for node in "${nodes[@]}"; do
    host="${node%:*}"
    port="${node#*:}"
    reset_node "$host" "$port"
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

# Шаг 4: Проверка состояния кластера
echo "Verifying cluster state..."
for attempt in $(seq 1 5); do
    if check_cluster; then
        echo "✓ Cluster verification successful"
        break
    fi
    if [ $attempt -eq 5 ]; then
        echo "WARNING: Cluster verification failed, but cluster was created"
        break
    fi
    echo "Waiting for cluster stabilization... (attempt $attempt/5)"
    sleep 3
done

# Шаг 5: Показать итоговое состояние
echo ""
echo "=== Cluster Status ==="
redis-cli --cluster check redis-node-1:7379 -a "${REDIS_PASSWORD}"
echo "=== Redis Cluster Creator completed successfully ==="
