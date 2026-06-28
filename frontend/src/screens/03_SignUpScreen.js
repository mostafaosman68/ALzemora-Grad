import React, {useState} from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  Alert,
  ActivityIndicator,
} from 'react-native';
import {
  ScreenBg,
  BrandHeader,
  Card,
  GrayInput,
  DarkBtn,
  Subtitle,
  CardTitle,
  COLORS,
} from '../components/UI';
import {useAuth} from '../../App';
import { BASE_URL } from '../config';

const API_URL = BASE_URL;

export default function SignUpScreen({navigation, route}) {
  const {setUser} = useAuth();
  const accountType = route.params?.accountType || 'User';

  const isHelper = accountType === 'Guardian' || accountType === 'CareGiver';

  const [fullName,    setFullName]    = useState('');
  const [age,         setAge]         = useState('');
  const [email,       setEmail]       = useState('');
  const [password,    setPassword]    = useState('');
  const [confirm,     setConfirm]     = useState('');
  const [patientName, setPatientName] = useState('');
  const [loading,     setLoading]     = useState(false);

  const isValid =
    fullName.trim().length > 0 &&
    age.trim().length > 0 &&
    email.trim().length > 0 &&
    password.length > 0 &&
    confirm.length > 0 &&
    (!isHelper || patientName.trim().length > 0); // patient name required for helpers

  const handleSignUp = async () => {
    if (!fullName.trim()) {
      Alert.alert('Missing Info', 'Please enter your full name.');
      return;
    }
    if (!age.trim()) {
      Alert.alert('Missing Info', 'Please enter your age.');
      return;
    }
    const ageNum = parseInt(age, 10);
    if (isNaN(ageNum) || ageNum < 1 || ageNum > 150) {
      Alert.alert('Invalid Age', 'Please enter a valid age between 1 and 150.');
      return;
    }
    if (!email.trim()) {
      Alert.alert('Missing Info', 'Please enter your email.');
      return;
    }
    if (!password) {
      Alert.alert('Missing Info', 'Please enter a password.');
      return;
    }
    if (password !== confirm) {
      Alert.alert('Password Mismatch', 'Passwords do not match.');
      return;
    }
    if (password.length < 6) {
      Alert.alert('Weak Password', 'Password must be at least 6 characters.');
      return;
    }
    if (isHelper && !patientName.trim()) {
      Alert.alert('Missing Info', 'Please enter the patient\'s name.');
      return;
    }

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('email',     email.trim().toLowerCase());
      formData.append('password',  password);
      formData.append('full_name', fullName.trim());
      formData.append('age',       parseInt(age, 10));
      formData.append('role',      accountType);
      if (isHelper) {
        formData.append('patient_name', patientName.trim());
      }

      const response = await fetch(`${API_URL}/users/create-user`, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (data.error) {
        Alert.alert('Sign Up Failed', data.error);
        return;
      }

      // Auto-login after signup
      setUser(data);
      navigation.replace('Dashboard');

    } catch (err) {
      Alert.alert(
        'Connection Error',
        'Could not reach the server. Make sure your backend is running and you are on the same Wi-Fi.',
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <ScreenBg>
      <BrandHeader />

      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={StyleSheet.absoluteFill}>
        <Card topRightRadius={60}>
          <ScrollView
            showsVerticalScrollIndicator={false}
            keyboardShouldPersistTaps="handled">

            {/* Account type badge */}
            <View style={styles.badge}>
              <Text style={styles.badgeText}>{accountType}</Text>
            </View>

            <CardTitle>Create account</CardTitle>

            <Subtitle
              text="Already have an account?"
              linkText="Sign in"
              onLinkPress={() => navigation.navigate('Login')}
            />

            <GrayInput
              label="Full Name:"
              placeholder="Ahmed Hany"
              value={fullName}
              onChangeText={setFullName}
            />
            <GrayInput
              label="Age:"
              placeholder="25"
              value={age}
              onChangeText={setAge}
              keyboardType="number-pad"
            />
            <GrayInput
              label="Email:"
              placeholder="ahmed@gmail.com"
              value={email}
              onChangeText={setEmail}
              keyboardType="email-address"
            />
            <GrayInput
              label="Password:"
              placeholder="••••••"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
            />
            <GrayInput
              label="Confirm Password:"
              placeholder="••••••"
              value={confirm}
              onChangeText={setConfirm}
              secureTextEntry
            />

            {/* Patient name — only shown for Guardian and CareGiver */}
            {isHelper && (
              <>
                <View style={styles.divider} />
                <Text style={styles.patientNote}>
                  Enter the full name of the patient you are caring for.
                  They must already have a registered account.
                </Text>
                <GrayInput
                  label="Patient Name:"
                  placeholder="Patient's full name"
                  value={patientName}
                  onChangeText={setPatientName}
                />
              </>
            )}

            {loading ? (
              <View style={styles.loadingContainer}>
                <ActivityIndicator size="large" color={COLORS.dark} />
                <Text style={styles.loadingText}>Creating account...</Text>
              </View>
            ) : (
              <DarkBtn
                title="Sign Up"
                onPress={handleSignUp}
                disabled={!isValid}
                style={styles.btn}
              />
            )}

          </ScrollView>
        </Card>
      </KeyboardAvoidingView>
    </ScreenBg>
  );
}

const styles = StyleSheet.create({
  badge: {
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(28,33,32,0.1)',
    borderRadius: 20,
    paddingHorizontal: 14,
    paddingVertical: 4,
    marginBottom: 10,
  },
  badgeText: {
    fontSize: 12,
    fontWeight: '500',
    color: '#2a4a5c',
  },
  divider: {
    height: 1,
    backgroundColor: 'rgba(0,0,0,0.1)',
    marginVertical: 14,
  },
  patientNote: {
    fontSize: 12,
    fontWeight: '300',
    color: COLORS.subtext,
    marginBottom: 12,
    lineHeight: 18,
  },
  btn: {
    marginTop: 14,
    marginBottom: 10,
  },
  loadingContainer: {
    marginTop: 20,
    alignItems: 'center',
    gap: 8,
  },
  loadingText: {
    fontSize: 13,
    color: COLORS.subtext,
    fontWeight: '300',
  },
});