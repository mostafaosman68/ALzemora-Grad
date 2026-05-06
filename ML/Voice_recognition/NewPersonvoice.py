import pyaudio
import wave
import os
import time

# ---------------- SETTINGS ----------------
USER_NAME = "Mostafa"  # Change this to the person you are recording
SAVE_PATH = r"C:\Users\ITD\Downloads\MOBILEFaceNet\voices"
TOTAL_CLIPS = 5        # We will record 5 clips
CLIP_DURATION = 5      # 5 seconds each
RATE = 16000           # Must match your other scripts

# ---------------- SETUP ----------------
person_folder = os.path.join(SAVE_PATH, USER_NAME)
if not os.path.exists(person_folder):
    os.makedirs(person_folder)

p = pyaudio.PyAudio()

print(f"\n🎙️  Recording clean samples for: {USER_NAME}")
print(f"📂 Saving to: {person_folder}")
print("   (Speak naturally, vary your tone slightly)")

for i in range(TOTAL_CLIPS):
    input(f"\nPress ENTER to record clip {i+1}/{TOTAL_CLIPS}...")
    
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True, frames_per_buffer=1024)
    frames = []

    print("   🔴 Recording... (Count to 5)")
    for _ in range(0, int(RATE / 1024 * CLIP_DURATION)):
        data = stream.read(1024)
        frames.append(data)

    print("   ✅ Done.")
    stream.stop_stream()
    stream.close()

    # Save file
    filename = os.path.join(person_folder, f"sample_{i}.wav")
    wf = wave.open(filename, 'wb')
    wf.setnchannels(1)
    wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()

p.terminate()
print("\n🎉 Recording complete! Now run Extract_Voice.py again.")