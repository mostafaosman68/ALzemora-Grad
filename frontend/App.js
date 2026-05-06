import React, {createContext, useContext, useState, useEffect} from 'react';
import {NavigationContainer} from '@react-navigation/native';
import {createNativeStackNavigator} from '@react-navigation/native-stack';
import {SafeAreaProvider} from 'react-native-safe-area-context';
import {PermissionsAndroid, Platform} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

import SplashScreen      from './src/screens/01_SplashScreen';
import AccountTypeScreen from './src/screens/02_AccountTypeScreen';
import SignUpScreen      from './src/screens/03_SignUpScreen';
import LoginScreen       from './src/screens/04_LoginScreen';
import DashboardScreen   from './src/screens/05_DashboardScreen';
import GeoLocationScreen from './src/screens/06_GeoLocationScreen';
import AddFriendScreen   from './src/screens/07_AddFriendScreen';
import AddMedScreen      from './src/screens/08_AddMedScreen';
import UserProfileScreen from './src/screens/09_UserProfileScreen';
import AddPatientScreen  from './src/screens/10_AddPatientScreen';
import HBScreen          from './src/screens/11_HBScreen';

const Stack = createNativeStackNavigator();

/* ─── Auth Context ───────────────────────────────────────── */
export const AuthContext = createContext(null);

export function useAuth() {
  return useContext(AuthContext);
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const requestNotificationPermission = async () => {
      if (Platform.OS !== 'android' || Platform.Version < 33) {
        return;
      }

      try {
        await PermissionsAndroid.request(PermissionsAndroid.PERMISSIONS.POST_NOTIFICATIONS);
      } catch (error) {
        console.log('[NOTIFICATIONS] Permission request failed:', error);
      }
    };

    requestNotificationPermission();
  }, []);

  // Load user data from AsyncStorage on app start
  useEffect(() => {
    const loadUser = async () => {
      try {
        const userData = await AsyncStorage.getItem('user');
        if (userData) {
          setUser(JSON.parse(userData));
          console.log('[AUTH] User loaded from storage:', JSON.parse(userData).full_name);
        }
      } catch (error) {
        console.log('[AUTH] Error loading user from storage:', error);
      } finally {
        setIsLoading(false);
      }
    };
    loadUser();
  }, []);

  // Save user data to AsyncStorage whenever user changes
  useEffect(() => {
    const saveUser = async () => {
      try {
        if (user) {
          await AsyncStorage.setItem('user', JSON.stringify(user));
          console.log('[AUTH] User saved to storage:', user.full_name);
        } else {
          await AsyncStorage.removeItem('user');
          console.log('[AUTH] User removed from storage');
        }
      } catch (error) {
        console.log('[AUTH] Error saving user to storage:', error);
      }
    };

    // Only save after initial loading is complete
    if (!isLoading) {
      saveUser();
    }
  }, [user, isLoading]);

  const logout = async () => {
    try {
      await AsyncStorage.removeItem('user');
      setUser(null);
      console.log('[AUTH] User logged out and storage cleared');
    } catch (error) {
      console.log('[AUTH] Error during logout:', error);
      // Still clear user state even if storage fails
      setUser(null);
    }
  };

  // Show loading screen while checking for stored user
  if (isLoading) {
    return (
      <SafeAreaProvider>
        <NavigationContainer>
          <Stack.Navigator screenOptions={{ headerShown: false }}>
            <Stack.Screen name="Splash" component={SplashScreen} />
          </Stack.Navigator>
        </NavigationContainer>
      </SafeAreaProvider>
    );
  }

  return (
    <AuthContext.Provider value={{user, setUser, logout}}>
      <SafeAreaProvider>
        <NavigationContainer>
          <Stack.Navigator
            initialRouteName={user ? "Dashboard" : "Splash"}
            screenOptions={{
              headerShown: false,
              animation: 'slide_from_right',
              contentStyle: {backgroundColor: '#11232e'},
            }}>
            <Stack.Screen name="Splash"       component={SplashScreen} />
            <Stack.Screen name="AccountType"  component={AccountTypeScreen} />
            <Stack.Screen name="SignUp"       component={SignUpScreen} />
            <Stack.Screen name="Login"        component={LoginScreen} />
            <Stack.Screen name="Dashboard"    component={DashboardScreen} />
            <Stack.Screen name="GeoLocation"  component={GeoLocationScreen} />
            <Stack.Screen name="HB"           component={HBScreen} />
            <Stack.Screen name="AddFriend"    component={AddFriendScreen} />
            <Stack.Screen name="AddMed"       component={AddMedScreen} />
            <Stack.Screen name="UserProfile"  component={UserProfileScreen} />
            <Stack.Screen name="AddPatient"   component={AddPatientScreen} />
          </Stack.Navigator>
        </NavigationContainer>
      </SafeAreaProvider>
    </AuthContext.Provider>
  );
}

export default function App() {
  return (
    <AuthProvider />
  );
}