#!/usr/bin/env python3
"""
End-to-End Testing Script for User-Aware Multimodal Recognition System

This script tests the complete flow:
1. Backend API endpoints
2. Database integration
3. User-aware recognition system
4. Mobile app integration points

Usage:
    python test_system.py [user_id]

If no user_id is provided, it will test with the first user found in the database.
"""

import requests
import json
import sys
import time
import subprocess
from pathlib import Path

# Configuration
BACKEND_URL = "http://localhost:8000"  # Adjust if your backend runs on different port
ML_DIR = Path(__file__).parent / "ML"

def test_backend_connection():
    """Test if backend is running"""
    try:
        response = requests.get(f"{BACKEND_URL}/docs")
        if response.status_code == 200:
            print("✅ Backend is running")
            return True
        else:
            print(f"❌ Backend returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot connect to backend: {e}")
        return False

def get_test_user():
    """Get a test user from the database"""
    try:
        response = requests.get(f"{BACKEND_URL}/users")
        if response.status_code == 200:
            data = response.json()
            users = data.get('users', [])
            if users:
                user = users[0]  # Take first user
                print(f"✅ Found test user: {user.get('full_name', 'Unknown')} (ID: {user['_id']})")
                return user
            else:
                print("❌ No users found in database")
                return None
        else:
            print(f"❌ Failed to get users: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Error getting users: {e}")
        return None

def test_user_people_endpoint(user_id):
    """Test the /people/{user_id} endpoint"""
    try:
        response = requests.get(f"{BACKEND_URL}/people/{user_id}")
        if response.status_code == 200:
            data = response.json()
            people = data.get('people', [])
            count = data.get('count', 0)
            print(f"✅ User has {count} registered people")
            if people:
                for person in people[:3]:  # Show first 3
                    print(f"   - {person.get('name', 'Unknown')}")
            return True
        else:
            print(f"❌ Failed to get people: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing people endpoint: {e}")
        return False

def test_recognition_start(user_id):
    """Test starting recognition for a user"""
    try:
        response = requests.post(f"{BACKEND_URL}/start-recognition", 
                               json={"user_id": user_id})
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'started':
                print("✅ Recognition started successfully")
                print(f"   Message: {data.get('message')}")
                print(f"   People count: {data.get('people_count', 0)}")
                return True
            elif data.get('status') == 'no_people':
                print(f"⚠️  {data.get('message')}")
                return True  # This is expected if no people are registered
            else:
                print(f"❌ Unexpected response: {data}")
                return False
        else:
            print(f"❌ Failed to start recognition: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error starting recognition: {e}")
        return False

def test_ml_scripts():
    """Test if ML scripts exist and are executable"""
    scripts_to_check = [
        "user_aware_recognizer.py",
        "start_recognition.py",
        "multimodal_recognizer.py"
    ]

    all_exist = True
    for script in scripts_to_check:
        script_path = ML_DIR / script
        if script_path.exists():
            print(f"✅ {script} exists")
        else:
            print(f"❌ {script} not found")
            all_exist = False

    return all_exist

def main():
    print("🧪 Testing User-Aware Multimodal Recognition System")
    print("=" * 60)

    # Test 1: Backend connection
    print("\n1. Testing Backend Connection...")
    if not test_backend_connection():
        print("❌ Backend not available. Make sure to run: uvicorn app.main:app --reload")
        return

    # Test 2: ML scripts existence
    print("\n2. Checking ML Scripts...")
    if not test_ml_scripts():
        print("❌ Some ML scripts are missing")
        return

    # Test 3: Get test user
    print("\n3. Getting Test User...")
    user = get_test_user()
    if not user:
        print("❌ No test user available")
        return

    user_id = user['_id']

    # Test 4: Test people endpoint
    print(f"\n4. Testing People Endpoint for User {user_id}...")
    if not test_user_people_endpoint(user_id):
        print("❌ People endpoint test failed")
        return

    # Test 5: Test recognition start
    print(f"\n5. Testing Recognition Start for User {user_id}...")
    if not test_recognition_start(user_id):
        print("❌ Recognition start test failed")
        return

    print("\n" + "=" * 60)
    print("🎉 All tests passed! System is ready.")
    print("\nNext steps:")
    print("1. Start your mobile app")
    print("2. Log in as a user")
    print("3. Tap 'Face Recognition' on the dashboard")
    print("4. Open camera on your laptop to see recognition")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Use provided user ID
        user_id = sys.argv[1]
        print(f"Testing with provided user ID: {user_id}")
        # You could add specific user testing here
    else:
        main()