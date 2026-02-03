#!/bin/bash
# Docker build script for ResearchLab

set -e

# Configuration
IMAGE_NAME="researchlab"
BUILD_CONTEXT="."
DOCKERFILE="Dockerfile.production"

# Parse command line arguments
BUILD_TYPE="production"
TAG="latest"
PUSH=false
NO_CACHE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --dev|--development)
            BUILD_TYPE="development"
            DOCKERFILE="Dockerfile"
            TAG="dev"
            shift
            ;;
        --tag)
            TAG="$2"
            shift 2
            ;;
        --push)
            PUSH=true
            shift
            ;;
        --no-cache)
            NO_CACHE=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --dev, --development    Build development image"
            echo "  --tag TAG              Set image tag (default: latest)"
            echo "  --push                 Push to registry after build"
            echo "  --no-cache            Build without cache"
            echo "  --help                Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "🐳 Building ResearchLab Docker image..."
echo "📋 Configuration:"
echo "   🏗️  Build type: $BUILD_TYPE"
echo "   📁 Dockerfile: $DOCKERFILE"
echo "   🏷️  Tag: $IMAGE_NAME:$TAG"
echo "   🚀 Push: $PUSH"
echo "   💨 No cache: $NO_CACHE"
echo

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi

# Build arguments
BUILD_ARGS=""
if [ "$NO_CACHE" = true ]; then
    BUILD_ARGS="$BUILD_ARGS --no-cache"
fi

# Build the image
echo "🔨 Building Docker image..."
if [ "$BUILD_TYPE" = "production" ]; then
    # Multi-stage production build
    docker build \
        $BUILD_ARGS \
        -f $DOCKERFILE \
        -t $IMAGE_NAME:$TAG \
        -t $IMAGE_NAME:latest \
        --target production \
        $BUILD_CONTEXT
else
    # Development build
    docker build \
        $BUILD_ARGS \
        -f $DOCKERFILE \
        -t $IMAGE_NAME:$TAG \
        $BUILD_CONTEXT
fi

echo "✅ Build completed successfully!"

# Show image details
echo "📊 Image details:"
docker images $IMAGE_NAME:$TAG --format "table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}\t{{.CreatedAt}}"

# Security scan if available
if command -v docker-scout >/dev/null 2>&1; then
    echo "🔍 Running security scan..."
    docker scout cves $IMAGE_NAME:$TAG || echo "⚠️  Security scan failed or not available"
fi

# Push to registry if requested
if [ "$PUSH" = true ]; then
    echo "📤 Pushing to registry..."
    
    # Check if we're logged in to a registry
    if ! docker info | grep -q "Username:"; then
        echo "⚠️  Not logged in to Docker registry. Please run 'docker login' first."
        read -p "Continue without pushing? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        docker push $IMAGE_NAME:$TAG
        if [ "$TAG" != "latest" ] && [ "$BUILD_TYPE" = "production" ]; then
            docker push $IMAGE_NAME:latest
        fi
        echo "✅ Push completed!"
    fi
fi

# Show usage instructions
echo
echo "🚀 Usage Instructions:"
echo
echo "Development:"
echo "  docker run -p 8000:8000 --env-file .env $IMAGE_NAME:$TAG"
echo
echo "Production with Docker Compose:"
echo "  docker-compose -f docker-compose.production.yml up -d"
echo
echo "Manual production run:"
echo "  docker run -p 8000:8000 --env-file .env.production $IMAGE_NAME:$TAG"
echo
echo "🎉 Docker image build completed successfully!"