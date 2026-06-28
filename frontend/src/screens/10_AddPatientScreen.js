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
  TouchableOpacity,
} from 'react-native';
import {
  ScreenBg,
  BrandHeader,
  Card,
  GrayInput,
  DarkBtn,
  BackBtn,
  CardTitle,
  COLORS,
} from '../components/UI';
import {useAuth} from '../../App';
import { BASE_URL } from '../config';

export default function AddPatientScreen({navigation}) {
  const {user, setUser} = useAuth();
  const [mode, setMode] = useState('new'); // 'new' or 'existing'
  const [fullName, setFullName] = useState('');
  const [age, setAge] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [patientEmail, setPatientEmail] = useState('');
  const [patientPassword, setPatientPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const isValidNew =
    fullName.trim().length > 0 &&
    age.trim().length > 0 &&
    email.trim().length > 0 &&
    password.length > 0 &&
    confirm.length > 0;
  const isValidExisting = patientEmail.trim().length > 0 && patientPassword.length > 0;

  const handleAddNewPatient = async () => {
    if (!fullName.trim()) {
      Alert.alert('Missing Info', 'Please enter the patient\'s full name.');
      return;
    }
    if (!age.trim()) {
      Alert.alert('Missing Info', 'Please enter the patient\'s age.');
      return;
    }
    const ageNum = parseInt(age, 10);
    if (isNaN(ageNum) || ageNum < 1 || ageNum > 150) {
      Alert.alert('Invalid Age', 'Please enter a valid age between 1 and 150.');
      return;
    }
    if (!email.trim()) {
      Alert.alert('Missing Info', 'Please enter the patient\'s email.');
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

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('email', email.trim().toLowerCase());
      formData.append('password', password);
      formData.append('full_name', fullName.trim());
      formData.append('role', 'User');
      formData.append('age', ageNum);
      if (user?.role === 'Guardian' || user?.role === 'CareGiver') {
        formData.append('editor_user_id', user.user_id);
        formData.append('editor_role', user.role);
      }

      const response = await fetch(`${BASE_URL}/users/create-user`, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (data.error) {
        Alert.alert('Failed to Add Patient', data.error);
        return;
      }

      if ((user?.role === 'Guardian' || user?.role === 'CareGiver') && Array.isArray(data.patient_links)) {
        setUser((prev) => ({
          ...prev,
          patient_name: data.patient_name,
          patient_id: data.patient_id,
          patient_links: data.patient_links,
        }));
      }

      Alert.alert(
        'Patient Added Successfully',
        `Patient account created for ${data.email}`,
        [{text: 'OK', onPress: () => navigation.goBack()}]
      );

    } catch (err) {
      Alert.alert(
        'Connection Error',
        'Could not reach the server. Make sure your backend is running and you are on the same Wi-Fi.',
      );
    } finally {
      setLoading(false);
    }
  };

  const handleLinkExistingPatient = async () => {
    if (!user?.user_id || !user?.role) {
      Alert.alert('Session Error', 'Could not identify the logged in account. Please sign in again.');
      return;
    }
    if (!patientEmail.trim()) {
      Alert.alert('Missing Info', 'Please enter the patient\'s email.');
      return;
    }
    if (!patientPassword) {
      Alert.alert('Missing Info', 'Please enter the patient\'s password.');
      return;
    }

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('editor_user_id', user.user_id);
      formData.append('editor_role', user.role);
      formData.append('patient_email', patientEmail.trim().toLowerCase());
      formData.append('patient_password', patientPassword);

      const response = await fetch(`${BASE_URL}/users/link-existing-patient`, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (data.error) {
        Alert.alert('Failed to Link Patient', data.error);
        return;
      }

      setUser((prev) => ({
        ...prev,
        patient_name: data.patient_name,
        patient_id: data.patient_id,
        patient_links: Array.isArray(data.patient_links) ? data.patient_links : prev?.patient_links,
      }));

      Alert.alert(
        'Patient Linked Successfully',
        `You are now linked to ${data.patient_name}`,
        [{text: 'OK', onPress: () => navigation.goBack()}]
      );

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

            <BackBtn onPress={() => navigation.goBack()} />

            <CardTitle>Add Patient</CardTitle>

            {/* Mode Selection */}
            <View style={styles.modeContainer}>
              <TouchableOpacity
                style={[styles.modeButton, mode === 'new' && styles.modeButtonActive]}
                onPress={() => setMode('new')}
                activeOpacity={0.8}>
                <Text style={[styles.modeButtonText, mode === 'new' && styles.modeButtonTextActive]}>
                  Create New Patient
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.modeButton, mode === 'existing' && styles.modeButtonActive]}
                onPress={() => setMode('existing')}
                activeOpacity={0.8}>
                <Text style={[styles.modeButtonText, mode === 'existing' && styles.modeButtonTextActive]}>
                  Link Existing Patient
                </Text>
              </TouchableOpacity>
            </View>

            {mode === 'new' ? (
              <>
                <Text style={styles.description}>
                  Create a new patient account. The patient will be able to log in with their email and password.
                </Text>

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
                  placeholder="patient@example.com"
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

                {loading ? (
                  <View style={styles.loadingContainer}>
                    <ActivityIndicator size="large" color={COLORS.teal} />
                    <Text style={styles.loadingText}>Creating patient account...</Text>
                  </View>
                ) : (
                  <DarkBtn
                    title="Create Patient"
                    onPress={handleAddNewPatient}
                    disabled={!isValidNew}
                  />
                )}
              </>
            ) : (
              <>
                <Text style={styles.description}>
                  Link your current account to an existing patient. Each patient can have up to 2 guardians and 1 caregiver.
                </Text>

                <GrayInput
                  label="Patient Email:"
                  placeholder="patient@example.com"
                  value={patientEmail}
                  onChangeText={setPatientEmail}
                  keyboardType="email-address"
                />
                <GrayInput
                  label="Patient Password:"
                  placeholder="••••••"
                  value={patientPassword}
                  onChangeText={setPatientPassword}
                  secureTextEntry
                />

                {loading ? (
                  <View style={styles.loadingContainer}>
                    <ActivityIndicator size="large" color={COLORS.teal} />
                    <Text style={styles.loadingText}>Linking to patient...</Text>
                  </View>
                ) : (
                  <DarkBtn
                    title="Link Patient"
                    onPress={handleLinkExistingPatient}
                    disabled={!isValidExisting}
                  />
                )}
              </>
            )}
          </ScrollView>
        </Card>
      </KeyboardAvoidingView>
    </ScreenBg>
  );
}

const styles = StyleSheet.create({
  modeContainer: {
    flexDirection: 'row',
    marginBottom: 20,
    gap: 10,
  },
  modeButton: {
    flex: 1,
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: COLORS.inputBorder,
    backgroundColor: COLORS.inputLight,
    alignItems: 'center',
  },
  modeButtonActive: {
    backgroundColor: COLORS.teal,
    borderColor: COLORS.teal,
  },
  modeButtonText: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.subtext,
  },
  modeButtonTextActive: {
    color: COLORS.white,
  },
  description: {
    fontSize: 14,
    color: COLORS.subtext,
    marginBottom: 20,
    lineHeight: 20,
  },
  loadingContainer: {
    alignItems: 'center',
    paddingVertical: 40,
  },
  loadingText: {
    marginTop: 10,
    fontSize: 16,
    color: COLORS.subtext,
  },
});