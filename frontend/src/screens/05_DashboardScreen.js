import React, {useState, useEffect} from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Dimensions,
  Platform,
  Alert,
  ActivityIndicator,
} from 'react-native';
import {useFocusEffect} from '@react-navigation/native';
import {ScreenBg, TopBar, COLORS} from '../components/UI';
import {useAuth} from '../../App';
import { BASE_URL } from '../config';

const {width} = Dimensions.get('window');

const MENU_ITEMS = [
  {label: 'Profile', icon: '🧑', screen: 'UserProfile'},
  {label: 'Add Friends',  icon: '👥', screen: 'AddFriend'},
  {label: 'Add Meds',     icon: '💊', screen: 'AddMed'},
  
  {label: 'HB',           icon: '💓', screen: 'HB'},
  {label: 'GEO-Location', icon: '📍', screen: 'GeoLocation'},
  {label: 'Face Recognition', icon: '👁️', action: 'startRecognition'},
];

const getAccountLabel = (role) => {
  if (role === 'Guardian') return 'Guardian Account';
  if (role === 'CareGiver') return 'Caregiver Account';
  return 'Patient Account';
};

const DEMO_MEDICATIONS = {
  default: [
    {name: 'Donepezil 5mg', schedule: '8:00 AM'},
    {name: 'Memantine 10mg', schedule: '2:00 PM'},
    {name: 'Vitamin D', schedule: '9:00 PM'},
  ],
  alternate: [
    {name: 'Aspirin 81mg', schedule: '7:30 AM'},
    {name: 'Metformin 500mg', schedule: '1:00 PM'},
    {name: 'Atorvastatin 20mg', schedule: '9:30 PM'},
  ],
};

export default function DashboardScreen({navigation}) {
  const {user, setUser} = useAuth();
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [stats, setStats] = useState({
    friends_count: 0,
    meds_count: 0,
    status: 'Active'
  });

  const isHelper = user?.role === 'Guardian' || user?.role === 'CareGiver';
  const helperPatients = isHelper
    ? (
      Array.isArray(user?.patient_links) && user.patient_links.length > 0
        ? user.patient_links
        : (user?.patient_id
          ? [{patient_id: user.patient_id, patient_name: user.patient_name}]
          : [])
    )
    : [];

  const activePatientIndex = helperPatients.findIndex(
    (item) => item?.patient_id && item.patient_id === user?.patient_id,
  );
  const safeActivePatientIndex = activePatientIndex >= 0 ? activePatientIndex : 0;

  // Get first name only for the greeting
  const firstName = user?.full_name?.split(' ')[0] ?? 'User';

  const getTimeGreeting = () => {
    const hour = new Date().getHours();
    if (hour >= 5 && hour < 12) return 'Good Morning';
    if (hour >= 12 && hour < 20) return 'Good Afternoon';
    return 'Good Evening';
  };

  const getGreetingEmoji = () => {
    const hour = new Date().getHours();
    if (hour >= 5 && hour < 12) return '☀️';
    if (hour >= 12 && hour < 20) return '🌤️';
    return '🌙';
  };

  const timeGreeting = getTimeGreeting();
  const timeEmoji = getGreetingEmoji();

  useEffect(() => {
    if (isHelper && helperPatients.length > 0 && !user?.patient_id) {
      const first = helperPatients[0];
      setUser((prev) => ({
        ...prev,
        patient_id: first?.patient_id,
        patient_name: first?.patient_name,
      }));
    }
  }, [isHelper, helperPatients, user?.patient_id, setUser]);

  // Determine target user ID (patient for guardians/caregivers, self for patients)
  const targetUserId =
    isHelper
      ? user?.patient_id
      : user?.user_id;

  const demoMeds = (() => {
    const key = String(targetUserId || '');
    if (!key) return DEMO_MEDICATIONS.default;
    return key.charCodeAt(key.length - 1) % 2 === 0
      ? DEMO_MEDICATIONS.default
      : DEMO_MEDICATIONS.alternate;
  })();

  const refreshHelperPatients = async () => {
    if (!isHelper || !user?.user_id || !user?.role) return;

    try {
      const response = await fetch(
        `${BASE_URL}/helper-patients?user_id=${encodeURIComponent(user.user_id)}&role=${encodeURIComponent(user.role)}`,
        {
          method: 'GET',
          headers: {
            'Accept': 'application/json',
          },
        },
      );

      const data = await response.json();
      if (!response.ok || data?.error) {
        return;
      }

      const links = Array.isArray(data?.patient_links) ? data.patient_links : [];
      setUser((prev) => {
        if (!links.length) {
          return {
            ...prev,
            patient_links: [],
            patient_id: null,
            patient_name: null,
          };
        }

        const currentStillValid = links.find((item) => item?.patient_id === prev?.patient_id);
        const backendActive = links.find((item) => item?.patient_id === data?.patient_id);
        const selected = currentStillValid || backendActive || links[0];

        return {
          ...prev,
          patient_links: links,
          patient_id: selected?.patient_id,
          patient_name: selected?.patient_name,
        };
      });
    } catch (err) {
      console.log('[HELPER PATIENTS] refresh error:', err);
    }
  };

  useFocusEffect(
    React.useCallback(() => {
      refreshHelperPatients();
    }, [isHelper, user?.user_id, user?.role]),
  );

  const handleSwitchPatient = (direction) => {
    if (helperPatients.length < 2) return;
    const currentIndex = safeActivePatientIndex;
    const delta = direction === 'next' ? 1 : -1;
    const nextIndex = (currentIndex + delta + helperPatients.length) % helperPatients.length;
    const selectedPatient = helperPatients[nextIndex];

    setUser((prev) => ({
      ...prev,
      patient_id: selectedPatient?.patient_id,
      patient_name: selectedPatient?.patient_name,
    }));
  };

  // Fetch user statistics when component mounts or user changes
  useEffect(() => {
    if (targetUserId) {
      fetchUserStats();
    }
  }, [targetUserId]);

  const fetchUserStats = async () => {
    try {
      const response = await fetch(`${BASE_URL}/user-stats/${targetUserId}`, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
        },
      });

      const data = await response.json();

      if (response.ok && !data.error) {
        setStats({
          friends_count: data.friends_count || 0,
          meds_count: data.meds_count || 0,
          status: data.status || 'Active'
        });
      }
    } catch (err) {
      console.log('[STATS] Error fetching user statistics:', err);
      // Use default values if fetch fails
      setStats({
        friends_count: 0,
        meds_count: 0,
        status: 'Active'
      });
    }
  };

  const startRecognition = async () => {
    if (!targetUserId) {
      Alert.alert('Error', 'Could not determine user account. Please log in again.');
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`${BASE_URL}/start-recognition`, {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: targetUserId
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        Alert.alert('Recognition Failed', data.detail || 'Failed to start recognition');
        return;
      }

      if (data.status === 'no_people') {
        Alert.alert(
          'No People Registered',
          data.message,
          [
            {text: 'Add Friends', onPress: () => navigation.navigate('AddFriend')},
            {text: 'Cancel', style: 'cancel'}
          ]
        );
        return;
      }

      if (data.status === 'started') {
        Alert.alert(
          'Recognition Started! 🎥',
          `${data.message}\n\n${data.instructions}\n\nPeople to recognize: ${data.people_count}`,
          [{text: 'OK'}]
        );
        return;
      }

      // Fallback for unexpected response
      Alert.alert(
        'Recognition Started! 🎥',
        `Face and voice recognition has been started.\n\nOpen the camera on your laptop to see the recognition in action!`,
        [{text: 'OK'}]
      );

    } catch (err) {
      Alert.alert(
        'Connection Error',
        'Could not start recognition. Make sure your backend is running and you are on the same Wi-Fi.',
      );
    } finally {
      setLoading(false);
    }
  };

  const handleMenuPress = (item) => {
    setSidebarOpen(false);
    if (item.action === 'startRecognition') {
      startRecognition();
    } else if (item.screen) {
      navigation.navigate(item.screen);
    }
  };

  return (
    <ScreenBg>
      <TopBar
        navigation={navigation}
        title={`welcome, ${firstName}!`}
        leftElement={
          <TouchableOpacity
            onPress={() => setSidebarOpen(true)}
            activeOpacity={0.8}
            style={styles.menuToggleBtn}>
            <Text style={styles.menuToggleIcon}>☰</Text>
          </TouchableOpacity>
        }
        rightElement={
          (user?.role === 'Guardian' || user?.role === 'CareGiver') ? (
            <TouchableOpacity
              onPress={() => navigation.navigate('AddPatient')}
              activeOpacity={0.8}
              style={styles.plusButton}
            >
              <Text style={styles.plusIcon}>+</Text>
            </TouchableOpacity>
          ) : null
        }
      />

      {/* Greeting card */}
      <View style={styles.greetCard}>
        <Text style={styles.greetSub}>{timeGreeting} {timeEmoji}</Text>
        <Text style={styles.greetName}>{user?.full_name ?? 'User'}</Text>
        <Text style={styles.greetRole}>
          {getAccountLabel(user?.role)} · {isHelper ? (user?.patient_name || 'No patient selected') : 'All systems active'}
        </Text>
      </View>

      {isHelper && helperPatients.length > 0 && (
        <View style={styles.patientSwitcher}>
          <TouchableOpacity
            style={styles.switchBtn}
            onPress={() => handleSwitchPatient('prev')}
            activeOpacity={0.8}
            disabled={helperPatients.length < 2}>
            <Text style={styles.switchBtnText}>{'<'}</Text>
          </TouchableOpacity>

          <View style={styles.switchCenter}>
            <Text style={styles.switchTitle}>Current Patient</Text>
            <Text style={styles.switchPatientName}>
              {user?.patient_name || helperPatients[safeActivePatientIndex]?.patient_name || 'Unknown'}
            </Text>
            <Text style={styles.switchCount}>
              {`${safeActivePatientIndex + 1} / ${helperPatients.length}`}
            </Text>
          </View>

          <TouchableOpacity
            style={styles.switchBtn}
            onPress={() => handleSwitchPatient('next')}
            activeOpacity={0.8}
            disabled={helperPatients.length < 2}>
            <Text style={styles.switchBtnText}>{'>'}</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Demo medications list */}
      <View style={styles.medsSection}>
        <View style={styles.medsHeaderRow}>
          <Text style={styles.medsTitle}>Today&apos;s Medications</Text>
          <Text style={styles.medsSubtitle}>Demo Data</Text>
        </View>

        {demoMeds.map((med, index) => (
          <View key={`${med.name}-${index}`} style={styles.medRow}>
            <View style={styles.medInfo}>
              <Text style={styles.medName}>{med.name}</Text>
              <Text style={styles.medSchedule}>Take at {med.schedule}</Text>
            </View>
            <View style={styles.medTimePill}>
              <Text style={styles.medTimeText}>{med.schedule}</Text>
            </View>
          </View>
        ))}
      </View>

      {sidebarOpen && (
        <View style={styles.sidebarOverlay}>
          <TouchableOpacity
            style={styles.sidebarBackdrop}
            activeOpacity={1}
            onPress={() => setSidebarOpen(false)}
          />

          <View style={styles.sidebarPanel}>
            <View style={styles.sidebarHeader}>
              <Text style={styles.sidebarTitle}>Dashboard</Text>
              <TouchableOpacity
                onPress={() => setSidebarOpen(false)}
                activeOpacity={0.8}
                style={styles.sidebarCloseBtn}>
                <Text style={styles.sidebarCloseText}>✕</Text>
              </TouchableOpacity>
            </View>

            {MENU_ITEMS.map((item, index) => (
              <TouchableOpacity
                key={item.screen || item.action || index}
                style={styles.sidebarItem}
                onPress={() => handleMenuPress(item)}
                activeOpacity={0.82}
                disabled={loading && item.action === 'startRecognition'}>
                <Text style={styles.sidebarItemIcon}>{item.icon}</Text>
                <Text style={styles.sidebarItemLabel}>
                  {loading && item.action === 'startRecognition' ? 'Starting...' : item.label}
                </Text>
                {loading && item.action === 'startRecognition' && (
                  <ActivityIndicator size="small" color={COLORS.white} />
                )}
              </TouchableOpacity>
            ))}
          </View>
        </View>
      )}

      {/* Quick stats */}
      <View style={styles.statsRow}>
        <View style={styles.statCard}>
          <Text style={styles.statValue}>{stats?.friends_count ?? 0}</Text>
          <Text style={styles.statLabel}>Friends</Text>
        </View>
        <View style={styles.statCard}>
          <Text style={styles.statValue}>{stats?.meds_count ?? 0}</Text>
          <Text style={styles.statLabel}>Meds</Text>
        </View>
      </View>
    </ScreenBg>
  );
}

const styles = StyleSheet.create({
  greetCard: {
    marginHorizontal: 18,
    marginTop: 8,
    backgroundColor: 'rgba(255,255,255,0.07)',
    borderRadius: 22,
    padding: 18,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.09)',
  },
  greetSub: {
    fontSize: 13,
    fontWeight: '300',
    color: 'rgba(255,255,255,0.55)',
    marginBottom: 3,
  },
  greetName: {
    fontSize: 22,
    fontWeight: '700',
    color: COLORS.white,
  },
  greetRole: {
    fontSize: 12,
    fontWeight: '300',
    color: 'rgba(255,255,255,0.45)',
    marginTop: 4,
  },
  menuToggleBtn: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: 'rgba(255,255,255,0.14)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  menuToggleIcon: {
    color: COLORS.white,
    fontSize: 17,
    fontWeight: '700',
  },

  sidebarOverlay: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 30,
  },
  sidebarBackdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.35)',
  },
  sidebarPanel: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    left: 0,
    width: Math.min(300, width * 0.78),
    backgroundColor: COLORS.bgDark,
    borderRightWidth: 1,
    borderRightColor: 'rgba(255,255,255,0.08)',
    paddingTop: Platform.OS === 'ios' ? 58 : 40,
    paddingHorizontal: 14,
  },
  sidebarHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 14,
  },
  sidebarTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: COLORS.white,
  },
  sidebarCloseBtn: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: 'rgba(255,255,255,0.14)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  sidebarCloseText: {
    color: COLORS.white,
    fontWeight: '700',
    fontSize: 14,
  },
  sidebarItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderRadius: 12,
    paddingVertical: 12,
    paddingHorizontal: 12,
    marginBottom: 8,
    backgroundColor: 'rgba(255,255,255,0.08)',
  },
  sidebarItemIcon: {
    fontSize: 18,
  },
  sidebarItemLabel: {
    flex: 1,
    fontSize: 15,
    fontWeight: '600',
    color: COLORS.white,
  },
  medsSection: {
    marginTop: 14,
    marginHorizontal: 18,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.1)',
    backgroundColor: 'rgba(255,255,255,0.06)',
    paddingVertical: 12,
    paddingHorizontal: 12,
  },
  medsHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  medsTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: COLORS.white,
  },
  medsSubtitle: {
    fontSize: 11,
    color: 'rgba(255,255,255,0.6)',
  },
  medRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
    paddingVertical: 8,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255,255,255,0.08)',
  },
  medInfo: {
    flex: 1,
  },
  medName: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.white,
  },
  medSchedule: {
    marginTop: 2,
    fontSize: 12,
    color: 'rgba(255,255,255,0.65)',
  },
  medTimePill: {
    borderRadius: 14,
    paddingVertical: 4,
    paddingHorizontal: 10,
    backgroundColor: 'rgba(126,207,212,0.3)',
  },
  medTimeText: {
    fontSize: 11,
    fontWeight: '700',
    color: COLORS.white,
  },
  statsRow: {
    position: 'absolute',
    bottom: Platform.OS === 'ios' ? 50 : 32,
    left: 18,
    right: 18,
    flexDirection: 'row',
    gap: 10,
  },
  statCard: {
    flex: 1,
    backgroundColor: 'rgba(255,255,255,0.07)',
    borderRadius: 18,
    paddingVertical: 14,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
  },
  statValue: {
    fontSize: 22,
    fontWeight: '700',
    color: COLORS.teal,
  },
  statLabel: {
    fontSize: 11,
    fontWeight: '300',
    color: 'rgba(255,255,255,0.5)',
    marginTop: 3,
  },
  plusButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: COLORS.teal,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 2},
    shadowOpacity: 0.3,
    shadowRadius: 4,
    elevation: 4,
  },
  plusIcon: {
    fontSize: 24,
    fontWeight: 'bold',
    color: COLORS.white,
  },
  patientSwitcher: {
    marginTop: 12,
    marginHorizontal: 18,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.1)',
    backgroundColor: 'rgba(255,255,255,0.06)',
    paddingVertical: 10,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  switchBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: 'rgba(255,255,255,0.15)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  switchBtnText: {
    color: COLORS.white,
    fontSize: 18,
    fontWeight: '700',
  },
  switchCenter: {
    flex: 1,
    alignItems: 'center',
  },
  switchTitle: {
    fontSize: 11,
    color: 'rgba(255,255,255,0.65)',
  },
  switchPatientName: {
    marginTop: 2,
    fontSize: 15,
    fontWeight: '700',
    color: COLORS.white,
  },
  switchCount: {
    marginTop: 2,
    fontSize: 11,
    color: 'rgba(255,255,255,0.7)',
  },
});