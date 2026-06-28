import messaging from '@react-native-firebase/messaging';
import {Platform} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

const FCM_TOKEN_KEY = 'fcm_device_token';
const BACKEND_URL = require('../config').BASE_URL;

export async function initializeMessaging() {
  try {
    // Request notification permission on Android 13+
    if (Platform.OS === 'android') {
      await messaging().requestPermission();
    }

    // Get FCM token
    const token = await messaging().getToken();
    console.log('[FCM] Device token obtained:', token);

    // Store locally
    await AsyncStorage.setItem(FCM_TOKEN_KEY, token);

    return token;
  } catch (error) {
    console.log('[FCM] Failed to initialize messaging:', error.message);
    return null;
  }
}

export async function registerFCMToken(patientId) {
  if (!patientId) {
    console.log('[FCM] patient_id not provided');
    return false;
  }

  try {
    let token = await AsyncStorage.getItem(FCM_TOKEN_KEY);
    if (!token) {
      // Recover from cold start race: generate token now if it has not been cached yet.
      token = await initializeMessaging();
    }

    if (!token) {
      console.log('[FCM] No token available after initialization');
      return false;
    }

    const response = await fetch(`${BACKEND_URL}/users/fcm-token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({
        patient_id: patientId,
        fcm_token: token,
      }),
    });

    const data = await response.json();

    if (!response.ok || data?.error) {
      throw new Error(data?.error || `HTTP ${response.status}`);
    }

    console.log('[FCM] Token registered successfully');
    return true;
  } catch (error) {
    console.log('[FCM] Failed to register token:', error.message);
    return false;
  }
}

export function setupForegroundNotificationHandler(onNotification) {
  const unsubscribe = messaging().onMessage(async (remoteMessage) => {
    console.log('[FCM] Foreground notification:', remoteMessage);

    if (onNotification) {
      onNotification(remoteMessage);
    }
  });

  return unsubscribe;
}

export function setupBackgroundNotificationHandler() {
  messaging().onNotificationOpenedApp((remoteMessage) => {
    console.log('[FCM] App opened from background notification:', remoteMessage);
  });

  // Check if the app was opened from a notification when it was completely closed
  messaging()
    .getInitialNotification()
    .then((remoteMessage) => {
      if (remoteMessage) {
        console.log('[FCM] App opened from quit state by notification:', remoteMessage);
      }
    });
}

export async function getFCMToken() {
  return await AsyncStorage.getItem(FCM_TOKEN_KEY);
}
