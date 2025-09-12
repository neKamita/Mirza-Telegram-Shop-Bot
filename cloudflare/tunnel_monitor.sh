#!/bin/bash

# Cloudflare Tunnel Monitor - улучшенный мониторинг cloudflared туннеля
# Проверяет connectivity, статус туннеля и доступность сервисов

LOG_FILE="/var/log/cloudflared-monitor.log"
CHECK_INTERVAL=30
MAX_RETRIES=3

# Функция для отправки алертов
send_alert() {
    local message="$1"
    local level="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
    
    # Интеграция с системами мониторинга (раскомментировать при настройке):
    # - Telegram notifications
    # - Slack webhook
    # - Email alerts
    
    echo "CLOUDFLARED ALERT: $message"
}

# Функция проверки статуса туннеля
check_tunnel_status() {
    echo "=== Cloudflare Tunnel Check - $(date) ==="
    
    # Проверяем, запущен ли cloudflared процесс
    if ! pgrep -f "cloudflared" > /dev/null; then
        send_alert "Cloudflared процесс не запущен" "CRITICAL"
        return 1
    fi
    
    # Проверяем статус туннеля
    local retries=0
    local tunnel_info=""
    
    while [ $retries -lt $MAX_RETRIES ]; do
        tunnel_info=$(timeout 10 cloudflared tunnel info 2>/dev/null)
        if [ $? -eq 0 ]; then
            break
        fi
        retries=$((retries + 1))
        sleep 2
    done
    
    if [ $retries -eq $MAX_RETRIES ]; then
        send_alert "Не удалось получить информацию о туннеле после $MAX_RETRIES попыток" "CRITICAL"
        return 1
    fi
    
    # Анализируем статус туннеля
    local tunnel_status=$(echo "$tunnel_info" | grep -oP 'Status:\s*\K[^ ]+' || echo "unknown")
    local connections=$(echo "$tunnel_info" | grep -oP 'Connections:\s*\K[0-9]+' || echo "0")
    local active_conns=$(echo "$tunnel_info" | grep -oP 'Active Connections:\s*\K[0-9]+' || echo "0")
    
    echo "Статус туннеля: $tunnel_status"
    echo "Всего подключений: $connections"
    echo "Активные подключения: $active_conns"
    
    # Проверяем критичные состояния
    if [ "$tunnel_status" = "unknown" ] || [ "$tunnel_status" = "inactive" ]; then
        send_alert "Туннель в неактивном состоянии: $tunnel_status" "CRITICAL"
    elif [ "$tunnel_status" = "degraded" ]; then
        send_alert "Туннель в деградировавшем состоянии: $tunnel_status" "WARNING"
    fi
    
    # Проверяем connectivity к внутренним сервисам через туннель
    check_internal_services
    
    return 0
}

# Функция проверки внутренних сервисов
check_internal_services() {
    echo ""
    echo "=== Проверка внутренних сервисов ==="
    
    local services=(
        "http://localhost:8080/health"
        "http://localhost:8001/health"
        "http://localhost:4444/wd/hub/status"
    )
    
    local service_names=("Nginx" "Webhook" "Selenium")
    
    for i in "${!services[@]}"; do
        local service_url="${services[$i]}"
        local service_name="${service_names[$i]}"
        local retries=0
        local success=false
        
        while [ $retries -lt $MAX_RETRIES ]; do
            if curl -f -s --connect-timeout 5 "$service_url" > /dev/null; then
                echo "✓ $service_name: доступен"
                success=true
                break
            fi
            retries=$((retries + 1))
            sleep 1
        done
        
        if [ "$success" = false ]; then
            send_alert "Сервис $service_name недоступен по адресу: $service_url" "WARNING"
            echo "✗ $service_name: недоступен после $MAX_RETRIES попыток"
        fi
    done
}

# Функция проверки DNS resolution
check_dns_resolution() {
    echo ""
    echo "=== Проверка DNS разрешения ==="
    
    local domains=(
        "api.telegram.org"
        "api.heleket.com"
        "cloudflare.com"
    )
    
    for domain in "${domains[@]}"; do
        if timeout 5 dig +short "$domain" > /dev/null 2>&1; then
            echo "✓ DNS $domain: разрешается"
        else
            send_alert "Не удалось разрешить DNS для: $domain" "WARNING"
            echo "✗ DNS $domain: не разрешается"
        fi
    done
}

# Функция проверки сертификатов
check_certificates() {
    echo ""
    echo "=== Проверка SSL сертификатов ==="
    
    local cert_paths=(
        "/etc/cloudflared/cert.pem"
        "/etc/nginx/ssl/cert.pem"
    )
    
    for cert_path in "${cert_paths[@]}"; do
        if [ -f "$cert_path" ]; then
            local expiry_date=$(openssl x509 -enddate -noout -in "$cert_path" 2>/dev/null | cut -d= -f2)
            if [ -n "$expiry_date" ]; then
                local expiry_epoch=$(date -d "$expiry_date" +%s 2>/dev/null)
                local now_epoch=$(date +%s)
                local days_until_expiry=$(( (expiry_epoch - now_epoch) / 86400 ))
                
                echo "Сертификат $cert_path: истекает через $days_until_expiry дней ($expiry_date)"
                
                if [ $days_until_expiry -lt 7 ]; then
                    send_alert "Сертификат $cert_path истекает через $days_until_expiry дней!" "CRITICAL"
                elif [ $days_until_expiry -lt 30 ]; then
                    send_alert "Сертификат $cert_path истекает через $days_until_expiry дней" "WARNING"
                fi
            else
                echo "⚠ Не удалось проверить срок действия сертификата: $cert_path"
            fi
        else
            send_alert "Сертификат не найден: $cert_path" "WARNING"
        fi
    done
}

# Основной цикл мониторинга
echo "Starting Cloudflare Tunnel Monitor..."
echo "Log file: $LOG_FILE"
echo "Check interval: ${CHECK_INTERVAL}s"

while true; do
    echo ""
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running cloudflared health check..."
    
    check_tunnel_status
    check_dns_resolution
    check_certificates
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Check completed. Waiting for ${CHECK_INTERVAL} seconds..."
    echo "=========================================="
    
    sleep $CHECK_INTERVAL
done