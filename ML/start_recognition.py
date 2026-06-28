#!/usr/bin/env python3
"""
User-Aware Multimodal Recognition Launcher
This script is called by the mobile app to start face/voice recognition
for a specific logged-in user.
"""

import sys
import os
import subprocess
import json

def main():
    if len(sys.argv) != 2:
        print("Usage: python start_recognition.py <user_id>")
        return 1

    user_id = sys.argv[1]
    print(f"Starting user-aware recognition for user: {user_id}")

    # Launch the user-aware recognizer
    recognizer_path = os.path.join(os.path.dirname(__file__), "user_aware_recognizer.py")

    try:
        # Set user_id in environment variable so recognizer doesn't need command-line argument
        env = os.environ.copy()
        env["USER_ID_FOR_RECOGNITION"] = user_id
        
        # Run the recognizer (this will block until user presses 'q')
        # No need to pass user_id as argument - it's in environment variable
        subprocess.run([sys.executable, recognizer_path], env=env, check=True)
        return 0
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Recognizer failed with code {e.returncode}")
        return e.returncode
    except KeyboardInterrupt:
        print("Recognition stopped by user")
        return 0

if __name__ == "__main__":
    sys.exit(main())