#!/usr/bin/env python3
"""CLI tool for managing rate limits."""

import asyncio
import sys
import argparse
from pathlib import Path
from typing import Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rate_limiting.backends import MemoryBackend, RedisBackend
from rate_limiting.middleware import reset_rate_limit, get_rate_limit_status
from core.config import get_settings
import structlog

# Configure logging
structlog.configure(
    processors=[
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    logger_factory=structlog.dev.LoggerFactory(),
    wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO level
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


class RateLimitCLI:
    """CLI for rate limit management."""
    
    def __init__(self):
        self.backend = None
        self.settings = get_settings()
    
    async def _get_backend(self):
        """Get rate limiting backend."""
        if self.backend is None:
            # Try Redis first
            if self.settings.database.redis_url:
                try:
                    from redis.asyncio import Redis
                    redis_client = Redis.from_url(self.settings.database.redis_url)
                    
                    # Test connection
                    await redis_client.ping()
                    
                    self.backend = RedisBackend(redis_client)
                    logger.info("Connected to Redis backend")
                
                except ImportError:
                    logger.warning("Redis not available, using memory backend")
                    self.backend = MemoryBackend()
                
                except Exception as e:
                    logger.error("Failed to connect to Redis, using memory backend", error=str(e))
                    self.backend = MemoryBackend()
            else:
                logger.info("Using memory backend")
                self.backend = MemoryBackend()
        
        return self.backend
    
    async def check_status(self, key: str) -> bool:
        """Check rate limit status for a key."""
        try:
            backend = await self._get_backend()
            info = await get_rate_limit_status(backend, key)
            
            if info is None:
                print(f"📊 No rate limit data found for key: {key}")
                return True
            
            print(f"📊 Rate Limit Status for: {key}")
            print("─" * 50)
            
            if isinstance(info, dict):
                for field, value in info.items():
                    if field == "key":
                        continue
                    
                    if field.endswith("_request") and value:
                        import time
                        readable_time = time.ctime(value)
                        print(f"  📅 {field}: {readable_time}")
                    else:
                        print(f"  📊 {field}: {value}")
            else:
                print(f"  📊 Info: {info}")
            
            return True
        
        except Exception as e:
            print(f"❌ Failed to check status: {e}")
            return False
    
    async def reset_key(self, key: str) -> bool:
        """Reset rate limit for a key."""
        try:
            backend = await self._get_backend()
            success = await reset_rate_limit(backend, key)
            
            if success:
                print(f"✅ Rate limit reset for key: {key}")
            else:
                print(f"⚠️  No rate limit data found for key: {key}")
            
            return success
        
        except Exception as e:
            print(f"❌ Failed to reset rate limit: {e}")
            return False
    
    async def list_keys(self, pattern: Optional[str] = None) -> bool:
        """List active rate limit keys."""
        try:
            backend = await self._get_backend()
            
            # This functionality would need to be implemented in backends
            # For now, show a message
            print("📋 List Keys Feature")
            print("─" * 30)
            print("⚠️  Key listing not implemented for current backend")
            print("💡 Suggestion: Use Redis CLI or memory backend inspection")
            
            return True
        
        except Exception as e:
            print(f"❌ Failed to list keys: {e}")
            return False
    
    async def test_key(self, key: str, limit: int = 10, window: int = 60, 
                      requests: int = 1) -> bool:
        """Test rate limiting for a key."""
        try:
            backend = await self._get_backend()
            
            print(f"🧪 Testing rate limit for: {key}")
            print(f"📏 Limit: {limit} requests per {window} seconds")
            print(f"🔄 Making {requests} test requests...")
            print("─" * 50)
            
            for i in range(requests):
                result = await backend.check_rate_limit(key, limit, window, 1)
                
                status_icon = "✅" if result.allowed else "❌"
                print(f"  {status_icon} Request {i+1}: allowed={result.allowed}, "
                      f"remaining={result.remaining}")
                
                if not result.allowed and result.retry_after:
                    print(f"     ⏰ Retry after: {result.retry_after:.2f} seconds")
            
            return True
        
        except Exception as e:
            print(f"❌ Failed to test rate limit: {e}")
            return False
    
    async def monitor_key(self, key: str, interval: int = 5) -> None:
        """Monitor rate limit status for a key."""
        print(f"👁️  Monitoring rate limit for: {key}")
        print(f"🔄 Update interval: {interval} seconds")
        print("Press Ctrl+C to stop\n")
        
        try:
            while True:
                print(f"\n📊 Status Update - {key}")
                print("─" * 40)
                
                await self.check_status(key)
                
                await asyncio.sleep(interval)
        
        except KeyboardInterrupt:
            print("\n⏹️  Monitoring stopped")


async def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(description="ResearchLab Rate Limit Management")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Check rate limit status for a key")
    status_parser.add_argument("key", help="Rate limit key to check")
    
    # Reset command
    reset_parser = subparsers.add_parser("reset", help="Reset rate limit for a key")
    reset_parser.add_argument("key", help="Rate limit key to reset")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List active rate limit keys")
    list_parser.add_argument("--pattern", help="Pattern to filter keys")
    
    # Test command
    test_parser = subparsers.add_parser("test", help="Test rate limiting for a key")
    test_parser.add_argument("key", help="Rate limit key to test")
    test_parser.add_argument("--limit", type=int, default=10, help="Rate limit (default: 10)")
    test_parser.add_argument("--window", type=int, default=60, help="Time window in seconds (default: 60)")
    test_parser.add_argument("--requests", type=int, default=5, help="Number of test requests (default: 5)")
    
    # Monitor command
    monitor_parser = subparsers.add_parser("monitor", help="Monitor rate limit status continuously")
    monitor_parser.add_argument("key", help="Rate limit key to monitor")
    monitor_parser.add_argument("--interval", "-i", type=int, default=5, 
                               help="Update interval in seconds (default: 5)")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    cli = RateLimitCLI()
    
    try:
        if args.command == "status":
            success = await cli.check_status(args.key)
            if not success:
                sys.exit(1)
        
        elif args.command == "reset":
            success = await cli.reset_key(args.key)
            if not success:
                sys.exit(1)
        
        elif args.command == "list":
            success = await cli.list_keys(args.pattern)
            if not success:
                sys.exit(1)
        
        elif args.command == "test":
            success = await cli.test_key(args.key, args.limit, args.window, args.requests)
            if not success:
                sys.exit(1)
        
        elif args.command == "monitor":
            await cli.monitor_key(args.key, args.interval)
    
    except KeyboardInterrupt:
        print("\n⏹️  Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())