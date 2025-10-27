#!/usr/bin/env python3
"""
PowerNight Smoke Tests

Basic smoke tests to verify the application starts and basic functionality works.
Run this script to perform a quick health check of the PowerNight application.
"""

import requests
import sys
import time
import json
from urllib.parse import urljoin


class PowerNightSmokeTest:
    """Smoke test suite for PowerNight application."""
    
    def __init__(self, base_url="http://localhost:5001"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.timeout = 10
        
    def test_server_running(self):
        """Test that the server is running and responding."""
        print("Testing server connectivity...")
        try:
            response = self.session.get(self.base_url)
            if response.status_code in [200, 302]:  # 302 for redirect
                print("✓ Server is running and responding")
                return True
            else:
                print(f"✗ Server returned unexpected status: {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"✗ Server is not responding: {e}")
            return False
    
    def test_page_routes(self):
        """Test that all page routes are accessible."""
        print("Testing page routes...")
        routes = [
            ('/dashboard', 'Dashboard'),
            ('/scheduling', 'Scheduling'),
            ('/logs', 'Logs')
        ]
        
        all_passed = True
        for route, name in routes:
            try:
                response = self.session.get(urljoin(self.base_url, route))
                if response.status_code == 200:
                    print(f"✓ {name} page loads successfully")
                else:
                    print(f"✗ {name} page failed with status {response.status_code}")
                    all_passed = False
            except requests.exceptions.RequestException as e:
                print(f"✗ {name} page failed: {e}")
                all_passed = False
        
        return all_passed
    
    def test_api_endpoints(self):
        """Test that API endpoints are working."""
        print("Testing API endpoints...")
        endpoints = [
            ('/api/v1/status', 'Status API'),
            ('/api/v1/backup-reserve', 'Backup Reserve API'),
            ('/health', 'Health Check')
        ]
        
        all_passed = True
        for endpoint, name in endpoints:
            try:
                response = self.session.get(urljoin(self.base_url, endpoint))
                if response.status_code == 200:
                    data = response.json()
                    if 'success' in data or 'status' in data:
                        print(f"✓ {name} returns valid data")
                    else:
                        print(f"✗ {name} returns invalid data format")
                        all_passed = False
                else:
                    print(f"✗ {name} failed with status {response.status_code}")
                    all_passed = False
            except requests.exceptions.RequestException as e:
                print(f"✗ {name} failed: {e}")
                all_passed = False
            except json.JSONDecodeError as e:
                print(f"✗ {name} returned invalid JSON: {e}")
                all_passed = False
        
        return all_passed
    
    def test_static_assets(self):
        """Test that static assets are accessible."""
        print("Testing static assets...")
        assets = [
            '/static/css/app.css',
            '/static/js/api.js',
            '/static/js/selector.js',
            '/static/js/dashboard-page.js'
        ]
        
        all_passed = True
        for asset in assets:
            try:
                response = self.session.get(urljoin(self.base_url, asset))
                if response.status_code == 200:
                    print(f"✓ {asset} loads successfully")
                else:
                    print(f"✗ {asset} failed with status {response.status_code}")
                    all_passed = False
            except requests.exceptions.RequestException as e:
                print(f"✗ {asset} failed: {e}")
                all_passed = False
        
        return all_passed
    
    def test_redirects(self):
        """Test that redirects work correctly."""
        print("Testing redirects...")
        
        # Test root redirect to dashboard
        try:
            response = self.session.get(self.base_url, allow_redirects=False)
            if response.status_code == 302 and '/dashboard' in response.headers.get('Location', ''):
                print("✓ Root redirects to dashboard")
            else:
                print(f"✗ Root redirect failed: {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"✗ Root redirect failed: {e}")
            return False
        
        # Test old interface redirect
        try:
            response = self.session.get(urljoin(self.base_url, '/static/index.html'), allow_redirects=False)
            if response.status_code == 302 and '/dashboard' in response.headers.get('Location', ''):
                print("✓ Old interface redirects to dashboard")
            else:
                print(f"✗ Old interface redirect failed: {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"✗ Old interface redirect failed: {e}")
            return False
        
        return True
    
    def test_demo_mode(self):
        """Test that demo mode is working correctly."""
        print("Testing demo mode...")
        
        try:
            response = self.session.get(urljoin(self.base_url, '/api/v1/backup-reserve'))
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('data', {}).get('demo_mode'):
                    print("✓ Demo mode is working correctly")
                    return True
                else:
                    print("✗ Demo mode not detected in backup-reserve endpoint")
                    return False
            else:
                print(f"✗ Backup-reserve endpoint failed: {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"✗ Demo mode test failed: {e}")
            return False
    
    def run_all_tests(self):
        """Run all smoke tests."""
        print("=" * 50)
        print("PowerNight Smoke Test Suite")
        print("=" * 50)
        
        tests = [
            self.test_server_running,
            self.test_page_routes,
            self.test_api_endpoints,
            self.test_static_assets,
            self.test_redirects,
            self.test_demo_mode
        ]
        
        passed = 0
        total = len(tests)
        
        for test in tests:
            try:
                if test():
                    passed += 1
                print()  # Add spacing between tests
            except Exception as e:
                print(f"✗ Test {test.__name__} failed with exception: {e}")
                print()
        
        print("=" * 50)
        print(f"Test Results: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All tests passed! PowerNight is working correctly.")
            return True
        else:
            print("❌ Some tests failed. Please check the application.")
            return False


def main():
    """Main entry point for smoke tests."""
    import argparse
    
    parser = argparse.ArgumentParser(description='PowerNight Smoke Tests')
    parser.add_argument('--url', default='http://localhost:5001', 
                       help='Base URL for the PowerNight application')
    parser.add_argument('--wait', type=int, default=0,
                       help='Wait N seconds before starting tests')
    
    args = parser.parse_args()
    
    if args.wait > 0:
        print(f"Waiting {args.wait} seconds before starting tests...")
        time.sleep(args.wait)
    
    smoke_test = PowerNightSmokeTest(args.url)
    success = smoke_test.run_all_tests()
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
