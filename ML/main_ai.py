import RPi.GPIO as GPIO
import time
import subprocess
import sys

PIN = 17
GPIO.cleanup()           # reset first
GPIO.setmode(GPIO.BCM)   # set mode AFTER cleanup
GPIO.setup(PIN, GPIO.IN)

camera_running = False
process = None

def start_camera():
    global camera_running, process
    if not camera_running:
        print("Camera ON")
        process = subprocess.Popen([sys.executable, "multimodal_recognizer.py"])
        camera_running = True

def stop_camera():
    global camera_running, process
    if camera_running:
        print("Camera OFF")
        process.terminate()
        process = None
        camera_running = False

bright_counter = 0
THRESHOLD = 3

try:
    while True:
        value = GPIO.input(PIN)
        if value == 1:       # LIGHT ? glasses worn
            bright_counter += 1
        else:
            bright_counter = 0

        if bright_counter >= THRESHOLD:
            start_camera()
        else:
            stop_camera()

        time.sleep(0.3)

except KeyboardInterrupt:
    print("Exiting...")
    if process:
        process.terminate()
    GPIO.cleanup()