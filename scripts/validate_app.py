#!/usr/bin/env python3
"""Validation script to ensure the application is properly configured."""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_imports():
    """Test that all critical imports work."""
    print("Testing imports...")
    
    try:
        from core.config import settings
        print("✓ Configuration loaded")
        
        from core.logging import setup_logging, get_logger
        print("✓ Logging system imported")
        
        from core.app import create_app
        print("✓ App factory imported")
        
        from api import research_router, workflow_router, news_router, agents_router, companies_router
        print("✓ API routers imported")
        
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False


def test_app_creation():
    """Test that the app can be created successfully."""
    print("Testing app creation...")
    
    try:
        from core.app import create_app
        app = create_app()
        print("✓ App created successfully")
        
        # Check that routes are registered
        route_count = len(app.routes)
        print(f"✓ App has {route_count} routes registered")
        
        # Test OpenAPI schema generation
        schema = app.openapi()
        print(f"✓ OpenAPI schema generated with {len(schema.get('paths', {}))} paths")
        
        return True
    except Exception as e:
        print(f"✗ App creation failed: {e}")
        return False


def test_logging_system():
    """Test the enhanced logging system."""
    print("Testing logging system...")
    
    try:
        from core.logging import setup_logging, get_logger, LoggingContext, log_performance
        
        # Setup logging
        setup_logging()
        logger = get_logger("validation")
        
        # Test basic logging
        logger.info("Validation test log entry")
        
        # Test context manager
        with LoggingContext(request_id="validation-test"):
            logger.info("Testing context manager")
        
        # Test performance decorator
        @log_performance("validation_operation")
        def test_function():
            return "success"
        
        result = test_function()
        assert result == "success"
        
        print("✓ Logging system working correctly")
        return True
    except Exception as e:
        print(f"✗ Logging test failed: {e}")
        return False


def test_configuration():
    """Test configuration system."""
    print("Testing configuration...")
    
    try:
        from core.config import settings
        
        # Check key settings
        assert settings.app.app_name == "ResearchLab"
        assert settings.app.environment in ["development", "testing", "production"]
        assert hasattr(settings, "database")
        assert hasattr(settings, "monitoring")
        
        print(f"✓ Configuration valid (env: {settings.app.environment})")
        return True
    except Exception as e:
        print(f"✗ Configuration test failed: {e}")
        return False


def main():
    """Run all validation tests."""
    print("🧪 ResearchLab Application Validation")
    print("=" * 40)
    
    tests = [
        ("Imports", test_imports),
        ("Configuration", test_configuration), 
        ("Logging System", test_logging_system),
        ("App Creation", test_app_creation),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🔍 {test_name}")
        print("-" * 20)
        if test_func():
            passed += 1
            print(f"✅ {test_name} PASSED")
        else:
            print(f"❌ {test_name} FAILED")
    
    print("\n" + "=" * 40)
    print(f"📊 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All validation tests PASSED! Application is ready.")
        return 0
    else:
        print("⚠️  Some tests failed. Please review the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())