#!/usr/bin/env python3
"""
Test script for ResearchLab LITE
Run this to validate that the lite version is working correctly.
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_imports():
    """Test that all core modules can be imported."""
    print("🔍 Testing imports...")
    
    try:
        from src.lite.config import LiteSettings
        print("  ✅ Config import OK")
    except Exception as e:
        print(f"  ❌ Config import failed: {e}")
        return False
    
    try:
        from src.lite.database import Base, Research, Company, Cache, SimpleCache
        print("  ✅ Database models import OK")
    except Exception as e:
        print(f"  ❌ Database models import failed: {e}")
        return False
    
    try:
        from src.lite.agent import ResearchAgent
        print("  ✅ Research agent import OK")
    except Exception as e:
        print(f"  ❌ Research agent import failed: {e}")
        return False
    
    try:
        from src.lite.app import create_lite_app
        print("  ✅ App import OK")
    except Exception as e:
        print(f"  ❌ App import failed: {e}")
        return False
    
    return True


def test_config():
    """Test configuration with dummy keys."""
    print("\n🔧 Testing configuration...")
    
    # Set dummy environment variables
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test123"
    os.environ["FINNHUB_API_KEY"] = "test123"
    os.environ["DATABASE_FILE"] = "test_lite.db"
    
    try:
        from src.lite.config import LiteSettings
        settings = LiteSettings()
        print(f"  ✅ Config loaded: {settings.app_name}")
        print(f"  ✅ Database URL: {settings.database_url}")
        print(f"  ✅ Host: {settings.host}:{settings.port}")
        return True
    except Exception as e:
        print(f"  ❌ Config failed: {e}")
        return False


def test_app_creation():
    """Test app creation without starting server."""
    print("\n🚀 Testing app creation...")
    
    try:
        from src.lite.app import create_lite_app
        app = create_lite_app()
        print(f"  ✅ App created: {app.title}")
        print(f"  ✅ Routes configured: {len(app.routes)}")
        return True
    except Exception as e:
        print(f"  ❌ App creation failed: {e}")
        return False


def test_database():
    """Test database initialization."""
    print("\n💾 Testing database...")
    
    try:
        import asyncio
        from src.lite.database import init_database, close_database
        
        async def test_db():
            await init_database()
            print("  ✅ Database initialized")
            await close_database()
            print("  ✅ Database closed")
        
        asyncio.run(test_db())
        return True
    except Exception as e:
        print(f"  ❌ Database test failed: {e}")
        return False


def test_templates():
    """Test that template files exist."""
    print("\n🎨 Testing templates...")
    
    template_dir = Path(__file__).parent / "src/lite/templates"
    required_templates = ["base.html", "index.html", "results.html", "error.html", "history.html"]
    
    all_exist = True
    for template in required_templates:
        template_path = template_dir / template
        if template_path.exists():
            print(f"  ✅ {template} exists")
        else:
            print(f"  ❌ {template} missing")
            all_exist = False
    
    return all_exist


def main():
    """Run all tests."""
    print("🧪 ResearchLab LITE Test Suite\n")
    
    tests = [
        ("Imports", test_imports),
        ("Configuration", test_config), 
        ("App Creation", test_app_creation),
        ("Database", test_database),
        ("Templates", test_templates),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"  ❌ {test_name} test crashed: {e}")
            results.append((test_name, False))
    
    print("\n" + "="*50)
    print("📊 Test Results:")
    print("="*50)
    
    passed = 0
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status} {test_name}")
        if success:
            passed += 1
    
    print("="*50)
    print(f"Results: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("\n🎉 All tests passed! ResearchLab LITE is ready to use.")
        print("\nNext steps:")
        print("1. Add your real API keys to .env file")
        print("2. Run: python run.py") 
        print("3. Open browser to http://localhost:8000")
        return True
    else:
        print("\n⚠️  Some tests failed. Please check the errors above.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)