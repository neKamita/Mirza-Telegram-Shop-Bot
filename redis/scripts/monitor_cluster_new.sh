#!/bin/bash

echo "=== Redis Cluster Monitor - $(date) ==="
echo "Starting cluster monitoring..."
while true; do
  echo "Running health check at $(date)"

  # Проверка доступности всех нод
  NODES_OK=true
  for node in redis-node-1:7379 redis-node-2:7380 redis-node-3:7381 redis-replica-1:7382 redis-replica-2:7383 redis-replica-3:7384; do
    if ! redis-cli -h ${node%:*} -p ${node#*:} -a ${REDIS_PASSWORD} ping >/dev/null 2>&1; then
      echo "ERROR: Node $node is not available"
      NODES_OK=false
      break
    fi
  done

  if [ "$NODES_OK" = "true" ]; then
    # Проверка состояния кластера
    if redis-cli --cluster check redis-node-1:7379 -a ${REDIS_PASSWORD} >/dev/null 2>&1; then
      echo "Cluster is healthy"
    else
      echo "WARNING: Cluster state check failed, attempting recovery"

      # Попытка перезаписи конфигурации кластера
      echo "Attempting to fix cluster configuration..."
      redis-cli --cluster fix redis-node-1:7379 -a ${REDIS_PASSWORD} --cluster-yes || true

      # Ожидание и повторная проверка
      sleep 10
      if redis-cli --cluster check redis-node-1:7379 -a ${REDIS_PASSWORD} >/dev/null 2>&1; then
        echo "Cluster recovered successfully"
      else
        echo "ERROR: Cluster recovery failed, manual intervention required"
        echo "Cluster state:" >> /var/log/redis-cluster-error.log
        redis-cli --cluster check redis-node-1:7379 -a ${REDIS_PASSWORD} >> /var/log/redis-cluster-error.log 2>&1 || true
      fi
    fi
  else
    echo "ERROR: Some nodes are down, attempting restart"
    for node in redis-node-1 redis-node-2 redis-node-3 redis-replica-1 redis-replica-2 redis-replica-3; do
      if ! redis-cli -h $node -a ${REDIS_PASSWORD} ping >/dev/null 2>&1; then
        echo "Restarting container: $node"
        docker restart telegram-$node || true
        sleep 10
      fi
    done
  fi

  echo "Health check completed, waiting for 5 minutes..."
  sleep 300
done
