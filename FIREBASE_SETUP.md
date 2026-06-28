# Firebase Setup for Push Notifications

## Overview
Push notifications are now integrated with Firebase Cloud Messaging (FCM). This allows the app to receive notifications even when it's closed.

## Setup Steps

### 1. Create a Firebase Project

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Click "Create a project" or use an existing project
3. Name it "Alzemora" or similar
4. Enable Google Analytics (optional)

### 2. Add Android App to Firebase

1. In the Firebase Console, click the Android icon to add an Android app
2. Package name: `com.alzemora.app` (or your package name from AndroidManifest.xml)
3. App nickname: "Alzemora Android"
4. Register the app
5. Download the `google-services.json` file

### 3. Place google-services.json

Place the downloaded `google-services.json` file in:
```
frontend/android/app/google-services.json
```

### 4. Get Service Account Key (for Backend)

1. In Firebase Console, go to **Project Settings** (gear icon)
2. Click the **Service Accounts** tab
3. Click **Generate a new private key**
4. Save the JSON file securely, rename it to `firebase-credentials.json`

### 5. Configure Backend

**Option A: Environment Variable (Recommended)**
```bash
export FIREBASE_CREDENTIALS_PATH=/path/to/firebase-credentials.json
```

**Option B: GOOGLE_APPLICATION_CREDENTIALS**
```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/firebase-credentials.json
```

### 6. Update Android Build Configuration

The Firebase libraries are already added to `package.json`. After setting up google-services.json, run:

```bash
cd frontend
npm install
cd ../
```

### 7. Rebuild the Android App

```bash
cd frontend
npm run android:device
# or
npm run android
```

## How It Works

### Backend Flow:
1. Heart rate reading received from Polar sensor (BPM > 90)
2. Backend sends push notification via Firebase to patient's device
3. Alert also stored in database for history

### Frontend Flow:
1. App initializes Firebase messaging on startup
2. Retrieves FCM device token automatically
3. Registers token with backend when user logs in
4. Receives push notifications even when app is closed
5. User sees system-level notification (like WhatsApp)

## Testing Push Notifications

1. Start the backend with patient ID configured:
```bash
$env:POLAR_PATIENT_ID="69e4dddc1f634d107d9f1388"
uvicorn app.main:app --reload
```

2. Run the mobile app on Android device

3. Open the HB Monitor screen

4. If Polar sensor reads BPM > 90, a push notification will appear on the device

## Troubleshooting

**No notifications appearing?**
- Verify `google-services.json` is in `frontend/android/app/`
- Check Firebase console for errors
- Ensure Android device has internet connection
- Allow notifications in Android settings

**FCM token not registering?**
- Check backend logs for Firebase initialization errors
- Verify service account JSON has correct permissions
- Ensure FIREBASE_CREDENTIALS_PATH is correct

**Backend errors?**
- Install firebase-admin: `pip install firebase-admin`
- Verify service account JSON path is correct
- Check Backend logs for initialization messages
