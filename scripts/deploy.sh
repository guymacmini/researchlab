#!/bin/bash
# Production deployment script for ResearchLab

set -e

# Configuration
COMPOSE_FILE="docker-compose.production.yml"
ENV_FILE=".env.production"
BACKUP_DIR="backups"
SERVICE_NAME="app"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Parse command line arguments
COMMAND=""
FORCE=false
BACKUP=true
HEALTHCHECK=true
ROLLBACK=false

while [[ $# -gt 0 ]]; do
    case $1 in
        deploy|start|stop|restart|status|logs|backup|rollback)
            COMMAND="$1"
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --no-backup)
            BACKUP=false
            shift
            ;;
        --no-healthcheck)
            HEALTHCHECK=false
            shift
            ;;
        --help)
            echo "Usage: $0 COMMAND [OPTIONS]"
            echo ""
            echo "Commands:"
            echo "  deploy      Deploy/update the application"
            echo "  start       Start services"
            echo "  stop        Stop services"
            echo "  restart     Restart services"
            echo "  status      Show service status"
            echo "  logs        Show service logs"
            echo "  backup      Backup data"
            echo "  rollback    Rollback to previous version"
            echo ""
            echo "Options:"
            echo "  --force         Force deployment without confirmation"
            echo "  --no-backup     Skip backup before deployment"
            echo "  --no-healthcheck Skip health check after deployment"
            echo "  --help          Show this help"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

if [ -z "$COMMAND" ]; then
    log_error "No command specified. Use --help for usage information."
    exit 1
fi

# Pre-flight checks
check_requirements() {
    log_info "Running pre-flight checks..."
    
    # Check Docker
    if ! command -v docker >/dev/null 2>&1; then
        log_error "Docker is not installed"
        exit 1
    fi
    
    if ! docker info >/dev/null 2>&1; then
        log_error "Docker is not running"
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose >/dev/null 2>&1; then
        log_error "Docker Compose is not installed"
        exit 1
    fi
    
    # Check environment file
    if [ ! -f "$ENV_FILE" ]; then
        log_error "Environment file $ENV_FILE not found"
        log_info "Copy .env.production and configure it with your values"
        exit 1
    fi
    
    # Validate environment file
    if grep -q "CHANGE_ME" "$ENV_FILE"; then
        log_error "Environment file contains unconfigured values (CHANGE_ME)"
        log_info "Please update $ENV_FILE with your actual values"
        exit 1
    fi
    
    log_success "Pre-flight checks passed"
}

# Backup data
backup_data() {
    if [ "$BACKUP" = false ]; then
        log_info "Skipping backup (--no-backup specified)"
        return
    fi
    
    log_info "Creating backup..."
    
    mkdir -p "$BACKUP_DIR"
    
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/researchlab_backup_$TIMESTAMP.tar.gz"
    
    # Backup database
    log_info "Backing up database..."
    docker-compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T postgres \
        pg_dump -U researchlab researchlab_prod | gzip > "$BACKUP_DIR/db_backup_$TIMESTAMP.sql.gz"
    
    # Backup Redis data (if running)
    if docker-compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps redis | grep -q "Up"; then
        log_info "Backing up Redis data..."
        docker-compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T redis \
            redis-cli BGSAVE
    fi
    
    # Backup volumes
    log_info "Backing up application data..."
    docker run --rm -v researchlab_prod_app_data:/data -v "$(pwd)/$BACKUP_DIR":/backup \
        alpine:latest tar czf "/backup/app_data_$TIMESTAMP.tar.gz" -C /data .
    
    log_success "Backup completed: $BACKUP_FILE"
}

# Health check
health_check() {
    if [ "$HEALTHCHECK" = false ]; then
        log_info "Skipping health check (--no-healthcheck specified)"
        return
    fi
    
    log_info "Performing health check..."
    
    # Wait for service to be ready
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -f -s http://localhost:8000/health > /dev/null 2>&1; then
            log_success "Health check passed"
            return 0
        fi
        
        log_info "Health check attempt $attempt/$max_attempts failed, waiting..."
        sleep 10
        ((attempt++))
    done
    
    log_error "Health check failed after $max_attempts attempts"
    return 1
}

# Deploy application
deploy() {
    log_info "Starting deployment..."
    
    # Confirmation
    if [ "$FORCE" = false ]; then
        echo -n "This will deploy ResearchLab to production. Continue? (y/N): "
        read -r response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            log_info "Deployment cancelled"
            exit 0
        fi
    fi
    
    check_requirements
    backup_data
    
    # Pull latest images
    log_info "Pulling latest images..."
    docker-compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" pull
    
    # Stop services gracefully
    log_info "Stopping services..."
    docker-compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" down --timeout 30
    
    # Start services
    log_info "Starting services..."
    docker-compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d
    
    # Health check
    if health_check; then
        log_success "Deployment completed successfully!"
        
        # Show service status
        log_info "Service status:"
        docker-compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps
    else
        log_error "Deployment failed health check"
        log_info "Check logs with: $0 logs"
        exit 1
    fi
}

# Execute commands
case $COMMAND in
    deploy)
        deploy
        ;;
    start)
        check_requirements
        log_info "Starting services..."
        docker-compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d
        log_success "Services started"
        ;;
    stop)
        log_info "Stopping services..."
        docker-compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" down
        log_success "Services stopped"
        ;;
    restart)
        log_info "Restarting services..."
        docker-compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" restart
        log_success "Services restarted"
        ;;
    status)
        log_info "Service status:"
        docker-compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps
        ;;
    logs)
        docker-compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" logs -f "$SERVICE_NAME"
        ;;
    backup)
        check_requirements
        backup_data
        ;;
    rollback)
        log_warning "Rollback functionality not implemented yet"
        log_info "To rollback manually:"
        log_info "1. Stop services: $0 stop"
        log_info "2. Restore database from backup"
        log_info "3. Start services: $0 start"
        ;;
esac