import React, {useState, useEffect, useRef} from 'react';
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
import {fetchPatientMedications} from '../services/medicationService';
import {getMedAlerts, markAlertAsRead} from '../services/alertService';

const {width} = Dimensions.get('window');

const MENU_ITEMS = [
  {label: 'Profile',          icon: '🧑', screen: 'UserProfile'},
  {label: 'Add Friends',      icon: '👥', screen: 'AddFriend'},
  {label: 'My Contacts',     icon: '🧑‍🤝‍🧑', screen: 'PeopleList'},
  {label: 'Add Meds',         icon: '💊', screen: 'AddMed'},
  {label: 'My Meds',          icon: '📋', screen: 'MedsList'},
  {label: 'HB',               icon: '💓', screen: 'HB'},
  {label: 'GEO-Location',     icon: '📍', screen: 'GeoLocation'},
  {label: 'Face Recognition', icon: '👁️', action: 'startRecognition'},
];

const getAccountLabel = (role) => {
  if (role === 'Guardian') return 'Guardian Account';
  if (role === 'CareGiver') return 'Caregiver Account';
  return 'Patient Account';
};

const formatMedicationSchedule = (med) => {
  // Prefer explicit top-level date/time fields
  const days = Array.isArray(med?.date)
    ? med.date.join(', ')
    : typeof med?.date === 'string' ? med.date : null;
  const time = med?.time || null;
  if (days || time) return [days, time].filter(Boolean).join(' • ');

  // Fall back to nested schedule object
  const schedule = med?.schedule;
  if (!schedule) return 'No schedule set';
  if (typeof schedule === 'string') return schedule;
  const parts = [];
  if (Array.isArray(schedule.days) && schedule.days.length > 0) parts.push(schedule.days.join(', '));
  if (schedule.time) parts.push(schedule.time);
  else if (schedule.hour && schedule.minute && schedule.period) parts.push(`${schedule.hour}:${schedule.minute} ${schedule.period}`);
  return parts.length > 0 ? parts.join(' • ') : 'No schedule set';
};

const normalizeMedication = (med, index) => ({
  id: med?._id || `${med?.name || 'med'}-${index}`,
  name: med?.name || med?.medication_name || 'Medication',
  schedule: formatMedicationSchedule(med),
});

const TODAY_DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

const isScheduledToday = (med) => {
  const schedule = med?.schedule;
  if (!schedule || typeof schedule === 'string') return false;
  if (!Array.isArray(schedule.days) || schedule.days.length === 0) return false;
  const todayShort = TODAY_DAYS[new Date().getDay()];
  return schedule.days.includes(todayShort);
};

export default function DashboardScreen({navigation}) {
  const {user, setUser} = useAuth();
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [medications, setMedications] = useState([]);
  const [medsLoading, setMedsLoading] = useState(false);
  const [friendsLoading, setFriendsLoading] = useState(false);
  const [stats, setStats] = useState({
    friends_count: 0,
    meds_count: 0,
    status: 'Active'
  });
  // Active medication alert (most recent unread medication_due alert)
  const [medAlert, setMedAlert] = useState(null);
  const medAlertPollRef = useRef(null);

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

  const loadMedications = async () => {
    if (!targetUserId) {
      setMedications([]);
      setStats((prev) => ({ ...prev, meds_count: 0 }));
      return;
    }

    setMedsLoading(true);
    try {
      const data = await fetchPatientMedications(targetUserId);
      const items = Array.isArray(data?.items) ? data.items : [];
      const todayItems = items.filter(isScheduledToday);
      setMedications(todayItems.map(normalizeMedication));
      setStats((prev) => ({ ...prev, meds_count: items.length }));
    } catch (err) {
      console.log('[MEDS] Error fetching patient medications:', err);
      setMedications([]);
      setStats((prev) => ({ ...prev, meds_count: 0 }));
    } finally {
      setMedsLoading(false);
    }
  };

  const loadPatientFriendsCount = async () => {
    if (!targetUserId) {
      setStats((prev) => ({ ...prev, friends_count: 0 }));
      return;
    }

    setFriendsLoading(true);
    try {
      const response = await fetch(`${BASE_URL}/people/${encodeURIComponent(targetUserId)}`, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
        },
      });
      const data = await response.json();

      if (response.ok && !data?.error) {
        const count = Number(data.count ?? (Array.isArray(data.people) ? data.people.length : 0));
        setStats((prev) => ({ ...prev, friends_count: count }));
      } else {
        setStats((prev) => ({ ...prev, friends_count: 0 }));
      }
    } catch (err) {
      console.log('[FRIENDS] Error fetching patient friends count:', err);
      setStats((prev) => ({ ...prev, friends_count: 0 }));
    } finally {
      setFriendsLoading(false);
    }
  };

  const refreshHelperPatients = async () => {
    if (!isHelper || !user?.user_id || !user?.role) return;

    try {
      const response = await fetch(
        `${BASE_URL}/users/helper-patients?user_id=${encodeURIComponent(user.user_id)}&role=${encodeURIComponent(user.role)}`,
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

  const checkMedAlerts = React.useCallback(async () => {
    if (!targetUserId) return;
    const alerts = await getMedAlerts(targetUserId);
    setMedAlert(alerts.length > 0 ? alerts[0] : null);
  }, [targetUserId]);

  const dismissMedAlert = async () => {
    if (!medAlert?._id) {
      setMedAlert(null);
      return;
    }
    try {
      await markAlertAsRead(medAlert._id);
    } catch (_) {}
    setMedAlert(null);
  };

  useFocusEffect(
    React.useCallback(() => {
      refreshHelperPatients();
      if (targetUserId) {
        loadMedications();
        loadPatientFriendsCount();
        checkMedAlerts();
      }

      // Poll for medication alerts every 15 seconds while screen is focused
      medAlertPollRef.current = setInterval(() => {
        checkMedAlerts();
      }, 15000);

      return () => {
        if (medAlertPollRef.current) {
          clearInterval(medAlertPollRef.current);
          medAlertPollRef.current = null;
        }
      };
    }, [isHelper, user?.user_id, user?.role, targetUserId, checkMedAlerts]),
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

  // Fetch user statistics and patient-specific counts when the selected patient changes
  useEffect(() => {
    if (targetUserId) {
      fetchUserStats();
      loadMedications();
      loadPatientFriendsCount();
    } else {
      setMedications([]);
      setStats((prev) => ({ ...prev, friends_count: 0, meds_count: 0, status: 'Active' }));
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
        setStats((prev) => ({
          ...prev,
          status: data.status || 'Active'
        }));
      }
    } catch (err) {
      console.log('[STATS] Error fetching user statistics:', err);
      setStats((prev) => ({
        ...prev,
        status: 'Active'
      }));
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
        headers: {'Accept': 'application/json', 'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: targetUserId}),
      });
      const data = await response.json();
      if (!response.ok) {
        Alert.alert('Failed', data.detail || 'Could not start recognition');
        return;
      }
      if (data.status === 'no_people') {
        Alert.alert('No People Registered', data.message, [
          {text: 'Add Friends', onPress: () => navigation.navigate('AddFriend')},
          {text: 'Cancel', style: 'cancel'},
        ]);
        return;
      }
      Alert.alert('Recognition Started', 'The Pi camera is now open and recognizing faces.');
    } catch (err) {
      Alert.alert('Connection Error', 'Cannot reach the backend. Make sure you are on the same Wi-Fi.');
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
        title={`Welcome, ${firstName}!`}
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

      {/* Medication alert banner */}
      {medAlert ? (
        <View style={styles.medAlertBanner}>
          <View style={styles.medAlertLeft}>
            <Text style={styles.medAlertIcon}>💊</Text>
            <View style={styles.medAlertTextGroup}>
              <Text style={styles.medAlertTitle}>Medication Reminder</Text>
              <Text style={styles.medAlertName} numberOfLines={1}>
                {medAlert.medication_name || 'Medication'}
              </Text>
              <Text style={styles.medAlertSub}>
                Camera scanning for medication...
              </Text>
            </View>
          </View>
          <TouchableOpacity
            onPress={dismissMedAlert}
            style={styles.medAlertDismiss}
            activeOpacity={0.7}>
            <Text style={styles.medAlertDismissText}>✕</Text>
          </TouchableOpacity>
        </View>
      ) : null}

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

      {/* Patient medications list */}
      <View style={styles.medsSection}>
        <View style={styles.medsHeaderRow}>
          <Text style={styles.medsTitle}>Today&apos;s Medications</Text>
          <Text style={styles.medsSubtitle}>{medsLoading ? 'Loading...' : 'From patient record'}</Text>
        </View>

        {!medsLoading && medications.length === 0 ? (
          <View style={styles.medEmptyState}>
            <Text style={styles.medEmptyText}>No medications scheduled for today.</Text>
          </View>
        ) : null}

        {medications.map((med, index) => (
          <View key={med.id} style={styles.medRow}>
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
  medAlertBanner: {
    marginHorizontal: 18,
    marginTop: 10,
    borderRadius: 16,
    paddingVertical: 12,
    paddingHorizontal: 14,
    backgroundColor: 'rgba(255, 165, 0, 0.18)',
    borderWidth: 1,
    borderColor: 'rgba(255, 165, 0, 0.55)',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  medAlertLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    gap: 10,
  },
  medAlertIcon: {
    fontSize: 24,
  },
  medAlertTextGroup: {
    flex: 1,
  },
  medAlertTitle: {
    fontSize: 12,
    fontWeight: '600',
    color: 'rgba(255, 200, 100, 0.95)',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  medAlertName: {
    fontSize: 15,
    fontWeight: '700',
    color: COLORS.white,
    marginTop: 1,
  },
  medAlertSub: {
    fontSize: 11,
    color: 'rgba(255,255,255,0.65)',
    marginTop: 2,
  },
  medAlertDismiss: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: 'rgba(255,255,255,0.15)',
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 8,
  },
  medAlertDismissText: {
    color: COLORS.white,
    fontSize: 13,
    fontWeight: '700',
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
  medEmptyState: {
    paddingVertical: 10,
  },
  medEmptyText: {
    fontSize: 12,
    color: 'rgba(255,255,255,0.65)',
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