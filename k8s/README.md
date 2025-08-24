# 🚀 Enterprise Kubernetes Infrastructure

## Обзор Архитектуры

### Multi-Environment Setup
```
📁 k8s/
├── 📄 namespaces.yaml          # Namespace definitions
├── 📁 dev/                     # Development environment
├── 📁 staging/                 # Staging environment
├── 📁 production/              # Production environment (Blue-Green)
├── 📁 monitoring/              # Observability stack
└── 📁 security/                # Security policies & RBAC
```

### Компоненты Инфраструктуры

#### 🔒 Security Stack
- **Network Policies**: Zero-trust networking
- **RBAC**: Role-based access control
- **Pod Security Policies**: Runtime security
- **Resource Quotas**: Resource governance

#### 📊 Monitoring Stack
- **Prometheus**: Metrics collection
- **Grafana**: Visualization dashboards
- **AlertManager**: Alert management
- **ELK Stack**: Centralized logging

#### 🚀 Deployment Strategy
- **Blue-Green**: Zero-downtime deployments
- **Horizontal Pod Autoscaling**: Auto-scaling
- **Rolling Updates**: Safe updates
- **Automated Rollbacks**: Failure recovery

## 🚀 Быстрое Развертывание

### 1. Создание Namespaces
```bash
kubectl apply -f k8s/namespaces.yaml
```

### 2. Развертывание Security Policies
```bash
kubectl apply -f k8s/security/
```

### 3. Настройка Monitoring Stack
```bash
kubectl apply -f k8s/monitoring/
```

### 4. Развертывание по Окружениям

#### Development
```bash
kubectl apply -f k8s/dev/
```

#### Staging
```bash
kubectl apply -f k8s/staging/
```

#### Production (Blue-Green)
```bash
# Deploy Blue environment
kubectl apply -f k8s/production/app-blue.yaml
kubectl apply -f k8s/production/service.yaml

# Deploy Green environment
kubectl apply -f k8s/production/app-green.yaml

# Switch traffic to Green
kubectl patch service telegram-bot -n production -p '{"spec":{"selector":{"version":"green"}}}'
```

## 📊 Мониторинг и Observability

### Доступ к Dashboard'ам

#### Grafana
```bash
kubectl port-forward -n monitoring svc/grafana 3000:3000
# Access: http://localhost:3000
# Default: admin/admin
```

#### Prometheus
```bash
kubectl port-forward -n monitoring svc/prometheus 9090:9090
# Access: http://localhost:9090
```

#### Kibana
```bash
kubectl port-forward -n monitoring svc/kibana 5601:5601
# Access: http://localhost:5601
```

### Ключевые Метрики

#### Application Metrics
- **Response Time**: `http_request_duration_seconds`
- **Error Rate**: `rate(http_requests_total{status=~"5.."}[5m])`
- **Cache Hit Rate**: `redis_keyspace_hits / (redis_keyspace_hits + redis_keyspace_misses)`

#### Infrastructure Metrics
- **Pod Health**: `kube_pod_status_ready`
- **Resource Usage**: `container_cpu_usage_seconds_total`
- **Network I/O**: `container_network_receive_bytes_total`

## 🔒 Безопасность

### Security Best Practices

#### Container Security
```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1001
  readOnlyRootFilesystem: true
  capabilities:
    drop:
    - ALL
```

#### Network Security
- Default deny all traffic
- Explicit allow rules
- Service mesh ready

#### Secrets Management
- Kubernetes secrets encryption
- External secret management ready
- No hardcoded credentials

## 📈 Масштабирование

### Horizontal Pod Autoscaling

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: telegram-bot-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: telegram-bot
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

### Vertical Pod Autoscaling

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: telegram-bot-vpa
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: telegram-bot
  updatePolicy:
    updateMode: "Auto"
```

## 🔄 Disaster Recovery

### Backup Strategy

#### Automated Backups
```bash
# Redis backups
kubectl apply -f k8s/production/redis-backup.yaml

# Database backups
kubectl apply -f k8s/production/db-backup.yaml
```

#### Disaster Recovery Testing
```bash
# Simulate node failure
kubectl drain node-1 --ignore-daemonsets

# Test recovery
kubectl get pods -n production
kubectl logs -n production deployment/telegram-bot
```

## 📋 Troubleshooting

### Common Issues

#### Pod CrashLoopBackOff
```bash
# Check pod logs
kubectl logs -n production deployment/telegram-bot --tail=100

# Check pod events
kubectl describe pod -n production -l app=telegram-bot

# Check resource usage
kubectl top pods -n production
```

#### Service Unavailable
```bash
# Check endpoints
kubectl get endpoints -n production

# Check service configuration
kubectl describe service telegram-bot -n production

# Test service connectivity
kubectl run test --image=curlimages/curl --rm -it --restart=Never \
  -- curl http://telegram-bot:80/health
```

#### High Memory Usage
```bash
# Check memory usage
kubectl top pods -n production --sort-by=memory

# Check application metrics
kubectl port-forward -n monitoring svc/prometheus 9090:9090
# Query: container_memory_usage_bytes
```

## 🎯 Environment-Specific Configurations

### Development Environment
- **Replicas**: 1
- **Resources**: Minimal
- **Security**: Relaxed policies
- **Monitoring**: Basic metrics

### Staging Environment
- **Replicas**: 2
- **Resources**: Moderate
- **Security**: Production-like
- **Monitoring**: Full observability

### Production Environment
- **Replicas**: 3+ (with HPA)
- **Resources**: Optimized limits
- **Security**: Maximum security
- **Monitoring**: Enterprise monitoring

## 📚 Дополнительная Документация

- [Enterprise Deployment Guide](../docs/ENTERPRISE_DEPLOYMENT.md)
- [Architectural Audit Report](../docs/ARCHITECTURAL_AUDIT_REPORT.md)
- [CI/CD Pipeline](../.github/workflows/enterprise-cicd.yml)
- [Security Guidelines](../docs/SECURITY_GUIDELINES.md)

## 🚨 Emergency Procedures

### Emergency Rollback
```bash
# Immediate rollback to previous version
kubectl rollout undo deployment/telegram-bot -n production

# Check rollout status
kubectl rollout status deployment/telegram-bot -n production
```

### Emergency Shutdown
```bash
# Scale down to zero
kubectl scale deployment telegram-bot --replicas=0 -n production

# Scale up when ready
kubectl scale deployment telegram-bot --replicas=3 -n production
```

---

**Kubernetes Infrastructure v2.0.0**
**Enterprise-Grade Production Ready** 🎯

**Последнее обновление**: 2024-12-24
**Контакт**: devops@telegram-bot.com