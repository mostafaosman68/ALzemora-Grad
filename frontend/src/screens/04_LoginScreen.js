import {useState} from 'react';
import {
  Text,
  View,
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
  Subtitle,
  CardTitle,
  COLORS,
} from '../components/UI';
import {useAuth} from '../../App';
import { BASE_URL } from '../config';

const API_URL = BASE_URL;

const ROLES = ['User', 'Guardian', 'CareGiver'];

export default function LoginScreen({navigation}) {
  const {setUser} = useAuth();

  const [role,        setRole]        = useState('User');
  const [email,       setEmail]       = useState('');
  const [password,    setPassword]    = useState('');
  const [patientName, setPatientName] = useState('');
  const [loading,     setLoading]     = useState(false);

  const isHelper = role === 'Guardian' || role === 'CareGiver';

  const isValid =
    email.trim().length > 0 &&
    password.length > 0 &&
    (!isHelper || patientName.trim().length > 0);

  const handleLogin = async () => {
    if (!email.trim()) {
      Alert.alert('Missing Info', 'Please enter your email.');
      return;
    }
    if (!password) {
      Alert.alert('Missing Info', 'Please enter your password.');
      return;
    }
    if (isHelper && !patientName.trim()) {
      Alert.alert('Missing Info', 'Please enter the patient\'s name.');
      return;
    }

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('email',    email.trim().toLowerCase());
      formData.append('password', password);
      formData.append('role',     role);
      if (isHelper) {
        formData.append('patient_name', patientName.trim());
      }

      const response = await fetch(`${API_URL}/login`, {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
        },
        body: formData,
      });

      const data = await response.json();

      if (data.error) {
        Alert.alert('Login Failed', data.error);
        return;
      }

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

            <CardTitle>Login</CardTitle>

            <Subtitle
              text="First Time?"
              linkText="Sign Up"
              onLinkPress={() => navigation.navigate('AccountType')}
            />

            {/* Role selector */}
            <Text style={styles.roleLabel}>Account Type:</Text>
            <View style={styles.roleRow}>
              {ROLES.map(r => (
                <TouchableOpacity
                  key={r}
                  style={[styles.roleChip, role === r && styles.roleChipSelected]}
                  onPress={() => {
                    setRole(r);
                    setPatientName(''); // reset patient name when switching
                  }}>
                  <Text style={[styles.roleChipText, role === r && styles.roleChipTextSelected]}>
                    {r}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

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

            {/* Patient name — only for Guardian and CareGiver */}
            {isHelper && (
              <>
                <View style={styles.divider} />
                <Text style={styles.patientNote}>
                  Enter the full name of the patient you are caring for.
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
              </View>
            ) : (
              <DarkBtn
                title="Login"
                onPress={handleLogin}
                disabled={!isValid}
                style={styles.btn}
              />
            )}

            <Subtitle
              linkText="Forgot Password?"
              onLinkPress={() => navigation.navigate('SignUp')}
            />

          </ScrollView>
        </Card>
      </KeyboardAvoidingView>
    </ScreenBg>
  );
}

const styles = StyleSheet.create({
  roleLabel: {
    fontSize: 13,
    fontWeight: '200',
    color: COLORS.text,
    marginBottom: 8,
    marginLeft: 4,
  },
  roleRow: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 16,
  },
  roleChip: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 20,
    backgroundColor: '#e0e0e0',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#ccc',
  },
  roleChipSelected: {
    backgroundColor: COLORS.dark,
    borderColor: COLORS.dark,
  },
  roleChipText: {
    fontSize: 13,
    fontWeight: '500',
    color: COLORS.text,
  },
  roleChipTextSelected: {
    color: COLORS.white,
    fontWeight: '700',
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
    marginBottom: 10,
  },
  btn: {marginTop: 16, marginBottom: 6},
  loadingContainer: {marginTop: 20, alignItems: 'center'},
  forgot: {
    textAlign: 'center',
    marginTop: 16,
    fontSize: 11,
    fontWeight: '200',
    color: COLORS.text,
  },
  forgotUnderline: {
    textDecorationLine: 'underline',
    fontWeight: '400',
  },
});