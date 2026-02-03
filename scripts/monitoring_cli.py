#!/usr/bin/env python3
"""CLI tool for monitoring ResearchLab application."""

import asyncio
import sys
import time
import argparse
import json
from pathlib import Path
from typing import Optional

import httpx
import structlog

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from monitoring import get_health_checker, get_metrics_manager
from core.config import get_settings

# Configure logging
structlog.configure(
    processors=[
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    logger_factory=structlog.dev.LoggerFactory(),
    wrapper_class=structlog.make_filtering_bound_logger(30),  # WARNING level
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


class MonitoringCLI:
    """CLI for monitoring operations."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        
    async def check_health(self, components: Optional[str] = None, verbose: bool = False) -> bool:
        """Check application health via HTTP endpoint."""
        try:
            health_url = f"{self.base_url}/health"
            params = {"components": components} if components else {}
            
            async with httpx.AsyncClient() as client:
                response = await client.get(health_url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    print(f"🟢 Overall Status: {data['status'].upper()}")
                    print(f"⏱️  Check Duration: {data['duration']:.3f}s")
                    print(f"🕐 Timestamp: {time.ctime(data['timestamp'])}")
                    
                    if verbose:
                        print("\n📊 Component Details:")
                        for comp in data.get("components", []):
                            status_icon = self._get_status_icon(comp["status"])
                            print(f"  {status_icon} {comp['name']}: {comp['status']}")
                            if comp.get("message"):
                                print(f"     💬 {comp['message']}")
                            if comp.get("response_time"):
                                print(f"     ⏱️  Response time: {comp['response_time']:.3f}s")
                            if comp.get("metadata") and verbose:
                                print(f"     📋 Metadata: {json.dumps(comp['metadata'], indent=6)}")
                    
                    return True
                
                else:
                    print(f"❌ Health check failed with status {response.status_code}")
                    if response.content:
                        print(response.text)
                    return False
        
        except Exception as e:
            print(f"❌ Failed to check health: {e}")
            return False
    
    async def get_metrics(self, format_type: str = "prometheus", output_file: Optional[str] = None) -> bool:
        """Get application metrics via HTTP endpoint."""
        try:
            metrics_url = f"{self.base_url}/metrics"
            params = {"format": format_type}
            
            async with httpx.AsyncClient() as client:
                response = await client.get(metrics_url, params=params)
                
                if response.status_code == 200:
                    content = response.text
                    
                    if output_file:
                        with open(output_file, 'w') as f:
                            f.write(content)
                        print(f"📁 Metrics saved to {output_file}")
                    else:
                        print(content)
                    
                    return True
                
                else:
                    print(f"❌ Metrics request failed with status {response.status_code}")
                    if response.content:
                        print(response.text)
                    return False
        
        except Exception as e:
            print(f"❌ Failed to get metrics: {e}")
            return False
    
    async def monitor_continuously(self, interval: int = 30, components: Optional[str] = None):
        """Monitor health continuously."""
        print(f"🔄 Starting continuous monitoring (interval: {interval}s)")
        print("Press Ctrl+C to stop\n")
        
        try:
            while True:
                print(f"\n📊 Health Check - {time.strftime('%H:%M:%S')}")
                print("─" * 50)
                
                await self.check_health(components, verbose=False)
                
                await asyncio.sleep(interval)
        
        except KeyboardInterrupt:
            print("\n⏹️  Monitoring stopped")
    
    def _get_status_icon(self, status: str) -> str:
        """Get status icon for display."""
        icons = {
            "healthy": "🟢",
            "degraded": "🟡", 
            "unhealthy": "🔴",
            "unknown": "⚪"
        }
        return icons.get(status.lower(), "❓")
    
    async def local_health_check(self) -> bool:
        """Perform local health check without HTTP."""
        try:
            print("🔧 Performing local health check...")
            
            health_checker = get_health_checker()
            result = await health_checker.check_health()
            
            print(f"🟢 Overall Status: {result.overall_status.value.upper()}")
            print(f"⏱️  Check Duration: {result.check_duration:.3f}s")
            print(f"📊 Components checked: {len(result.components)}")
            
            for comp in result.components:
                status_icon = self._get_status_icon(comp.status.value)
                print(f"  {status_icon} {comp.name}: {comp.status.value}")
                if comp.message:
                    print(f"     💬 {comp.message}")
            
            return result.overall_status.value in ["healthy", "degraded"]
        
        except Exception as e:
            print(f"❌ Local health check failed: {e}")
            return False
    
    def local_metrics_summary(self) -> None:
        """Show local metrics summary."""
        try:
            print("📊 Local Metrics Summary")
            print("─" * 30)
            
            metrics_manager = get_metrics_manager()
            samples = metrics_manager.collect_metrics()
            
            if not samples:
                print("No metrics available")
                return
            
            # Group by metric name
            metrics_by_name = {}
            for sample in samples:
                name = sample.name
                if name not in metrics_by_name:
                    metrics_by_name[name] = []
                metrics_by_name[name].append(sample)
            
            print(f"Total metrics: {len(metrics_by_name)}")
            print(f"Total samples: {len(samples)}")
            print()
            
            # Show summary of each metric
            for name, metric_samples in sorted(metrics_by_name.items()):
                sample_count = len(metric_samples)
                total_value = sum(s.value for s in metric_samples)
                print(f"📈 {name}: {sample_count} samples, total value: {total_value}")
        
        except Exception as e:
            print(f"❌ Failed to get local metrics: {e}")


async def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(description="ResearchLab Monitoring CLI")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Application base URL")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Health command
    health_parser = subparsers.add_parser("health", help="Check application health")
    health_parser.add_argument("--components", help="Specific components to check (comma-separated)")
    health_parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    health_parser.add_argument("--local", action="store_true", help="Perform local check without HTTP")
    
    # Metrics command
    metrics_parser = subparsers.add_parser("metrics", help="Get application metrics")
    metrics_parser.add_argument("--format", choices=["prometheus", "json"], default="prometheus", 
                               help="Output format")
    metrics_parser.add_argument("--output", "-o", help="Output file path")
    metrics_parser.add_argument("--local", action="store_true", help="Show local metrics summary")
    
    # Monitor command
    monitor_parser = subparsers.add_parser("monitor", help="Monitor health continuously")
    monitor_parser.add_argument("--interval", "-i", type=int, default=30, 
                               help="Check interval in seconds")
    monitor_parser.add_argument("--components", help="Specific components to monitor")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    cli = MonitoringCLI(args.base_url)
    
    try:
        if args.command == "health":
            if args.local:
                success = await cli.local_health_check()
            else:
                success = await cli.check_health(args.components, args.verbose)
            
            if not success:
                sys.exit(1)
        
        elif args.command == "metrics":
            if args.local:
                cli.local_metrics_summary()
            else:
                success = await cli.get_metrics(args.format, args.output)
                if not success:
                    sys.exit(1)
        
        elif args.command == "monitor":
            await cli.monitor_continuously(args.interval, args.components)
    
    except KeyboardInterrupt:
        print("\n⏹️  Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())