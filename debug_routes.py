#!/usr/bin/env python3
"""
Debug script to test competition routes
Run this after starting your Flask app to verify all routes exist
"""

import requests
import sys
import time

def check_flask_running(base_url, max_retries=3):
    """Check if Flask app is running"""
    for attempt in range(max_retries):
        try:
            response = requests.get(f"{base_url}/", timeout=5)
            if response.status_code in [200, 302, 401, 403]:
                return True
        except requests.exceptions.ConnectionError:
            if attempt < max_retries - 1:
                print(f"Attempt {attempt + 1}: Flask app not responding, retrying in 2 seconds...")
                time.sleep(2)
            continue
        except Exception as e:
            print(f"Error checking Flask app: {e}")
            
    return False

def test_routes():
    base_url = "http://127.0.0.1:5000"
    
    # First check if Flask is running
    print("Checking if Flask app is running...")
    if not check_flask_running(base_url):
        print("❌ Cannot connect to Flask app!")
        print("\nTo fix this:")
        print("1. Open a terminal and navigate to your project directory")
        print("2. Activate your virtual environment:")
        print("   - Windows: venv\\Scripts\\activate")
        print("   - Linux/Mac: source venv/bin/activate")
        print("3. Start the Flask app: python app.py")
        print("4. Wait for 'Running on http://127.0.0.1:5000' message")
        print("5. Then run this script again in a NEW terminal window")
        return
    
    print("✅ Flask app is running!")
    
    routes_to_test = [
        ("GET", "/student/available-competitions", "Get available competitions"),
        ("POST", "/student/join-competition/1", "Join competition (will fail without auth but route should exist)"),
        ("GET", "/student/competition/1/status", "Get competition status"),
        ("POST", "/student/competition/1/start-station", "Start competition station"),
        ("POST", "/student/competition/complete-station", "Complete competition station"),
        ("GET", "/student/stats", "Get student stats"),
        ("GET", "/student/stations", "Get student stations")
    ]
    
    print("\nTesting competition routes...")
    print("=" * 70)
    
    working_routes = 0
    total_routes = len(routes_to_test)
    
    for method, route, description in routes_to_test:
        try:
            if method == "POST":
                response = requests.post(f"{base_url}{route}", timeout=5)
            else:
                response = requests.get(f"{base_url}{route}", timeout=5)
            
            # Check if route exists (not 404 with "Not Found" in response)
            if response.status_code == 404 and "Not Found" in response.text:
                print(f"❌ {method} {route}")
                print(f"   Description: {description}")
                print(f"   Error: Route does not exist (404)")
            elif response.status_code in [200, 302, 401, 403, 405, 500]:
                print(f"✅ {method} {route}")
                print(f"   Description: {description}")
                print(f"   Status: {response.status_code} ({get_status_description(response.status_code)})")
                working_routes += 1
            else:
                print(f"⚠️  {method} {route}")
                print(f"   Description: {description}")
                print(f"   Unexpected status: {response.status_code}")
                working_routes += 1  # Still counts as working
                
        except requests.exceptions.Timeout:
            print(f"⚠️  {method} {route}")
            print(f"   Description: {description}")
            print(f"   Error: Request timed out")
        except Exception as e:
            print(f"❌ {method} {route}")
            print(f"   Description: {description}")
            print(f"   Error: {str(e)}")
        
        print()  # Empty line for readability
    
    print("=" * 70)
    print(f"Results: {working_routes}/{total_routes} routes are working")
    
    if working_routes == total_routes:
        print("🎉 All routes are working! Your competition system should work.")
    elif working_routes >= total_routes * 0.8:  # 80% or more
        print("⚠️  Most routes are working. Check the failed ones above.")
    else:
        print("❌ Many routes are missing. Check your blueprints/student.py file.")
        print("\nNext steps:")
        print("1. Make sure you've updated blueprints/student.py with all competition routes")
        print("2. Restart your Flask app after making changes")
        print("3. Run this script again")

def get_status_description(status_code):
    """Get human-readable description of HTTP status codes"""
    descriptions = {
        200: "OK - Route exists and working",
        302: "Redirect - Route exists, probably redirecting to login",
        401: "Unauthorized - Route exists but requires authentication", 
        403: "Forbidden - Route exists but access denied",
        405: "Method Not Allowed - Route exists but wrong HTTP method",
        500: "Internal Server Error - Route exists but has a bug"
    }
    return descriptions.get(status_code, "Unknown status")

if __name__ == "__main__":
    test_routes()