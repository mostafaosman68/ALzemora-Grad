#!/usr/bin/env python3
"""
Test script to verify user-aware recognition works
Usage: python test_recognition.py <user_id>
"""

import sys
import os
import requests

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

def test_user_data(user_id):
    """Test if we can fetch user data from the backend"""
    try:
        print(f"Testing user data for: {user_id}")

        # Test getting people for user
        response = requests.get(f"{API_BASE_URL}/people/{user_id}", timeout=10)
        if response.status_code == 200:
            data = response.json()
            people_count = data.get("count", 0)
            print(f"✅ Found {people_count} people for user {user_id}")

            if people_count == 0:
                print("⚠️  No people registered for this user. Add friends/family first.")
                return False
            else:
                people = data.get("people", [])
                names = [p.get("name") for p in people if p.get("name")]
                print(f"   People: {', '.join(names)}")
                return True
        else:
            print(f"❌ Failed to get people: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        print(f"❌ Error testing user data: {e}")
        return False

def main():
    if len(sys.argv) != 2:
        print("Usage: python test_recognition.py <user_id>")
        print("Example: python test_recognition.py 507f1f77bcf86cd799439011")
        return 1

    user_id = sys.argv[1]

    print("🧪 Testing User-Aware Recognition Setup")
    print("=" * 40)

    # Test user data
    if not test_user_data(user_id):
        return 1

    print("\n✅ All tests passed! Ready to start recognition.")
    print(f"Run: python start_recognition.py {user_id}")

    return 0

if __name__ == "__main__":
    sys.exit(main())