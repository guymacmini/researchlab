#!/bin/bash
# Production startup script for ResearchLab

set -e

echo "🚀 Starting ResearchLab in production mode..."

# Run pre-start checks
./prestart.sh

# Calculate optimal worker count if not set
if [ -z "$WORKERS" ]; then
    # Use (2 * CPU cores) + 1 as recommended by Gunicorn
    WORKERS=$((2 * $(nproc) + 1))
    echo "📊 Auto-calculated worker count: $WORKERS"
fi

# Set default values for production
export HOST=${HOST:-"0.0.0.0"}
export PORT=${PORT:-"8000"}
export LOG_LEVEL=${LOG_LEVEL:-"info"}
export ACCESS_LOG=${ACCESS_LOG:-"true"}

echo "⚙️  Configuration:"
echo "   🌐 Host: $HOST"
echo "   🔌 Port: $PORT"
echo "   👷 Workers: $WORKERS"
echo "   📊 Log Level: $LOG_LEVEL"
echo "   📝 Access Logging: $ACCESS_LOG"

# Start application with Gunicorn for production
if [ "$USE_GUNICORN" = "true" ] || [ "$ENVIRONMENT" = "production" ]; then
    echo "🚀 Starting with Gunicorn (production server)..."
    
    # Install gunicorn if not present
    pip install gunicorn uvicorn[standard]
    
    exec gunicorn src.core.app:app \
        --worker-class uvicorn.workers.UvicornWorker \
        --workers $WORKERS \
        --bind $HOST:$PORT \
        --timeout 120 \
        --keep-alive 5 \
        --max-requests 1000 \
        --max-requests-jitter 100 \
        --preload \
        --access-logfile - \
        --error-logfile - \
        --log-level $LOG_LEVEL \
        --capture-output \
        --enable-stdio-inheritance
else
    echo "🚀 Starting with Uvicorn (development server)..."
    
    UVICORN_ARGS="src.core.app:app --host $HOST --port $PORT --log-level $LOG_LEVEL"
    
    # Add access logging in production
    if [ "$ACCESS_LOG" = "true" ]; then
        UVICORN_ARGS="$UVICORN_ARGS --access-log"
    fi
    
    # No reload in production
    if [ "$ENVIRONMENT" != "production" ]; then
        UVICORN_ARGS="$UVICORN_ARGS --reload"
    fi
    
    exec uvicorn $UVICORN_ARGS
fi