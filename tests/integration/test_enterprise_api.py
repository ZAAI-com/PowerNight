#!/usr/bin/env python3
"""
Test script for PowerNight Enterprise API

Quick test to verify that the enterprise-grade Flask application loads correctly.
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_app_creation():
    """Test that the Flask app can be created successfully."""
    try:
        from powernight.web.app import create_app

        print("✓ Successfully imported create_app")

        # Create test app
        app = create_app(testing=True)
        print("✓ Successfully created Flask app")

        # Check that blueprints are registered
        blueprint_names = [bp.name for bp in app.blueprints.values()]
        print(f"✓ Registered blueprints: {blueprint_names}")

        # Test app context
        with app.app_context():
            print("✓ App context working")

        return True

    except Exception as e:
        print(f"✗ Error creating app: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_monitoring_import():
    """Test that monitoring components can be imported."""
    try:
        from powernight.web.monitoring import get_metrics_collector, MetricsCollector

        print("✓ Successfully imported monitoring components")

        # Get metrics collector
        collector = get_metrics_collector()
        print(f"✓ Got metrics collector: {type(collector)}")

        # Test basic metrics recording
        collector.record_metric("test_metric", 42.0, {"source": "test"})
        print("✓ Successfully recorded test metric")

        return True

    except Exception as e:
        print(f"✗ Error testing monitoring: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_documentation():
    """Test that documentation components work."""
    try:
        from powernight.web.docs import get_docs_generator

        print("✓ Successfully imported documentation components")

        # Get documentation generator
        docs_gen = get_docs_generator()
        print(f"✓ Got docs generator: {type(docs_gen)}")

        # Generate OpenAPI spec
        spec = docs_gen.generate_openapi_spec()
        print(f"✓ Generated OpenAPI spec with {len(spec.get('paths', {}))} endpoints")

        return True

    except Exception as e:
        print(f"✗ Error testing documentation: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_schemas():
    """Test that schema validation works."""
    try:
        from powernight.web.schemas import get_schema_validator

        print("✓ Successfully imported schema components")

        # Get validator
        validator = get_schema_validator()
        print(f"✓ Got schema validator: {type(validator)}")

        # Test configuration validation
        test_config = {
            "powerwall": {
                "ip_address": "192.168.1.100",
                "email": "test@example.com",
                "timeout": 30
            }
        }

        result = validator.validate_config_update(test_config)
        print(f"✓ Validation result: valid={result.is_valid}, errors={len(result.errors)}")

        return True

    except Exception as e:
        print(f"✗ Error testing schemas: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("PowerNight Enterprise API Test Suite")
    print("=" * 40)

    tests = [
        ("App Creation", test_app_creation),
        ("Monitoring", test_monitoring_import),
        ("Documentation", test_documentation),
        ("Schema Validation", test_schemas),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\nTesting {test_name}...")
        print("-" * 20)

        if test_func():
            passed += 1
            print(f"✓ {test_name} PASSED")
        else:
            print(f"✗ {test_name} FAILED")

    print("\n" + "=" * 40)
    print(f"Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! Enterprise API is ready.")
        return 0
    else:
        print("❌ Some tests failed. Check the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())