#!/bin/bash
# Pre-start script for production deployment

set -e

echo "🚀 Starting ResearchLab pre-deployment checks..."

# Wait for database to be ready
echo "📦 Waiting for database connection..."
python -c "
import asyncio
import sys
from src.core.database import test_connection

async def main():
    max_tries = 30
    for i in range(max_tries):
        try:
            if await test_connection():
                print(f'✅ Database connected after {i+1} attempts')
                return
        except Exception as e:
            if i == max_tries - 1:
                print(f'❌ Failed to connect to database after {max_tries} attempts: {e}')
                sys.exit(1)
            print(f'⏳ Database not ready, waiting... (attempt {i+1}/{max_tries})')
            await asyncio.sleep(2)

asyncio.run(main())
"

# Run database migrations
echo "🔄 Running database migrations..."
alembic upgrade head

# Validate configuration
echo "⚙️  Validating configuration..."
python scripts/validate_config.py --environment production

# Test critical services
echo "🧪 Testing critical service connections..."
python -c "
import asyncio
from src.monitoring.health import get_health_checker

async def test_services():
    health_checker = get_health_checker()
    result = await health_checker.check_health(['database', 'redis'])
    
    critical_failed = []
    for component in result.components:
        if component.status.value != 'healthy':
            critical_failed.append(component.name)
    
    if critical_failed:
        print(f'❌ Critical services unhealthy: {critical_failed}')
        return False
    
    print('✅ All critical services healthy')
    return True

if not asyncio.run(test_services()):
    exit(1)
"

# Create necessary directories
echo "📁 Creating required directories..."
mkdir -p logs data

# Set up log rotation if logrotate is available
if command -v logrotate >/dev/null 2>&1; then
    echo "📋 Setting up log rotation..."
    cat > /tmp/researchlab-logrotate.conf << EOF
/app/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    sharedscripts
    copytruncate
}
EOF
fi

echo "✅ Pre-start checks completed successfully!"
echo "🎯 Ready to start ResearchLab application..."