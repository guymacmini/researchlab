# Docker Deployment Guide for ResearchLab

This directory contains Docker configurations for deploying ResearchLab in production environments.

## 🏗️ Architecture

The production deployment includes:

- **ResearchLab Application**: FastAPI backend with Gunicorn
- **PostgreSQL**: Primary database
- **Redis**: Caching and rate limiting
- **Nginx**: Reverse proxy and load balancer (optional)
- **Prometheus**: Metrics collection (optional)
- **Grafana**: Monitoring dashboard (optional)

## 🚀 Quick Start

### 1. Prepare Environment

```bash
# Copy and configure environment file
cp .env.production .env.production.local
editor .env.production.local  # Update with your values

# Build production image
./scripts/docker_build.sh
```

### 2. Deploy with Docker Compose

```bash
# Deploy all services
./scripts/deploy.sh deploy

# Or manually
docker-compose -f docker-compose.production.yml --env-file .env.production.local up -d
```

### 3. Verify Deployment

```bash
# Check service status
./scripts/deploy.sh status

# View logs
./scripts/deploy.sh logs

# Health check
curl http://localhost:8000/health
```

## 📋 Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- At least 2GB RAM
- 10GB disk space

## ⚙️ Configuration

### Environment Variables

Key variables to configure in `.env.production`:

```bash
# Security (REQUIRED)
SECRET_KEY=your-secret-key-here
DB_PASSWORD=strong-database-password

# API Keys (REQUIRED)
FINNHUB_API_KEY=your-finnhub-key
ALPHA_VANTAGE_API_KEY=your-alpha-vantage-key
ANTHROPIC_API_KEY=your-anthropic-key

# Optional
GOOGLE_CREDENTIALS_FILE=/app/credentials/google-service-account.json
```

### Service Profiles

Use profiles to enable optional services:

```bash
# Enable monitoring stack
docker-compose --profile monitoring up -d

# Enable nginx proxy
docker-compose --profile nginx up -d

# Enable all optional services
docker-compose --profile monitoring --profile nginx up -d
```

## 🔧 Management Commands

### Deployment

```bash
./scripts/deploy.sh deploy              # Full deployment
./scripts/deploy.sh deploy --force      # Skip confirmation
./scripts/deploy.sh deploy --no-backup  # Skip backup
```

### Service Management

```bash
./scripts/deploy.sh start     # Start services
./scripts/deploy.sh stop      # Stop services  
./scripts/deploy.sh restart   # Restart services
./scripts/deploy.sh status    # Show status
./scripts/deploy.sh logs      # View logs
```

### Data Management

```bash
./scripts/deploy.sh backup    # Backup data
./scripts/deploy.sh rollback  # Rollback (manual process)
```

## 🏗️ Build Options

```bash
# Production build (default)
./scripts/docker_build.sh

# Development build
./scripts/docker_build.sh --dev

# Custom tag
./scripts/docker_build.sh --tag v1.0.0

# Build and push
./scripts/docker_build.sh --push

# No cache build
./scripts/docker_build.sh --no-cache
```

## 📊 Monitoring

### Accessing Services

- **ResearchLab**: http://localhost:8000
- **Health Check**: http://localhost:8000/health
- **Metrics**: http://localhost:8000/metrics
- **Prometheus**: http://localhost:9090 (with monitoring profile)
- **Grafana**: http://localhost:3000 (with monitoring profile)

### Metrics Endpoints

The application exposes Prometheus-compatible metrics:

- HTTP request metrics
- Database operation metrics
- Agent execution metrics
- Rate limiting metrics
- System resource metrics

### Log Files

Logs are available via Docker:

```bash
# Application logs
docker-compose logs -f app

# All services
docker-compose logs -f

# Specific service
docker-compose logs -f postgres
```

## 🔒 Security

### Best Practices Implemented

- Non-root container user
- Multi-stage builds to reduce attack surface
- Security headers via Nginx
- Rate limiting
- Input validation
- Secrets via environment variables
- Network isolation

### SSL/TLS Setup

For production with SSL:

1. Obtain SSL certificates
2. Place them in `docker/nginx/ssl/`
3. Uncomment HTTPS server block in `nginx.conf`
4. Update environment variables

## 📈 Scaling

### Horizontal Scaling

Scale application containers:

```bash
docker-compose up -d --scale app=3
```

### Resource Limits

Adjust in `docker-compose.production.yml`:

```yaml
services:
  app:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
```

## 🔧 Troubleshooting

### Common Issues

**Service won't start:**
```bash
# Check logs
docker-compose logs app

# Check health
curl http://localhost:8000/health
```

**Database connection failed:**
```bash
# Check PostgreSQL
docker-compose logs postgres

# Verify network
docker network ls
docker network inspect researchlab_prod
```

**Out of memory:**
```bash
# Check resource usage
docker stats

# Reduce workers
export WORKERS=2
docker-compose up -d
```

### Health Checks

All services include health checks:

```bash
# Check all service health
docker-compose ps

# Manual health check
docker-compose exec app curl -f http://localhost:8000/health
```

### Backup and Recovery

**Manual Database Backup:**
```bash
docker-compose exec postgres pg_dump -U researchlab researchlab_prod > backup.sql
```

**Restore Database:**
```bash
docker-compose exec -T postgres psql -U researchlab researchlab_prod < backup.sql
```

### Performance Tuning

**Database Performance:**
```bash
# Check database performance
docker-compose exec postgres psql -U researchlab -c "SELECT * FROM pg_stat_activity;"
```

**Application Performance:**
```bash
# Monitor metrics
curl http://localhost:8000/metrics

# Check resource usage
docker-compose exec app python scripts/monitoring_cli.py monitor
```

## 🔄 Updates

### Application Updates

```bash
# Pull new image
docker-compose pull app

# Deploy update
./scripts/deploy.sh deploy
```

### Database Migrations

Migrations run automatically during startup via `prestart.sh`.

Manual migration:
```bash
docker-compose exec app alembic upgrade head
```

## 📚 Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Reference](https://docs.docker.com/compose/)
- [Nginx Configuration Guide](https://nginx.org/en/docs/)
- [Prometheus Monitoring](https://prometheus.io/docs/)
- [PostgreSQL Tuning](https://wiki.postgresql.org/wiki/Tuning_Your_PostgreSQL_Server)