# User-Aware Multimodal Recognition System

This system connects your mobile app with a laptop-based face and voice recognition system that only recognizes people associated with the logged-in user/patient.

## 🚀 How It Works

1. **User logs in** on mobile app (User, Guardian, or CareGiver)
2. **Tap "Face Recognition"** on dashboard
3. **System starts** on your laptop, loading only people known to that user
4. **Camera opens** and recognizes faces/voices of friends/family for that specific patient

## 📁 Files Created

- `user_aware_recognizer.py` - Main recognition system (loads user-specific data)
- `start_recognition.py` - Launcher script called by mobile app
- `test_recognition.py` - Test script to verify setup

## 🔧 Backend Changes

- **New endpoint**: `GET /people/{user_id}` - Get people for specific user
- **New endpoint**: `POST /start-recognition` - Start recognition for logged-in user (user_id in request body)
- **User-aware filtering**: Only loads people associated with the requesting user

## 📱 Mobile App Changes

- **New button**: "Face Recognition 👁️" added to dashboard
- **Smart user detection**: Links to correct patient automatically
- **API integration**: Calls backend to start laptop recognition

## 🖥️ How to Use

### 1. From Mobile App (Recommended) ✨
- Log in as User/Guardian/CareGiver
- Go to Dashboard
- Tap "Face Recognition"
- **No manual user ID needed** - Backend automatically handles it!
- Recognition starts on your laptop

### 2. Manual Testing (with User ID)
```bash
# Option A: Using command-line argument
python user_aware_recognizer.py <user_id>
python user_aware_recognizer.py 507f1f77bcf86cd799439011

# Option B: Using environment variable (same as backend uses)
USER_ID_FOR_RECOGNITION=<user_id> python user_aware_recognizer.py
set USER_ID_FOR_RECOGNITION=507f1f77bcf86cd799439011 && python user_aware_recognizer.py
```

### 3. Direct Backend Testing
```bash
# Test if user has data
python test_recognition.py <user_id>

# Start recognition via launcher (automatically uses environment variable)
python start_recognition.py <user_id>
```

### 4. API Testing
```bash
# Get people for user
curl http://192.168.1.19:8000/people/<user_id>

# Start recognition (sends user_id in JSON body)
curl -X POST http://192.168.1.19:8000/start-recognition \
  -H "Content-Type: application/json" \
  -d '{"user_id": "<user_id>"}'
```

## 🔐 Security & Privacy

- **User-specific**: Only recognizes people added by/for that user
- **Patient-focused**: Guardians/Caregivers see their patient's people
- **No cross-contamination**: Users can't see each other's data

## 🎯 Recognition Features

- **Face Recognition**: Detects and identifies faces using InsightFace
- **Voice Recognition**: Uses ECAPA-TDNN for speaker identification
- **Fusion**: Combines face + voice for better accuracy
- **Real-time**: Processes video/audio streams live
- **User-aware**: Only knows people associated with logged-in user

## 🛠️ Requirements

- Python 3.8+
- Webcam + Microphone on laptop
- Mobile app connected to same network
- People/friends added for the user

## 🎨 UI Indicators

- **Green box**: Recognized person
- **Red box**: Unknown person
- **Orange box**: Speaker not visible (voice-only recognition)
- **Bottom status**: Shows voice recognition status and current user

Press **'Q'** to quit recognition on laptop.

## 🧪 Testing the System

### Quick System Test
Run the comprehensive test script from the project root:

```bash
python test_system.py
```

This will test:
- ✅ Backend connection
- ✅ ML scripts existence
- ✅ Database user data
- ✅ API endpoints
- ✅ Recognition start

### Manual Testing Steps

1. **Start Backend**:
   ```bash
   cd Backend
   uvicorn app.main:app --reload
   ```

2. **Test API Endpoints**:
   ```bash
   # Get all users
   curl http://localhost:8000/users

   # Get people for a user (replace USER_ID)
   curl http://localhost:8000/people/USER_ID

   # Start recognition (replace USER_ID)
   curl -X POST http://localhost:8000/start-recognition/USER_ID
   ```

3. **Test ML Scripts**:
   ```bash
   cd ML
   python test_recognition.py USER_ID
   ```

4. **Mobile App Testing**:
   - Start React Native app
   - Log in as a user
   - Go to Dashboard
   - Tap "Face Recognition"
   - Check laptop for camera opening

### Troubleshooting

- **"No people registered"**: Add friends/family using "Add Friends" in mobile app
- **"Backend not running"**: Make sure `uvicorn app.main:app --reload` is running
- **"Recognition script not found"**: Check that `ML/start_recognition.py` exists
- **Camera doesn't open**: Check webcam permissions and that no other app is using camera